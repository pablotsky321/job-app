"""
FastAPI application factory and Lambda handler.

Provides:
- FastAPI app initialization with CORS middleware
- Startup event that validates all environment variables and Bedrock models
- Structured logging setup
- Mangum ASGI handler for Lambda
- Cold start optimization via deferred imports (boto3, Bedrock init)

Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 23.1, 23.2, 23.3, 22.1, 22.2, 22.4, 16.2
"""

import os
import json
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from backend.shared.logging_config import get_contextual_logger, RequestContext
from backend.shared.errors import AppException

# Initialize logger
logger = get_contextual_logger(__name__)


# Track whether startup has been done (for Lambda cold start optimization)
_startup_done = False


async def _validate_startup() -> None:
    """
    Validate environment and initialize Bedrock on Lambda startup.

    This runs once when the Lambda container starts (cold start).
    If any validation fails, the entire Lambda is marked as failed.

    Validates:
    1. All required environment variables are set
    2. All table names are set and valid
    3. Bedrock models are accessible
    """
    global _startup_done
    
    if _startup_done:
        return

    logger.info("lambda_startup_begin")

    # Required environment variables (Req 16.2, 21.5, 23.1)
    required_env_vars = [
        "BEDROCK_REGION",
        "BEDROCK_MODEL_SMALL",
        "BEDROCK_MODEL_MID",
        "DYNAMODB_TABLE_EMPRESAS",
        "DYNAMODB_TABLE_VACANTES",
        "DYNAMODB_TABLE_USUARIO_VACANTE",
        "DYNAMODB_TABLE_PERFILES",
        "DYNAMODB_TABLE_SUSCRIPCIONES",
        "DYNAMODB_TABLE_SCAN_JOBS",
        "DYNAMODB_TABLE_ENTRADAS",
        "SQS_QUEUE_SCAN_URL",
        "SQS_QUEUE_SCAN_DLQ_URL",
        "SQS_QUEUE_SCORING_URL",
        "SQS_QUEUE_SCORING_DLQ_URL",
        "CORS_ALLOWED_ORIGINS",
    ]

    missing_vars = []
    for var_name in required_env_vars:
        if not os.getenv(var_name):
            missing_vars.append(var_name)

    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(
            "startup_validation_failed_env_vars",
            context={
                "missing_vars": missing_vars,
                "error": error_msg,
            },
        )
        raise RuntimeError(error_msg)

    logger.info(
        "startup_validation_env_vars_ok",
        context={"vars_checked": len(required_env_vars)},
    )

    # Validate Bedrock models (Req 11.2, 21.5)
    try:
        from backend.shared.bedrock import startup_validation
        startup_validation()
    except RuntimeError as e:
        logger.error(
            "startup_validation_failed_bedrock",
            context={
                "error": str(e),
            },
        )
        raise

    logger.info("lambda_startup_complete")
    _startup_done = True


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    - Sets up CORS middleware from CORS_ALLOWED_ORIGINS env var
    - Registers all route blueprints
    - Configures exception handlers
    - Returns app ready for Mangum handler

    Startup events (run once per Lambda container):
    - Validate all required environment variables
    - Call bedrock.startup_validation() to test model accessibility
    - Initialize route handlers

    Returns:
        Configured FastAPI application instance
    """
    
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator:
        """Lifespan context manager for startup/shutdown events."""
        # Startup
        await _validate_startup()
        yield
        # Shutdown (cleanup if needed)

    app = FastAPI(
        title="Job-App Backend API",
        description="REST API for job search platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ===========================
    # CORS Configuration (Req 23)
    # ===========================
    cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    origins_list = [origin.strip() for origin in cors_origins.split(",")]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # ===========================
    # Exception Handlers
    # ===========================
    @app.exception_handler(AppException)
    async def app_exception_handler(request, exc: AppException):
        """Handle custom AppException and convert to JSON response."""
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc: Exception):
        """Handle unexpected exceptions."""
        logger.error(
            "unhandled_exception",
            context={
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred",
            },
        )

    # ===========================
    # Route Registration
    # ===========================
    from backend.api.routes import health, profile, companies, orquestador, vacancies, entries

    app.include_router(health.router)
    app.include_router(profile.router)
    app.include_router(profile.roles_router)
    app.include_router(companies.companies_router)
    app.include_router(companies.subscriptions_router)
    app.include_router(orquestador.scans_router)
    app.include_router(vacancies.router)
    app.include_router(entries.entries_router)

    return app


# ===========================
# Global App Instance
# ===========================
# Create the app at module level for Lambda handler to access
app = create_app()


# ===========================
# Lambda Handler (Mangum + EventBridge Scheduler routing)
# ===========================
_mangum_handler = Mangum(app, lifespan="off")


def _handle_programmed_scan(event: dict, context) -> dict:
    """
    Handle programmed-mode scan invoked by EventBridge Scheduler.

    No userId — scans the union of ALL active subscriptions across all users.
    Creates a ScanJob with userId=None.

    Requirements: 8.1, 8.2, 8.3, 8.4
    """
    import uuid
    from datetime import datetime, timezone
    from typing import List

    import boto3

    from backend.shared.db import scan_all_items, put_item, _get_dynamodb_client, TABLES
    from backend.api.routes.orquestador import (
        es_elegible_para_rescan,
        ScanMessage,
        _build_scan_job,
    )

    started_at = datetime.now(timezone.utc)
    scan_job_id = f"scan_{started_at.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    logger.info(
        "programmed_scan_start",
        context={"scan_job_id": scan_job_id, "source": "eventbridge-scheduler"},
    )

    # ---------------------------------------------------------------
    # Step 1: Resolve ALL active subscriptions across all users (Req 8.3)
    # Deduplicate by companyId
    # ---------------------------------------------------------------
    all_suscripciones = scan_all_items("suscripciones")

    company_ids_set: set = set()
    for item in all_suscripciones:
        if item.get("activa", False):
            company_id = item.get("companyId")
            if company_id:
                company_ids_set.add(company_id)

    company_ids: List[str] = list(company_ids_set)

    # ---------------------------------------------------------------
    # Step 2: Zero companies → DONE immediately
    # ---------------------------------------------------------------
    if not company_ids:
        scan_job_item = _build_scan_job(
            scan_job_id=scan_job_id,
            user_id=None,
            status="DONE",
            empresas_total=0,
            empresas_omitidas=[],
            empresas_fallidas=[],
            started_at=started_at,
        )
        put_item("scan_jobs", scan_job_item)

        logger.info(
            "programmed_scan_done_zero_companies",
            context={"scan_job_id": scan_job_id},
        )
        return {"statusCode": 200, "body": {"jobId": scan_job_id, "status": "DONE"}}

    # ---------------------------------------------------------------
    # Step 3: Load each Empresa and apply Ventana_Frescura (Req 8)
    # ---------------------------------------------------------------
    dynamodb = _get_dynamodb_client()
    empresas_table = dynamodb.Table(TABLES["empresas"])

    empresas_a_escanear: List[str] = []
    empresas_omitidas: List[str] = []

    for company_id in company_ids:
        try:
            response = empresas_table.get_item(Key={"companyId": company_id})
            empresa = response.get("Item")
        except Exception:
            empresa = None

        if not empresa:
            # Company not found in catalog — treat as eligible
            empresas_a_escanear.append(company_id)
            continue

        if es_elegible_para_rescan(empresa, started_at):
            empresas_a_escanear.append(company_id)
        else:
            empresas_omitidas.append(company_id)

    # ---------------------------------------------------------------
    # Step 4: All omitted → DONE immediately
    # ---------------------------------------------------------------
    if not empresas_a_escanear:
        scan_job_item = _build_scan_job(
            scan_job_id=scan_job_id,
            user_id=None,
            status="DONE",
            empresas_total=len(company_ids),
            empresas_omitidas=empresas_omitidas,
            empresas_fallidas=[],
            started_at=started_at,
        )
        put_item("scan_jobs", scan_job_item)

        logger.info(
            "programmed_scan_done_all_omitted",
            context={
                "scan_job_id": scan_job_id,
                "empresas_omitidas": len(empresas_omitidas),
            },
        )
        return {"statusCode": 200, "body": {"jobId": scan_job_id, "status": "DONE"}}

    # ---------------------------------------------------------------
    # Step 5: Create ScanJob with RUNNING (userId=None for programmed)
    # ---------------------------------------------------------------
    scan_job_item = _build_scan_job(
        scan_job_id=scan_job_id,
        user_id=None,
        status="RUNNING",
        empresas_total=len(empresas_a_escanear),
        empresas_omitidas=empresas_omitidas,
        empresas_fallidas=[],
        started_at=started_at,
    )
    put_item("scan_jobs", scan_job_item)

    # ---------------------------------------------------------------
    # Step 6: Publish ScanMessages to SQS_Scan
    # ---------------------------------------------------------------
    sqs_url = os.environ.get("SQS_QUEUE_SCAN_URL", "")
    sqs_client = boto3.client("sqs")

    failed_to_publish: List[str] = []

    for company_id in empresas_a_escanear:
        try:
            msg = ScanMessage(jobId=scan_job_id, companyId=company_id)
            sqs_client.send_message(
                QueueUrl=sqs_url,
                MessageBody=msg.model_dump_json(),
            )
        except Exception as e:
            logger.error(
                "programmed_scan_sqs_publish_failed",
                context={
                    "scan_job_id": scan_job_id,
                    "company_id": company_id,
                    "error": str(e)[:200],
                },
            )
            failed_to_publish.append(company_id)

    # ---------------------------------------------------------------
    # Step 7: Determine final status
    # ---------------------------------------------------------------
    final_status = "RUNNING"
    empresas_fallidas: List[str] = []

    if failed_to_publish:
        if len(failed_to_publish) == len(empresas_a_escanear):
            # ALL failed → FAILED
            final_status = "FAILED"
            empresas_fallidas = failed_to_publish
            logger.error(
                "programmed_scan_all_publish_failed",
                context={
                    "scan_job_id": scan_job_id,
                    "failed_count": len(failed_to_publish),
                    "total_attempted": len(empresas_a_escanear),
                },
            )
        else:
            # SOME failed → PARCIAL
            final_status = "PARCIAL"
            empresas_fallidas = failed_to_publish
            logger.warning(
                "programmed_scan_partial_publish_failure",
                context={
                    "scan_job_id": scan_job_id,
                    "success_count": len(empresas_a_escanear) - len(failed_to_publish),
                    "failed_count": len(failed_to_publish),
                },
            )

    # ---------------------------------------------------------------
    # Step 8: Update ScanJob with final status if changed
    # ---------------------------------------------------------------
    if final_status != "RUNNING" or empresas_fallidas:
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        scan_jobs_table = dynamodb.Table(TABLES["scan_jobs"])
        scan_jobs_table.update_item(
            Key={"scanJobId": scan_job_id},
            UpdateExpression="SET #s = :status, empresasFallidas = :fallidas, updatedAt = :upd",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": final_status,
                ":fallidas": empresas_fallidas,
                ":upd": updated_at,
            },
        )

    logger.info(
        "programmed_scan_complete",
        context={
            "scan_job_id": scan_job_id,
            "final_status": final_status,
            "empresas_total": len(empresas_a_escanear),
            "empresas_omitidas": len(empresas_omitidas),
            "empresas_fallidas": len(empresas_fallidas),
        },
    )

    return {"statusCode": 200, "body": {"jobId": scan_job_id, "status": final_status}}


def handler(event, context):
    """
    Lambda handler that routes EventBridge Scheduler events to programmed mode,
    and all other events (API Gateway) to FastAPI/Mangum.

    Requirements: 8.1, 8.2, 8.3, 8.4
    """
    if event.get("source") == "eventbridge-scheduler":
        return _handle_programmed_scan(event, context)
    return _mangum_handler(event, context)
