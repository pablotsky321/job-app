"""
Orquestador endpoints: POST /scans, GET /scans/{jobId}.

POST /scans: Triggers an async scan of all companies the user is subscribed to.
GET /scans/{jobId}: Polls scan job progress with zombie detection.

Requirements: 8, 9, 10, 11, 14, 15
"""

import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import boto3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.shared.logging_config import get_contextual_logger
from backend.shared.db import query_by_pk, put_item, _get_dynamodb_client, TABLES
from backend.api.routes.auth import get_current_user_id

logger = get_contextual_logger(__name__)

scans_router = APIRouter(prefix="/scans", tags=["scans"])

# ============================================================================
# Response Models
# ============================================================================


class PostScansResponse(BaseModel):
    """Response for POST /scans."""

    jobId: str


class ScanJobStatusResponse(BaseModel):
    """Response for GET /scans/{jobId}."""

    status: str
    empresasTotal: int
    completados: int
    omitidos: int
    fallidos: int
    startedAt: str
    canStop: bool
    pendingCompanies: Optional[List[str]] = None


# ============================================================================
# SQS Message Model (lightweight, only for publishing)
# ============================================================================


class ScanMessage(BaseModel):
    """Message payload for SQS_Scan queue."""

    jobId: str
    companyId: str


# ============================================================================
# Ventana de Frescura Logic (Requirement 8)
# ============================================================================


def es_elegible_para_rescan(
    empresa: dict, started_at: datetime
) -> bool:
    """
    Determine if an Empresa is eligible for re-scan based on Ventana_Frescura.

    Rules (Requirement 8):
    - No lastScannedAt → always eligible (8.3)
    - ultimoOrigenExitoso in [board_api, json_ld] → eligible if elapsed >= 3600s (8.1)
    - ultimoOrigenExitoso == html_llm → eligible if elapsed >= 43200s (8.2)
    - ultimoOrigenExitoso absent/null → eligible if elapsed >= 43200s (8.4)
    """
    last_scanned = empresa.get("lastScannedAt")

    if not last_scanned:
        return True  # Requirement 8.3

    # Parse lastScannedAt if it's a string
    if isinstance(last_scanned, str):
        last_scanned = datetime.fromisoformat(last_scanned.replace("Z", "+00:00"))

    elapsed = (started_at - last_scanned).total_seconds()

    ultimo_origen = empresa.get("ultimoOrigenExitoso")

    if ultimo_origen in ("board_api", "json_ld"):
        return elapsed >= 3600  # Requirement 8.1
    elif ultimo_origen == "html_llm":
        return elapsed >= 43200  # Requirement 8.2
    else:
        # No ultimoOrigenExitoso recorded (null or unrecognized)
        return elapsed >= 43200  # Requirement 8.4


# ============================================================================
# POST /scans Endpoint
# ============================================================================


