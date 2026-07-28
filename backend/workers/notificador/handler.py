"""
Notificador Lambda handler - triggered by DynamoDB Streams on ScanJobs table.

Detects programmed scan completion and sends email notifications to subscribed users
with qualified new vacancies.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 11.1, 11.2, 11.3, 11.4

IMPORTANT: DynamoDB Streams on ScanJobs table do NOT exist yet (infra gap).
This code can be implemented and unit-tested but has no trigger until the
infrastructure spec provisions it.
"""

import os
import json
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from backend.workers.notificador.qualification import (
    determine_qualified_vacancies,
    should_send_email,
)
from backend.workers.notificador.email_builder import build_notification_email
from backend.workers.notificador.ses_sender import send_notification_email


# Terminal statuses that trigger notification evaluation
TERMINAL_STATUSES = {"DONE", "PARCIAL", "FAILED"}


def handler(event: dict, context: Any) -> dict:
    """Lambda entry point for Notificador - triggered by DynamoDB Streams on ScanJobs."""
    _log_structured("INFO", "notificador_invoked", {
        "recordCount": len(event.get("Records", [])),
    })

    for record in event.get("Records", []):
        try:
            _process_stream_record(record)
        except Exception as e:
            # Per-record error isolation: log and continue
            _log_structured("ERROR", "record_processing_failed", {
                "error": str(e)[:500],
            })

    return {"statusCode": 200}


def _process_stream_record(record: dict) -> None:
    """Process a single DynamoDB Stream record."""
    # 11.1: Parse stream record
    parsed = _parse_stream_record(record)
    if parsed is None:
        return

    scan_job_id = parsed["scanJobId"]
    user_id = parsed["userId"]
    status = parsed["status"]
    empresas_completadas = parsed["empresasCompletadas"]
    started_at = parsed["startedAt"]

    # Skip manual scans (userId is not null)
    if user_id is not None:
        _log_structured("INFO", "skipping_manual_scan", {
            "scanJobId": scan_job_id,
        })
        return

    # Skip non-terminal transitions
    if status not in TERMINAL_STATUSES:
        _log_structured("INFO", "skipping_non_terminal_status", {
            "scanJobId": scan_job_id,
            "status": status,
        })
        return

    _log_structured("INFO", "processing_programmed_scan", {
        "scanJobId": scan_job_id,
        "status": status,
        "empresasCompletadasCount": len(empresas_completadas),
    })

    # 11.8: Resolve subscribed users for completed companies
    subscribed_users = _resolve_subscribed_users(empresas_completadas)

    if not subscribed_users:
        _log_structured("INFO", "no_subscribed_users_found", {
            "scanJobId": scan_job_id,
        })
        return

    # Process each unique user
    for target_user_id in subscribed_users:
        try:
            _process_user_notification(
                scan_job_id=scan_job_id,
                user_id=target_user_id,
                empresas_completadas=empresas_completadas,
                started_at=started_at,
            )
        except Exception as e:
            # Per-user error isolation: log and continue
            _log_structured("ERROR", "user_notification_failed", {
                "scanJobId": scan_job_id,
                "userId": target_user_id,
                "error": str(e)[:500],
            })


def _process_user_notification(
    scan_job_id: str,
    user_id: str,
    empresas_completadas: set[str],
    started_at: str,
) -> None:
    """Process notification for a single user."""
    # 11.7: Idempotency check — skip if already sent
    if _already_notified(scan_job_id, user_id):
        _log_structured("INFO", "notification_already_sent", {
            "scanJobId": scan_job_id,
            "userId": user_id,
        })
        return

    # 11.2: Determine qualified vacancies
    usuario_vacantes = _get_user_vacancies_with_details(user_id)
    qualified = determine_qualified_vacancies(
        usuario_vacantes=usuario_vacantes,
        empresas_completadas=empresas_completadas,
        started_at=started_at,
    )

    # Zero-vacancies guard
    if not should_send_email(qualified):
        _log_structured("INFO", "no_qualified_vacancies_for_user", {
            "scanJobId": scan_job_id,
            "userId": user_id,
        })
        return

    # 11.4: Build email
    user_display_data = _get_user_display_data(user_id)
    subject, body = build_notification_email(
        user_display_data=user_display_data,
        qualified_vacancies=qualified,
    )

    # 11.6: Send via SES
    recipient_email = user_display_data.get("email", "")
    if not recipient_email:
        _log_structured("WARNING", "user_email_not_found", {
            "scanJobId": scan_job_id,
            "userId": user_id,
        })
        return

    success = send_notification_email(
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        user_id=user_id,
        scan_job_id=scan_job_id,
    )

    # 11.7: Record notification sent (idempotency)
    if success:
        _mark_as_notified(scan_job_id, user_id)

    _log_structured("INFO", "user_notification_processed", {
        "scanJobId": scan_job_id,
        "userId": user_id,
        "vacantesCount": len(qualified),
        "emailSent": success,
    })


