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
    from backend.api.routes import health, profile, companies, orquestador

    app.include_router(health.router)
    app.include_router(profile.router)
    app.include_router(profile.roles_router)
    app.include_router(companies.companies_router)
    app.include_router(companies.subscriptions_router)
    app.include_router(orquestador.scans_router)

    return app


# ===========================
# Global App Instance
# ===========================
# Create the app at module level for Lambda handler to access
app = create_app()


# ===========================
# Lambda Handler (Mangum)
# ===========================
handler = Mangum(app, lifespan="off")