@scans_router.post("", response_model=PostScansResponse)
async def post_scans(user_id: str = Depends(get_current_user_id)):
    """
    Trigger an async scan of all companies the authenticated user is subscribed to.

    Flow:
    1. Extract userId from JWT (via dependency)
    2. Resolve active Suscripciones, deduplicate companyIds
    3. If zero companies → create ScanJob with status=DONE, return jobId
    4. Apply Ventana_Frescura to each Empresa
    5. If all omitted → create ScanJob with status=DONE, return jobId
    6. Create ScanJob with status=RUNNING
    7. Publish one ScanMessage per eligible company to SQS_Scan
    8. Handle publish failures: ALL fail → FAILED; SOME fail → PARCIAL
    9. Update ScanJob with final status
    10. Return jobId (HTTP 200)

    Requirements: 8, 9, 10, 11
    """
    started_at = datetime.now(timezone.utc)
    scan_job_id = f"scan_{started_at.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    logger.info(
        "post_scans_start",
        context={"user_id": user_id, "scan_job_id": scan_job_id},
    )

    # ---------------------------------------------------------------
    # Step 1: Resolve active Suscripciones and deduplicate companyIds
    # Requirement 9.2, 9.4
    # ---------------------------------------------------------------
    suscripciones_items = query_by_pk(
        "suscripciones", "userId", user_id, limit=1000
    )

    # Filter active and deduplicate companyIds
    company_ids_set: set = set()
    for item in suscripciones_items:
        if item.get("activa", False):
            company_id = item.get("companyId")
            if company_id:
                company_ids_set.add(company_id)

    company_ids: List[str] = list(company_ids_set)

    # ---------------------------------------------------------------
    # Step 2: Zero companies → DONE immediately (Requirement 10.1)
    # ---------------------------------------------------------------
    if not company_ids:
        scan_job_item = _build_scan_job(
            scan_job_id=scan_job_id,
            user_id=user_id,
            status="DONE",
            empresas_total=0,
            empresas_omitidas=[],
            empresas_fallidas=[],
            started_at=started_at,
        )
        put_item("scan_jobs", scan_job_item)

        logger.info(
            "post_scans_done_zero_companies",
            context={"scan_job_id": scan_job_id, "user_id": user_id},
        )
        return PostScansResponse(jobId=scan_job_id)

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
            # Company not found in catalog — treat as eligible (will fail in worker)
            empresas_a_escanear.append(company_id)
            continue

        if es_elegible_para_rescan(empresa, started_at):
            empresas_a_escanear.append(company_id)
        else:
            empresas_omitidas.append(company_id)

    # ---------------------------------------------------------------
    # Step 4: All omitted → DONE immediately (Requirement 10.2)
    # ---------------------------------------------------------------
    if not empresas_a_escanear:
        scan_job_item = _build_scan_job(
            scan_job_id=scan_job_id,
            user_id=user_id,
            status="DONE",
            empresas_total=len(company_ids),
            empresas_omitidas=empresas_omitidas,
            empresas_fallidas=[],
            started_at=started_at,
        )
        put_item("scan_jobs", scan_job_item)

        logger.info(
            "post_scans_done_all_omitted",
            context={
                "scan_job_id": scan_job_id,
                "empresas_omitidas": len(empresas_omitidas),
            },
        )
        return PostScansResponse(jobId=scan_job_id)

    # ---------------------------------------------------------------
    # Step 5: Create ScanJob with RUNNING (Requirement 9.5)
    # empresasTotal = count of empresas_a_escanear (AFTER Ventana_Frescura)
    # ---------------------------------------------------------------
    scan_job_item = _build_scan_job(
        scan_job_id=scan_job_id,
        user_id=user_id,
        status="RUNNING",
        empresas_total=len(empresas_a_escanear),
        empresas_omitidas=empresas_omitidas,
        empresas_fallidas=[],
        started_at=started_at,
    )
    put_item("scan_jobs", scan_job_item)

    # ---------------------------------------------------------------
    # Step 6: Publish ScanMessages to SQS_Scan (Requirement 9.8, 11.1)
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
                "sqs_publish_failed",
                context={
                    "scan_job_id": scan_job_id,
                    "company_id": company_id,
                    "error": str(e)[:200],
                },
            )
            failed_to_publish.append(company_id)

    # ---------------------------------------------------------------
    # Step 7: Determine final status (Requirement 11.2, 11.3)
    # ---------------------------------------------------------------
    final_status = "RUNNING"
    empresas_fallidas: List[str] = []

    if failed_to_publish:
        if len(failed_to_publish) == len(empresas_a_escanear):
            # ALL failed → FAILED (Requirement 11.2)
            final_status = "FAILED"
            empresas_fallidas = failed_to_publish
            logger.error(
                "post_scans_all_publish_failed",
                context={
                    "scan_job_id": scan_job_id,
                    "failed_count": len(failed_to_publish),
                    "total_attempted": len(empresas_a_escanear),
                },
            )
        else:
            # SOME failed → PARCIAL (Requirement 11.3)
            final_status = "PARCIAL"
            empresas_fallidas = failed_to_publish
            logger.warning(
                "post_scans_partial_publish_failure",
                context={
                    "scan_job_id": scan_job_id,
                    "success_count": len(empresas_a_escanear) - len(failed_to_publish),
                    "failed_count": len(failed_to_publish),
                },
            )

    # ---------------------------------------------------------------
    # Step 8: Update ScanJob with final status if changed (Req 11)
    # ---------------------------------------------------------------
    if final_status != "RUNNING" or empresas_fallidas:
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        update_fields = {
            "status": final_status,
            "empresasFallidas": empresas_fallidas,
            "updatedAt": updated_at,
        }

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
        "post_scans_complete",
        context={
            "scan_job_id": scan_job_id,
            "final_status": final_status,
            "empresas_total": len(empresas_a_escanear),
            "empresas_omitidas": len(empresas_omitidas),
            "empresas_fallidas": len(empresas_fallidas),
        },
    )

    return PostScansResponse(jobId=scan_job_id)


