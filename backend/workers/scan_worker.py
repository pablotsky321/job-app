"""
Scan_Worker Lambda — SQS_Scan consumer.

Standalone Lambda (NOT part of the FastAPI monolith). Triggered by SQS_Scan.
Processes one Empresa per SQS message:
  1. Execute cascada_descubrimiento(empresa)
  2. Classify result via classify_scan_result
  3. Update Empresa counters (consecutiveFailures, lastVacancyCount, ultimoOrigenExitoso)
  4. If OK: apply missCount logic, upsert Vacantes, fan-out ScoringMessages
  5. ADD companyId to ScanJob.empresasCompletadas (idempotent String Set)
  6. If FAILED/EMPTY_SOSPECHOSO: also ADD to empresasFallidas

IDEMPOTENCY: SQS delivers at-least-once. All state mutations use:
  - DynamoDB ADD for String Sets (empresasCompletadas, empresasFallidas)
  - Vacante keyed by vacancyId (SHA-256 dedup)
  - ScoringMessages re-delivered are handled by Scoring_Worker's profileVersion check

Requirements: 2, 6, 7, 12, 13
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Set

import boto3
from pydantic import BaseModel, ConfigDict, Field

from backend.shared.cascada_descubrimiento import cascada_descubrimiento
from backend.shared.extraction import VacancyExtracted, compute_vacancyId
from backend.shared.logging_config import get_contextual_logger, RequestContext
from backend.shared.misscount_logic import apply_missCount_logic
from backend.shared.models import Empresa, Vacante
from backend.shared.scan_classification import classify_scan_result

logger = get_contextual_logger(__name__)

# Environment variables
SQS_QUEUE_SCORING_URL = os.environ.get("SQS_QUEUE_SCORING_URL", "")
DYNAMODB_TABLE_EMPRESAS = os.environ.get("DYNAMODB_TABLE_EMPRESAS", "")
DYNAMODB_TABLE_VACANTES = os.environ.get("DYNAMODB_TABLE_VACANTES", "")
DYNAMODB_TABLE_SUSCRIPCIONES = os.environ.get("DYNAMODB_TABLE_SUSCRIPCIONES", "")
DYNAMODB_TABLE_SCAN_JOBS = os.environ.get("DYNAMODB_TABLE_SCAN_JOBS", "")


# ============================================================================
# SQS MESSAGE MODEL
# ============================================================================


class ScanMessage(BaseModel):
    """Message payload from SQS_Scan queue.

    Published by Orquestador, consumed by Scan_Worker.
    Requirement 12.1: One message per Empresa to scan.
    """

    jobId: str = Field(..., description="ScanJob ID")
    companyId: str = Field(..., description="SHA-256 hash of careers URL (64 hex chars)")

    model_config = ConfigDict(extra="ignore")


class ScoringMessage(BaseModel):
    """Message payload for SQS_Scoring queue.

    Published by Scan_Worker, consumed by Scoring_Worker.
    Requirement 12.4: One message per (userId, vacancyId) pair for NEW vacancies.
    """

    userId: str = Field(..., description="User ID (from JWT sub claim)")
    vacancyId: str = Field(..., description="Vacante ID (SHA-256 of normalized URL)")

    model_config = ConfigDict(extra="ignore")


# ============================================================================
# AWS CLIENT HELPERS (lazy-initialized)
# ============================================================================

_dynamodb_resource = None
_sqs_client = None


def _get_dynamodb():
    """Get or initialize DynamoDB resource."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb")
    return _dynamodb_resource


def _get_sqs():
    """Get or initialize SQS client."""
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client("sqs")
    return _sqs_client


# ============================================================================
# DYNAMODB OPERATIONS
# ============================================================================


def _get_empresa(company_id: str) -> Empresa:
    """Fetch Empresa record from DynamoDB."""
    dynamodb = _get_dynamodb()
    table = dynamodb.Table(DYNAMODB_TABLE_EMPRESAS)
    response = table.get_item(Key={"companyId": company_id})
    item = response.get("Item")
    if not item:
        raise ValueError(f"Empresa not found: {company_id}")
    return Empresa(**item)