# ============================================================================
# 11.1: DynamoDB Stream record parsing
# ============================================================================


def _parse_stream_record(record: dict) -> Optional[dict]:
    """
    Parse a DynamoDB Stream record, extracting fields from NewImage.

    DynamoDB Streams records use type descriptors:
    - {"S": "value"} for strings
    - {"SS": ["val1", "val2"]} for string sets
    - {"NULL": True} for null values

    Returns None if the record cannot be parsed or is not relevant.
    """
    try:
        new_image = record.get("dynamodb", {}).get("NewImage")
        if not new_image:
            return None

        scan_job_id = _extract_s(new_image.get("jobId"))
        if not scan_job_id:
            return None

        status = _extract_s(new_image.get("status"))
        if not status:
            return None

        # userId can be null for programmed scans
        user_id = _extract_s(new_image.get("userId"))

        # empresasCompletadas is a StringSet (SS)
        empresas_completadas = _extract_ss(new_image.get("empresasCompletadas"))

        # startedAt is a string (ISO 8601)
        started_at = _extract_s(new_image.get("startedAt"))
        if not started_at:
            return None

        return {
            "scanJobId": scan_job_id,
            "userId": user_id,
            "status": status,
            "empresasCompletadas": empresas_completadas,
            "startedAt": started_at,
        }

    except (KeyError, TypeError, AttributeError) as e:
        _log_structured("WARNING", "stream_record_parse_error", {
            "error": str(e)[:500],
        })
        return None


def _extract_s(attr: Optional[dict]) -> Optional[str]:
    """Extract a string value from a DynamoDB type descriptor."""
    if attr is None:
        return None
    if "S" in attr:
        return attr["S"]
    if "NULL" in attr and attr["NULL"]:
        return None
    return None


def _extract_ss(attr: Optional[dict]) -> set[str]:
    """Extract a string set value from a DynamoDB type descriptor."""
    if attr is None:
        return set()
    if "SS" in attr:
        return set(attr["SS"])
    return set()


# ============================================================================
# DynamoDB access helpers (specific to Notificador)
# ============================================================================


def _get_dynamodb_resource():
    """Get DynamoDB resource."""
    return boto3.resource("dynamodb")


def _resolve_subscribed_users(empresas_completadas: set[str]) -> set[str]:
    """
    Find all users subscribed to completed companies via GSI porEmpresa.

    Returns deduplicated set of userIds.
    """
    dynamodb = _get_dynamodb_resource()
    table_name = os.environ.get("DYNAMODB_TABLE_SUSCRIPCIONES", "")
    table = dynamodb.Table(table_name)

    subscribed_users: set[str] = set()

    for company_id in empresas_completadas:
        try:
            response = table.query(
                IndexName="porEmpresa",
                KeyConditionExpression="companyId = :cid",
                FilterExpression="activa = :active",
                ExpressionAttributeValues={
                    ":cid": company_id,
                    ":active": True,
                },
            )
            for item in response.get("Items", []):
                user_id = item.get("userId")
                if user_id:
                    subscribed_users.add(user_id)
        except ClientError as e:
            _log_structured("ERROR", "subscriptions_query_failed", {
                "companyId": company_id,
                "error": str(e)[:500],
            })

    return subscribed_users


def _get_user_vacancies_with_details(user_id: str) -> list[dict]:
    """
    Get all UsuarioVacante records for a user, enriched with Vacante details.

    Queries UsuarioVacante by userId (PK), then fetches Vacante for each to get
    firstSeenAt, titulo, descripcion, etc.
    """
    dynamodb = _get_dynamodb_resource()

    # Query UsuarioVacante
    uv_table_name = os.environ.get("DYNAMODB_TABLE_USUARIO_VACANTE", "")
    uv_table = dynamodb.Table(uv_table_name)

    try:
        response = uv_table.query(
            KeyConditionExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )
        uv_items = response.get("Items", [])
    except ClientError as e:
        _log_structured("ERROR", "usuario_vacante_query_failed", {
            "userId": user_id,
            "error": str(e)[:500],
        })
        return []

    # Enrich with Vacante details
    vacantes_table_name = os.environ.get("DYNAMODB_TABLE_VACANTES", "")
    vacantes_table = dynamodb.Table(vacantes_table_name)

    empresas_table_name = os.environ.get("DYNAMODB_TABLE_EMPRESAS", "")
    empresas_table = dynamodb.Table(empresas_table_name)

    enriched = []
    for uv in uv_items:
        # Parse SK to get companyId and vacancyId
        sk = uv.get("sk", "")
        parts = sk.split("#", 1)
        if len(parts) != 2:
            continue
        company_id, vacancy_id = parts

        # Fetch Vacante
        try:
            vacante_resp = vacantes_table.get_item(
                Key={"companyId": company_id, "vacancyId": vacancy_id}
            )
            vacante = vacante_resp.get("Item", {})
        except ClientError:
            vacante = {}

        # Fetch Empresa name
        try:
            empresa_resp = empresas_table.get_item(
                Key={"companyId": company_id}
            )
            empresa = empresa_resp.get("Item", {})
        except ClientError:
            empresa = {}

        enriched.append({
            "userId": user_id,
            "companyId": company_id,
            "vacancyId": vacancy_id,
            "estado": uv.get("estado"),
            "score": uv.get("score"),
            "cvAtsTexto": uv.get("cvAtsTexto"),
            "firstSeenAt": vacante.get("firstSeenAt", ""),
            "titulo": vacante.get("titulo", ""),
            "descripcion": vacante.get("descripcion", ""),
            "url": vacante.get("url", ""),
            "plataforma": vacante.get("plataforma", ""),
            "ubicacion": vacante.get("ubicacion", ""),
            "modalidad": vacante.get("modalidad", "sin_dato"),
            "empresa_nombre": empresa.get("nombre", ""),
        })

    return enriched