# ============================================================================
# Private Helpers
# ============================================================================


def _build_scan_job(
    scan_job_id: str,
    user_id: Optional[str],
    status: str,
    empresas_total: int,
    empresas_omitidas: List[str],
    empresas_fallidas: List[str],
    started_at: datetime,
) -> dict:
    """Build a ScanJob DynamoDB item dict."""
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    started_iso = started_at.isoformat().replace("+00:00", "Z")

    item = {
        "scanJobId": scan_job_id,
        "status": status,
        "empresasTotal": empresas_total,
        "empresasCompletadas": [],  # String Set starts empty
        "empresasOmitidas": empresas_omitidas,
        "empresasFallidas": empresas_fallidas,
        "startedAt": started_iso,
        "updatedAt": now_iso,
    }

    if user_id is not None:
        item["userId"] = user_id

    return item


# ============================================================================
# Constants
# ============================================================================

ZOMBIE_THRESHOLD_SECONDS = 600  # 10 minutes


# ============================================================================
# GET /scans/{jobId} - Poll scan job progress (Requirement 14, 15)
# ============================================================================


@scans_router.get("/{job_id}", response_model=ScanJobStatusResponse)
async def get_scan_job_status(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Poll scan job progress.

    Endpoint: GET /scans/{jobId}
    Auth: Required (JWT)

    Path Parameters:
        - jobId (str): Scan job identifier

    Response (HTTP 200):
        - status: RUNNING | DONE | PARCIAL | FAILED
        - empresasTotal: total companies in scan
        - completados: count of completed companies
        - omitidos: count of skipped companies
        - fallidos: count of failed companies
        - startedAt: ISO timestamp when scan started
        - canStop: true if status in [DONE, PARCIAL, FAILED], false if RUNNING
        - pendingCompanies: list of pending companyIds (only when status is PARCIAL)

    Error Responses:
        - HTTP 404: Job not found or not authorized

    Logic:
    1. Fetch ScanJob by jobId
    2. 404 if not found
    3. 404 if userId set and differs from requesting user (Req 15.3)
    4. If userId not set → any authenticated user can view (Req 15.4)
    5. Zombie detection: RUNNING + elapsed > 600s → PARCIAL (Req 14.1)
    6. Auto-DONE: RUNNING + empresasCompletadas >= empresasTotal → DONE
    7. Build response with counts and canStop flag (Req 15.5-15.8)
    8. If PARCIAL: include pending companyIds (Req 15.6)

    Requirements: 14.1, 14.2, 14.3, 15.1-15.8
    """
    logger.info(
        "get_scan_job_start",
        context={"job_id": job_id, "user_id": user_id},
    )

    # Fetch ScanJob from DynamoDB
    dynamodb = _get_dynamodb_client()
    scan_jobs_table = dynamodb.Table(TABLES["scan_jobs"])

    response = scan_jobs_table.get_item(Key={"scanJobId": job_id})

    if "Item" not in response:
        logger.warning(
            "get_scan_job_not_found",
            context={"job_id": job_id},
        )
        raise HTTPException(status_code=404, detail="Scan job not found")

    scan_job = response["Item"]

    # Requirement 15.3: 404 if userId is set and doesn't match requesting user
    # Requirement 15.4: If userId not set → any authenticated user can view
    scan_job_user_id = scan_job.get("userId")
    if scan_job_user_id and scan_job_user_id != user_id:
        logger.warning(
            "get_scan_job_unauthorized",
            context={"job_id": job_id, "user_id": user_id},
        )
        raise HTTPException(status_code=404, detail="Scan job not found")

    # Parse fields from DynamoDB item
    status = scan_job.get("status", "RUNNING")
    empresas_total = int(scan_job.get("empresasTotal", 0))
    empresas_completadas = scan_job.get("empresasCompletadas") or []
    empresas_omitidas = scan_job.get("empresasOmitidas") or []
    empresas_fallidas = scan_job.get("empresasFallidas") or []
    started_at = scan_job.get("startedAt", "")

    # Normalize to sets/lists for consistent handling
    if isinstance(empresas_completadas, set):
        empresas_completadas = empresas_completadas
    else:
        empresas_completadas = set(empresas_completadas)

    if isinstance(empresas_fallidas, set):
        empresas_fallidas = empresas_fallidas
    else:
        empresas_fallidas = set(empresas_fallidas)

    if isinstance(empresas_omitidas, set):
        empresas_omitidas = list(empresas_omitidas)

    # Requirement 14.1: Zombie detection
    # RUNNING + elapsed > 600s → PARCIAL
    if status == "RUNNING":
        now = datetime.now(timezone.utc)
        if started_at:
            if isinstance(started_at, str):
                started_at_dt = datetime.fromisoformat(
                    started_at.replace("Z", "+00:00")
                )
            else:
                started_at_dt = started_at

            elapsed = (now - started_at_dt).total_seconds()

            if elapsed > ZOMBIE_THRESHOLD_SECONDS:
                status = "PARCIAL"
                scan_jobs_table.update_item(
                    Key={"scanJobId": job_id},
                    UpdateExpression="SET #s = :status, updatedAt = :now",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":status": "PARCIAL",
                        ":now": now.isoformat().replace("+00:00", "Z"),
                    },
                )
                logger.info(
                    "get_scan_job_zombie_detected",
                    context={
                        "job_id": job_id,
                        "elapsed_seconds": elapsed,
                    },
                )

    # Auto-DONE: RUNNING + completadas >= empresasTotal → DONE
    if status == "RUNNING":
        if empresas_total > 0 and len(empresas_completadas) >= empresas_total:
            status = "DONE"
            now = datetime.now(timezone.utc)
            scan_jobs_table.update_item(
                Key={"scanJobId": job_id},
                UpdateExpression="SET #s = :status, updatedAt = :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":status": "DONE",
                    ":now": now.isoformat().replace("+00:00", "Z"),
                },
            )
            logger.info(
                "get_scan_job_auto_done",
                context={
                    "job_id": job_id,
                    "empresas_completadas": len(empresas_completadas),
                    "empresas_total": empresas_total,
                },
            )

    # Build response (Requirement 15.5-15.8)
    can_stop = status in ("DONE", "PARCIAL", "FAILED")

    result = ScanJobStatusResponse(
        status=status,
        empresasTotal=empresas_total,
        completados=len(empresas_completadas),
        omitidos=len(empresas_omitidas),
        fallidos=len(empresas_fallidas),
        startedAt=started_at if isinstance(started_at, str) else started_at.isoformat(),
        canStop=can_stop,
    )

    # Requirement 15.6: If PARCIAL → include pending companyIds
    if status == "PARCIAL":
        all_accounted = empresas_completadas | set(empresas_omitidas)
        # Pending companies are those in empresasFallidas that aren't in completadas,
        # plus any companies that haven't reported at all.
        # Since empresasFallidas from worker are also in completadas (worker ADDs to both),
        # the truly "pending" (never reported) are those not in completadas nor omitidas.
        # Without storing the original list, fallidas not in completadas = stuck.
        pending = list(empresas_fallidas - empresas_completadas)
        result.pendingCompanies = pending

    logger.info(
        "get_scan_job_success",
        context={
            "job_id": job_id,
            "status": status,
            "can_stop": can_stop,
        },
    )

    return result