def _get_existing_vacantes(company_id: str) -> List[Vacante]:
    """Fetch all existing vacantes for a company."""
    dynamodb = _get_dynamodb()
    table = dynamodb.Table(DYNAMODB_TABLE_VACANTES)

    items = []
    response = table.query(
        IndexName="companyId-index",
        KeyConditionExpression="companyId = :cid",
        ExpressionAttributeValues={":cid": company_id},
    )
    items.extend(response.get("Items", []))

    # Handle pagination
    while "LastEvaluatedKey" in response:
        response = table.query(
            IndexName="companyId-index",
            KeyConditionExpression="companyId = :cid",
            ExpressionAttributeValues={":cid": company_id},
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    return [Vacante(**item) for item in items]


def _update_empresa_ok(empresa: Empresa, num_vacantes: int, origen: str) -> None:
    """Update Empresa after OK classification (Req 6.9)."""
    dynamodb = _get_dynamodb()
    table = dynamodb.Table(DYNAMODB_TABLE_EMPRESAS)
    now = datetime.utcnow().isoformat()

    table.update_item(
        Key={"companyId": empresa.companyId},
        UpdateExpression=(
            "SET consecutiveFailures = :zero, "
            "lastVacancyCount = :count, "
            "ultimoOrigenExitoso = :origen, "
            "lastScannedAt = :now, "
            "lastScanStatus = :status"
        ),
        ExpressionAttributeValues={
            ":zero": 0,
            ":count": num_vacantes,
            ":origen": origen,
            ":now": now,
            ":status": "OK",
        },
    )


def _update_empresa_empty_legitimo(empresa: Empresa, origen: str) -> None:
    """Update Empresa after EMPTY_LEGITIMO classification (Req 6.9)."""
    dynamodb = _get_dynamodb()
    table = dynamodb.Table(DYNAMODB_TABLE_EMPRESAS)
    now = datetime.utcnow().isoformat()

    table.update_item(
        Key={"companyId": empresa.companyId},
        UpdateExpression=(
            "SET consecutiveFailures = :zero, "
            "lastVacancyCount = :count, "
            "ultimoOrigenExitoso = :origen, "
            "lastScannedAt = :now, "
            "lastScanStatus = :status"
        ),
        ExpressionAttributeValues={
            ":zero": 0,
            ":count": 0,
            ":origen": origen,
            ":now": now,
            ":status": "EMPTY_LEGITIMO",
        },
    )


def _update_empresa_failed(empresa: Empresa, status: str) -> None:
    """Update Empresa after FAILED or EMPTY_SOSPECHOSO classification (Req 6.7)."""
    dynamodb = _get_dynamodb()
    table = dynamodb.Table(DYNAMODB_TABLE_EMPRESAS)
    now = datetime.utcnow().isoformat()

    table.update_item(
        Key={"companyId": empresa.companyId},
        UpdateExpression=(
            "SET consecutiveFailures = consecutiveFailures + :one, "
            "lastScannedAt = :now, "
            "lastScanStatus = :status"
        ),
        ExpressionAttributeValues={
            ":one": 1,
            ":now": now,
            ":status": status,
        },
    )


def _upsert_vacantes(vacantes: List[Vacante]) -> None:
    """Batch upsert Vacante records to DynamoDB."""
    dynamodb = _get_dynamodb()
    table = dynamodb.Table(DYNAMODB_TABLE_VACANTES)

    for vacante in vacantes:
        item = vacante.model_dump()
        # Convert datetime fields to ISO string for DynamoDB
        for field_name in ["crawledAt", "verificadaAt"]:
            if item.get(field_name) and isinstance(item[field_name], datetime):
                item[field_name] = item[field_name].isoformat()
        table.put_item(Item=item)


def _get_active_subscriptions(company_id: str) -> List[Dict[str, Any]]:
    """Query active Suscripciones for a company (activa=true)."""
    dynamodb = _get_dynamodb()
    table = dynamodb.Table(DYNAMODB_TABLE_SUSCRIPCIONES)

    items = []
    response = table.query(
        IndexName="companyId-index",
        KeyConditionExpression="companyId = :cid",
        FilterExpression="activa = :active",
        ExpressionAttributeValues={
            ":cid": company_id,
            ":active": True,
        },
    )
    items.extend(response.get("Items", []))

    while "LastEvaluatedKey" in response:
        response = table.query(
            IndexName="companyId-index",
            KeyConditionExpression="companyId = :cid",
            FilterExpression="activa = :active",
            ExpressionAttributeValues={
                ":cid": company_id,
                ":active": True,
            },
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    return items


def _add_to_scan_job_completadas(job_id: str, company_id: str) -> None:
    """ADD companyId to ScanJob.empresasCompletadas (String Set, idempotent).

    Requirement 12.2: ADD operation is idempotent — safe for SQS redelivery.
    """
    dynamodb = _get_dynamodb()
    table = dynamodb.Table(DYNAMODB_TABLE_SCAN_JOBS)
    now = datetime.utcnow().isoformat()

    table.update_item(
        Key={"scanJobId": job_id},
        UpdateExpression="ADD empresasCompletadas :cid SET updatedAt = :now",
        ExpressionAttributeValues={
            ":cid": {company_id},
            ":now": now,
        },
    )


def _add_to_scan_job_fallidas(job_id: str, company_id: str) -> None:
    """ADD companyId to ScanJob.empresasFallidas (String Set, idempotent).

    Requirement 12.3: Also ADD for FAILED/EMPTY_SOSPECHOSO classifications.
    """
    dynamodb = _get_dynamodb()
    table = dynamodb.Table(DYNAMODB_TABLE_SCAN_JOBS)
    now = datetime.utcnow().isoformat()

    table.update_item(
        Key={"scanJobId": job_id},
        UpdateExpression="ADD empresasFallidas :cid SET updatedAt = :now",
        ExpressionAttributeValues={
            ":cid": {company_id},
            ":now": now,
        },
    )


# ============================================================================
# SQS SCORING FAN-OUT
# ============================================================================


def _enqueue_scoring_messages(
    user_ids: List[str],
    new_vacancy_ids: List[str],
) -> None:
    """Publish ScoringMessages to SQS_Scoring for new vacancies.

    Requirement 12.4: One message per (userId, vacancyId) pair.
    Requirement 12.5: If ANY enqueue fails, abort to allow SQS retry.

    Uses batch send (max 10 per batch) for efficiency.
    """
    sqs = _get_sqs()

    messages = []
    for user_id in user_ids:
        for vacancy_id in new_vacancy_ids:
            msg = ScoringMessage(userId=user_id, vacancyId=vacancy_id)
            messages.append(msg)

    # Send in batches of 10 (SQS limit)
    batch_size = 10
    for i in range(0, len(messages), batch_size):
        batch = messages[i : i + batch_size]
        entries = []
        for idx, msg in enumerate(batch):
            entries.append(
                {
                    "Id": str(i + idx),
                    "MessageBody": msg.model_dump_json(),
                }
            )

        response = sqs.send_message_batch(
            QueueUrl=SQS_QUEUE_SCORING_URL,
            Entries=entries,
        )

        # Requirement 12.5: If any message fails, raise to abort processing
        failed = response.get("Failed", [])
        if failed:
            failed_ids = [f["Id"] for f in failed]
            raise RuntimeError(
                f"Failed to enqueue {len(failed)} scoring messages: {failed_ids}"
            )


# ============================================================================
# CORE PROCESSING LOGIC
# ============================================================================


def _identify_new_vacancy_ids(
    vacantes_after_misscount: List[Vacante],
    existing_vacancy_ids: Set[str],
) -> List[str]:
    """Identify vacancies that are genuinely NEW (not previously existing).

    A vacancy is NEW if its vacancyId was not in the existing set before this scan.
    These are the only vacancies that trigger ScoringMessages.
    """
    return [
        v.vacanteSha256
        for v in vacantes_after_misscount
        if v.vacanteSha256 not in existing_vacancy_ids
    ]


def _process_single_message(job_id: str, company_id: str) -> None:
    """Process a single SQS_Scan message for one Empresa.

    This is the core logic, extracted for testability and clarity.
    Requirement 12.1: Exactly one Empresa per message.
    """
    # 1. Fetch Empresa
    empresa = _get_empresa(company_id)

    logger.info(
        "scan_worker_start",
        context={
            "jobId": job_id,
            "companyId": company_id,
            "plataforma": empresa.plataforma.value,
        },
    )

    # 2. Execute cascada
    vacantes_list, origen, error = cascada_descubrimiento(empresa)

    # 3. Classify result
    extraction_result = (vacantes_list, origen, error)
    classification = classify_scan_result(empresa, extraction_result)

    logger.info(
        "scan_worker_classified",
        context={
            "jobId": job_id,
            "companyId": company_id,
            "classification": classification,
            "vacancyCount": len(vacantes_list) if vacantes_list else 0,
            "origen": origen,
        },
    )

    # 4. Route by classification
    if classification == "OK":
        _handle_ok(job_id, company_id, empresa, vacantes_list, origen)
    elif classification == "EMPTY_LEGITIMO":
        _handle_empty_legitimo(job_id, company_id, empresa, origen)
    elif classification in ("FAILED", "EMPTY_SOSPECHOSO"):
        _handle_failed_or_sospechoso(job_id, company_id, empresa, classification)
    else:
        # Should never happen — classify_scan_result is exhaustive
        raise ValueError(f"Unknown classification: {classification}")


def _handle_ok(
    job_id: str,
    company_id: str,
    empresa: Empresa,
    vacantes_list: List[VacancyExtracted],
    origen: str,
) -> None:
    """Handle OK classification: missCount, upsert, fan-out scoring.

    Requirements: 6.9, 7.1-7.7, 12.2, 12.4
    """
    # Get existing vacancies for this company
    existing_vacantes = _get_existing_vacantes(company_id)
    existing_vacancy_ids = {v.vacanteSha256 for v in existing_vacantes}

    # Apply missCount logic (Requirement 7)
    updated_vacantes = apply_missCount_logic(
        empresa=empresa,
        vacantes_nuevas_en_escan=vacantes_list,
        vacantes_existentes=existing_vacantes,
        origen=origen,
    )

    # Upsert all vacantes to DynamoDB
    _upsert_vacantes(updated_vacantes)

    # Identify NEW vacancies (for scoring fan-out)
    new_vacancy_ids = _identify_new_vacancy_ids(updated_vacantes, existing_vacancy_ids)

    # Fan-out scoring messages for new vacancies (Requirement 12.4)
    if new_vacancy_ids:
        subscriptions = _get_active_subscriptions(company_id)
        user_ids = [sub["userId"] for sub in subscriptions]

        if user_ids:
            # Requirement 12.5: If enqueue fails, raise (no ADD to completadas)
            _enqueue_scoring_messages(user_ids, new_vacancy_ids)

    # Update Empresa counters (Requirement 6.9)
    _update_empresa_ok(empresa, len(vacantes_list), origen)

    # ADD to empresasCompletadas (Requirement 12.2, idempotent)
    _add_to_scan_job_completadas(job_id, company_id)

    logger.info(
        "scan_worker_ok_complete",
        context={
            "jobId": job_id,
            "companyId": company_id,
            "vacanciesUpserted": len(updated_vacantes),
            "newVacancies": len(new_vacancy_ids),
        },
    )


def _handle_empty_legitimo(
    job_id: str,
    company_id: str,
    empresa: Empresa,
    origen: str,
) -> None:
    """Handle EMPTY_LEGITIMO: reset counters, no vacancy changes.

    Requirement 6.9: consecutiveFailures=0, lastVacancyCount=0
    Requirement 2.10: update ultimoOrigenExitoso
    """
    _update_empresa_empty_legitimo(empresa, origen)
    _add_to_scan_job_completadas(job_id, company_id)

    logger.info(
        "scan_worker_empty_legitimo_complete",
        context={
            "jobId": job_id,
            "companyId": company_id,
        },
    )


def _handle_failed_or_sospechoso(
    job_id: str,
    company_id: str,
    empresa: Empresa,
    classification: str,
) -> None:
    """Handle FAILED or EMPTY_SOSPECHOSO: increment failures, no vacancy changes.

    CRITICAL (pitfalls.md): EMPTY_SOSPECHOSO does NOT touch existing vacancies.
    Requirement 6.7: consecutiveFailures += 1
    Requirement 12.3: ADD to empresasFallidas
    """
    _update_empresa_failed(empresa, classification)

    # ADD to both completadas AND fallidas (Requirements 12.2, 12.3)
    _add_to_scan_job_completadas(job_id, company_id)
    _add_to_scan_job_fallidas(job_id, company_id)

    logger.info(
        "scan_worker_failed_complete",
        context={
            "jobId": job_id,
            "companyId": company_id,
            "classification": classification,
        },
    )


# ============================================================================
# LAMBDA HANDLER
# ============================================================================


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda entry point for Scan_Worker (SQS_Scan consumer).

    Processes each SQS record sequentially. On any unhandled exception,
    the function raises so SQS retries the message (up to MaxReceiveCount=3).

    Args:
        event: SQS event with Records array
        context: Lambda context (requestId for tracing)

    Returns:
        Success response dict (statusCode 200)

    Raises:
        Exception: On processing failure (triggers SQS retry)
    """
    request_id = getattr(context, "aws_request_id", "unknown")

    with RequestContext(request_id=request_id):
        records = event.get("Records", [])
        logger.info(
            "scan_worker_invoked",
            context={"recordCount": len(records)},
        )

        for record in records:
            body = json.loads(record["body"])
            scan_message = ScanMessage(**body)

            _process_single_message(
                job_id=scan_message.jobId,
                company_id=scan_message.companyId,
            )

    return {"statusCode": 200, "body": "OK"}