def _get_user_display_data(user_id: str) -> dict:
    """
    Get user display data for email (nombre, email).

    Reads from Perfiles table. Email would come from Cognito in production,
    but for now we use a placeholder pattern.
    """
    dynamodb = _get_dynamodb_resource()
    perfiles_table_name = os.environ.get("DYNAMODB_TABLE_PERFILES", "")
    perfiles_table = dynamodb.Table(perfiles_table_name)

    try:
        response = perfiles_table.get_item(Key={"userId": user_id})
        perfil = response.get("Item", {})
        return {
            "nombre": perfil.get("nombre", "usuario"),
            "email": perfil.get("email", ""),
            "userId": user_id,
        }
    except ClientError as e:
        _log_structured("WARNING", "user_display_data_fetch_failed", {
            "userId": user_id,
            "error": str(e)[:500],
        })
        return {"nombre": "usuario", "email": "", "userId": user_id}


# ============================================================================
# 11.7: Idempotency via notificacionesEnviadas StringSet on ScanJob
# ============================================================================


def _already_notified(scan_job_id: str, user_id: str) -> bool:
    """
    Check if notification was already sent for (scanJobId, userId).

    Uses the notificacionesEnviadas StringSet on the ScanJob record.
    """
    dynamodb = _get_dynamodb_resource()
    table_name = os.environ.get("DYNAMODB_TABLE_SCAN_JOBS", "")
    table = dynamodb.Table(table_name)

    try:
        response = table.get_item(
            Key={"jobId": scan_job_id},
            ProjectionExpression="notificacionesEnviadas",
        )
        item = response.get("Item", {})
        notified_set = item.get("notificacionesEnviadas", set())

        # DynamoDB returns sets as Python sets when using resource API
        if isinstance(notified_set, set):
            return user_id in notified_set
        if isinstance(notified_set, list):
            return user_id in notified_set
        return False

    except ClientError as e:
        _log_structured("WARNING", "idempotency_check_failed", {
            "scanJobId": scan_job_id,
            "userId": user_id,
            "error": str(e)[:500],
        })
        # On failure, proceed with sending (better duplicate than lost notification)
        return False


def _mark_as_notified(scan_job_id: str, user_id: str) -> None:
    """
    Mark userId as notified for this scanJobId using ADD operation on StringSet.

    Uses DynamoDB ADD operation (String Set, never decremented) per tech rule 3.
    """
    dynamodb = _get_dynamodb_resource()
    table_name = os.environ.get("DYNAMODB_TABLE_SCAN_JOBS", "")
    table = dynamodb.Table(table_name)

    try:
        table.update_item(
            Key={"jobId": scan_job_id},
            UpdateExpression="ADD notificacionesEnviadas :uid",
            ExpressionAttributeValues={":uid": {user_id}},
        )
        _log_structured("INFO", "marked_as_notified", {
            "scanJobId": scan_job_id,
            "userId": user_id,
        })
    except ClientError as e:
        _log_structured("ERROR", "mark_notified_failed", {
            "scanJobId": scan_job_id,
            "userId": user_id,
            "error": str(e)[:500],
        })


# ============================================================================
# Structured logging
# ============================================================================


def _log_structured(level: str, message: str, context: dict) -> None:
    """Emit structured JSON log to stdout. Never includes sensitive content."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": level,
        "component": "Notificador_Lambda",
        "message": message,
        "context": context,
    }
    print(json.dumps(log_entry, default=str))
