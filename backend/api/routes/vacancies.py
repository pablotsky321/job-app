"""
Vacancy management endpoints.

Provides:
- GET /me/vacancies: List user's vacancies (activas or aplicadas)
- GET /me/vacancies/{companyId}/{vacancyId}: Vacancy detail
- POST /me/vacancies/manual: Register a manual vacancy
- POST /me/vacancies/{companyId}/{vacancyId}/apply: Mark as applied
- POST /me/vacancies/{companyId}/{vacancyId}/cv: Generate ATS-optimized CV

Requirements: 1.1-1.11, 2.1-2.6, 3.1-3.12, 5.1-5.7, 9.1-9.4, 10.1-10.4, 11.1-11.4
"""

import hashlib
import json
import os
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from backend.shared.logging_config import get_contextual_logger
from backend.shared.errors import AppException
from backend.shared.db import query_by_pk, put_item, update_item, scan_all_items, _get_dynamodb_client, TABLES
from backend.shared.extraction import normalize_url, compute_vacancyId
from backend.shared.bedrock import get_bedrock_client
from backend.shared.normalization import detect_language
from backend.shared.models import BedRockExtractVacancyOutput, CVATSOutput, ScoringMessage
from backend.shared.rescoring import enqueue_rescore
from backend.shared.services.vacancy_service import build_vacancy_listing
from backend.api.models.requests import ManualVacancyRequest
from backend.api.routes.auth import get_current_user_id

logger = get_contextual_logger(__name__)

router = APIRouter(prefix="/me/vacancies", tags=["vacancies"])


# ============================================================================
# Response Models
# ============================================================================


class EmpresaSummary(BaseModel):
    """Company summary included in vacancy listing."""

    nombre: str
    plataforma: str


class VacanteInfo(BaseModel):
    """Vacancy info included in listing."""

    titulo: Optional[str] = None
    modalidad: Optional[str] = None
    ubicacion: Optional[str] = None
    url: Optional[str] = None
    lastSeenAt: Optional[str] = None
    empresa_nombre: Optional[str] = None
    empresa_plataforma: Optional[str] = None


class VacancyListItem(BaseModel):
    """Single item in vacancy listing response."""

    userId: str
    companyId: str
    vacancyId: str
    estado: str
    score: Optional[int] = None
    scoreProfileVersion: Optional[int] = None
    appliedAt: Optional[str] = None
    createdAt: Optional[str] = None
    staleFlag: bool
    vacante: VacanteInfo


class VacancyListResponse(BaseModel):
    """Response for GET /me/vacancies."""

    vacancies: List[VacancyListItem]


class VacancyDetailResponse(BaseModel):
    """Response for GET /me/vacancies/{companyId}/{vacancyId}."""

    # Vacancy fields
    titulo: str
    descripcion: str
    modalidad: str
    ubicacion: str
    url: str
    lastSeenAt: Optional[str] = None
    cerrada: bool = False
    # Empresa summary
    empresa: EmpresaSummary
    # UsuarioVacante fields
    estado: str
    score: Optional[int] = None
    scoreDetalle: Optional[dict] = None
    scoreProfileVersion: Optional[int] = None
    cvAtsTexto: Optional[str] = None
    cvGeneratedAt: Optional[str] = None
    appliedAt: Optional[str] = None
    createdAt: Optional[str] = None


# ============================================================================
# GET /me/vacancies/{companyId}/{vacancyId} - Vacancy detail
# ============================================================================


@router.get("/{companyId}/{vacancyId}", response_model=VacancyDetailResponse)
async def get_vacancy_detail(
    companyId: str,
    vacancyId: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get detailed information about a specific vacancy.

    Endpoint: GET /me/vacancies/{companyId}/{vacancyId}
    Auth: Required (JWT)

    Path Parameters:
        - companyId (str): Company identifier
        - vacancyId (str): Vacancy identifier

    Response (HTTP 200):
        - Combined data from Vacante, Empresa (nombre, plataforma), and UsuarioVacante

    Error Responses:
        - HTTP 401: Missing JWT claim
        - HTTP 404: Vacante, UsuarioVacante, or Empresa not found

    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 9.1, 9.2, 9.3, 9.4, 11.1, 11.2, 11.3
    """
    logger.info(
        "get_vacancy_detail_start",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId},
    )

    # Read Vacante by (companyId, vacancyId)
    vacante_items = query_by_pk(
        "vacantes", "companyId", companyId, sk_name="vacancyId", sk_value=vacancyId
    )
    if not vacante_items:
        logger.info(
            "get_vacancy_detail_not_found",
            context={"user_id": user_id, "reason": "vacante_missing"},
        )
        raise AppException(
            error_code="not_found",
            message="Vacancy not found",
            http_status=404,
        )

    # Read UsuarioVacante by (userId, {companyId}#{vacancyId})
    sk_value = f"{companyId}#{vacancyId}"
    uv_items = query_by_pk(
        "usuario_vacante", "userId", user_id, sk_name="sk", sk_value=sk_value
    )
    if not uv_items:
        logger.info(
            "get_vacancy_detail_not_found",
            context={"user_id": user_id, "reason": "usuario_vacante_missing"},
        )
        raise AppException(
            error_code="not_found",
            message="User-vacancy relationship not found",
            http_status=404,
        )

    # Read Empresa by companyId
    empresa_items = query_by_pk("empresas", "companyId", companyId)
    if not empresa_items:
        logger.info(
            "get_vacancy_detail_not_found",
            context={"user_id": user_id, "reason": "empresa_missing"},
        )
        raise AppException(
            error_code="not_found",
            message="Company not found",
            http_status=404,
        )

    vacante = vacante_items[0]
    usuario_vacante = uv_items[0]
    empresa = empresa_items[0]

    # Build response combining Vacante, EmpresaSummary, and UsuarioVacante
    response = VacancyDetailResponse(
        titulo=vacante.get("titulo", ""),
        descripcion=vacante.get("descripcion", ""),
        modalidad=vacante.get("modalidad", ""),
        ubicacion=vacante.get("ubicacion", ""),
        url=vacante.get("url", ""),
        lastSeenAt=vacante.get("lastSeenAt"),
        cerrada=vacante.get("cerrada", False),
        empresa=EmpresaSummary(
            nombre=empresa.get("nombre", ""),
            plataforma=empresa.get("plataforma", ""),
        ),
        estado=usuario_vacante.get("estado", ""),
        score=usuario_vacante.get("score"),
        scoreDetalle=usuario_vacante.get("scoreDetalle"),
        scoreProfileVersion=usuario_vacante.get("scoreProfileVersion"),
        cvAtsTexto=usuario_vacante.get("cvAtsTexto"),
        cvGeneratedAt=_to_str_or_none(usuario_vacante.get("cvGeneratedAt")),
        appliedAt=_to_str_or_none(usuario_vacante.get("appliedAt")),
        createdAt=_to_str_or_none(usuario_vacante.get("createdAt")),
    )

    logger.info(
        "get_vacancy_detail_success",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId},
    )

    return response


def _to_str_or_none(value) -> Optional[str]:
    """Convert a value to string or None. Handles datetime objects and strings."""
    if value is None:
        return None
    return str(value)


# ============================================================================
# GET /me/vacancies - List user's vacancies
# ============================================================================


@router.get("", response_model=VacancyListResponse)
async def list_user_vacancies(
    estado: Optional[str] = Query(default=None, description="Filter: activas or aplicadas"),
    user_id: str = Depends(get_current_user_id),
):
    """
    List user's vacancies filtered by estado.

    Endpoint: GET /me/vacancies
    Auth: Required (JWT)

    Query Parameters:
        - estado (str, optional): "activas" (default) or "aplicadas" (case-sensitive)

    Response (HTTP 200):
        - vacancies: List of vacancy records with staleness flags

    Error Responses:
        - HTTP 400: Invalid estado value
        - HTTP 401: Missing JWT claim

    Requirements: 1.1-1.11, 9.1-9.4, 11.1-11.3
    """
    # Apply default and validate estado parameter
    estado_filter = estado if estado is not None else "activas"

    if estado_filter not in ("activas", "aplicadas"):
        logger.warning(
            "list_vacancies_invalid_estado",
            context={"user_id": user_id, "estado": estado_filter},
        )
        raise AppException(
            error_code="validation_error",
            message=f"Invalid estado value: '{estado_filter}'. Must be 'activas' or 'aplicadas'.",
            http_status=400,
        )

    logger.info(
        "list_vacancies_start",
        context={"user_id": user_id, "estado": estado_filter},
    )

    # Query UsuarioVacante by userId (PK only, no GSI)
    usuario_vacantes = query_by_pk(
        "usuario_vacante", "userId", user_id, limit=1000
    )

    if not usuario_vacantes:
        logger.info(
            "list_vacancies_empty",
            context={"user_id": user_id, "estado": estado_filter, "count": 0},
        )
        return VacancyListResponse(vacancies=[])

    # Fetch user's profile version
    profile_version = _get_profile_version(user_id)

    # Build vacantes_by_id map from Vacante + Empresa data
    vacantes_by_id = _fetch_vacantes_and_empresas(usuario_vacantes)

    # Apply pure filter/sort/staleness logic
    listing = build_vacancy_listing(
        usuario_vacantes=usuario_vacantes,
        vacantes_by_id=vacantes_by_id,
        profile_version=profile_version,
        estado_filter=estado_filter,
    )

    # Enqueue rescore for stale records
    for record in listing:
        if record.get("staleFlag"):
            vacancy_id = record.get("vacancyId", "")
            try:
                enqueue_rescore(user_id, vacancy_id)
            except Exception as e:
                logger.warning(
                    "enqueue_rescore_failed",
                    context={
                        "user_id": user_id,
                        "vacancy_id": vacancy_id,
                        "error": str(e)[:200],
                    },
                )
                # Continue returning existing score with staleFlag=true

    logger.info(
        "list_vacancies_success",
        context={"user_id": user_id, "estado": estado_filter, "count": len(listing)},
    )

    return VacancyListResponse(vacancies=listing)


# ============================================================================
# Helper functions (I/O)
# ============================================================================


def _get_profile_version(user_id: str) -> Optional[int]:
    """Fetch user's profileVersion from Perfiles table."""
    try:
        items = query_by_pk("perfiles", "userId", user_id, limit=1)
        if items:
            return items[0].get("profileVersion")
        return None
    except Exception as e:
        logger.warning(
            "fetch_profile_version_failed",
            context={"user_id": user_id, "error": str(e)[:200]},
        )
        return None


def _fetch_vacantes_and_empresas(usuario_vacantes: list[dict]) -> dict:
    """
    Fetch Vacante and Empresa data for all UsuarioVacante records.

    Returns dict keyed by "{companyId}#{vacancyId}" with combined info.
    """
    dynamodb = _get_dynamodb_client()
    vacantes_table = dynamodb.Table(TABLES["vacantes"])
    empresas_table = dynamodb.Table(TABLES["empresas"])

    vacantes_by_id = {}
    empresas_cache: dict[str, dict] = {}

    for uv in usuario_vacantes:
        company_id = uv.get("companyId", "")
        vacancy_id = uv.get("vacancyId", "")
        sk = f"{company_id}#{vacancy_id}"

        if sk in vacantes_by_id:
            continue

        # Fetch Vacante
        vacante_data = {}
        try:
            response = vacantes_table.get_item(
                Key={"companyId": company_id, "vacancyId": vacancy_id}
            )
            if "Item" in response:
                item = response["Item"]
                vacante_data = {
                    "titulo": item.get("titulo", ""),
                    "modalidad": item.get("modalidad", ""),
                    "ubicacion": item.get("ubicacion", ""),
                    "url": item.get("url", ""),
                    "lastSeenAt": item.get("lastSeenAt", ""),
                }
        except Exception as e:
            logger.warning(
                "fetch_vacante_failed",
                context={"company_id": company_id, "vacancy_id": vacancy_id, "error": str(e)[:200]},
            )

        # Fetch Empresa (cached)
        if company_id not in empresas_cache:
            try:
                response = empresas_table.get_item(Key={"companyId": company_id})
                if "Item" in response:
                    empresas_cache[company_id] = response["Item"]
                else:
                    empresas_cache[company_id] = {}
            except Exception as e:
                logger.warning(
                    "fetch_empresa_failed",
                    context={"company_id": company_id, "error": str(e)[:200]},
                )
                empresas_cache[company_id] = {}

        empresa = empresas_cache.get(company_id, {})
        vacante_data["empresa_nombre"] = empresa.get("nombre", "")
        vacante_data["empresa_plataforma"] = empresa.get("plataforma", "")

        vacantes_by_id[sk] = vacante_data

    return vacantes_by_id


# ============================================================================
# Response Models for Manual Vacancy
# ============================================================================


class ApplyResponse(BaseModel):
    """Response for POST /me/vacancies/{companyId}/{vacancyId}/apply."""

    vacancyId: str
    companyId: str
    estado: str
    appliedAt: Optional[str] = None


class ManualVacancyResponse(BaseModel):
    """Response for POST /me/vacancies/manual."""

    vacancyId: str
    companyId: str
    titulo: str
    created: bool  # True if UsuarioVacante was newly created, False if already existed


# ============================================================================
# POST /me/vacancies/manual - Register a manual vacancy
# ============================================================================


@router.post("/manual", response_model=ManualVacancyResponse)
async def create_manual_vacancy(
    body: ManualVacancyRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Register a manual vacancy from pasted job posting text.

    Endpoint: POST /me/vacancies/manual
    Auth: Required (JWT)

    Request Body:
        - textoPegado (str): Pasted job posting text (1-20000 chars)
        - enlace (str): Job posting URL (absolute http/https)
        - nombreEmpresa (str): Company name (1-200 chars after trim)

    Processing:
        1. Validate input (URL format, company name length after trim)
        2. Resolve or create Empresa (never creates Suscripcion)
        3. Compute vacancyId from normalized URL hash
        4. If Vacante doesn't exist: invoke Bedrock to extract fields
        5. Create UsuarioVacante if not exists, publish ScoringMessage

    Response (HTTP 200):
        - vacancyId, companyId, titulo, created flag

    Error Responses:
        - HTTP 400: Invalid input or Bedrock extraction failure
        - HTTP 401: Missing JWT claim
        - HTTP 502: Bedrock invocation failed (timeout/exception)

    Requirements: 3.1-3.12, 9.1-9.4, 10.1-10.4, 11.1-11.4
    """
    logger.info(
        "manual_vacancy_start",
        context={"user_id": user_id},
    )

    # ---------------------------------------------------------------
    # Step 1: Validate input
    # ---------------------------------------------------------------
    nombre_empresa_trimmed = body.nombreEmpresa.strip()
    if len(nombre_empresa_trimmed) < 1 or len(nombre_empresa_trimmed) > 200:
        raise AppException(
            error_code="validation_error",
            message="nombreEmpresa must be between 1 and 200 characters after trimming whitespace.",
            http_status=400,
        )

    # Validate enlace is an absolute http/https URL
    parsed_url = urlparse(body.enlace)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        raise AppException(
            error_code="validation_error",
            message="enlace must be an absolute URL with http or https scheme.",
            http_status=400,
        )

    # ---------------------------------------------------------------
    # Step 2: Compute vacancyId
    # ---------------------------------------------------------------
    vacancy_id = compute_vacancyId(body.enlace)

    # ---------------------------------------------------------------
    # Step 3: Resolve Empresa
    # ---------------------------------------------------------------
    nombre_normalizado = nombre_empresa_trimmed.lower()
    company_id = _resolve_or_create_empresa(nombre_empresa_trimmed, nombre_normalizado)

    # ---------------------------------------------------------------
    # Step 4: Check if Vacante exists; if not, invoke Bedrock
    # ---------------------------------------------------------------
    dynamodb = _get_dynamodb_client()
    vacantes_table = dynamodb.Table(TABLES["vacantes"])

    vacante_exists = False
    vacante_titulo = ""

    try:
        response = vacantes_table.get_item(
            Key={"companyId": company_id, "vacancyId": vacancy_id}
        )
        if "Item" in response:
            vacante_exists = True
            vacante_titulo = response["Item"].get("titulo", "")
    except Exception as e:
        logger.error(
            "manual_vacancy_check_vacante_failed",
            context={"user_id": user_id, "error": str(e)[:200]},
        )
        raise AppException(
            error_code="internal_error",
            message="Failed to check existing vacancy.",
            http_status=500,
        )

    if not vacante_exists:
        # Invoke Bedrock to extract vacancy fields from pasted text
        extraction = _extract_vacancy_from_text(body.textoPegado, user_id)

        # Create the Vacante record
        now_iso = datetime.utcnow().isoformat()
        vacante_item = {
            "companyId": company_id,
            "vacancyId": vacancy_id,
            "vacanteSha256": vacancy_id,
            "titulo": extraction.titulo,
            "descripcion": extraction.descripcion,
            "modalidad": extraction.modalidad,
            "ubicacion": extraction.ubicacion,
            "url": body.enlace,
            "plataforma": "manual",
            "origen": "manual",
            "cerrada": False,
            "crawledAt": now_iso,
            "missCount": 0,
            "requisitos": [],
        }
        put_item("vacantes", vacante_item)
        vacante_titulo = extraction.titulo

        logger.info(
            "manual_vacancy_vacante_created",
            context={"user_id": user_id, "vacancy_id": vacancy_id},
        )
    else:
        logger.info(
            "manual_vacancy_vacante_reused",
            context={"user_id": user_id, "vacancy_id": vacancy_id},
        )

    # ---------------------------------------------------------------
    # Step 5: Check if UsuarioVacante exists; if not, create + publish SQS
    # ---------------------------------------------------------------
    sk_value = f"{company_id}#{vacancy_id}"
    uv_items = query_by_pk(
        "usuario_vacante", "userId", user_id, sk_name="sk", sk_value=sk_value
    )

    if uv_items:
        # Already exists - return 200 without creating duplicate or publishing SQS
        logger.info(
            "manual_vacancy_uv_already_exists",
            context={"user_id": user_id, "vacancy_id": vacancy_id},
        )
        return ManualVacancyResponse(
            vacancyId=vacancy_id,
            companyId=company_id,
            titulo=vacante_titulo,
            created=False,
        )

    # Create UsuarioVacante
    now_iso = datetime.utcnow().isoformat()
    uv_item = {
        "userId": user_id,
        "sk": sk_value,
        "companyId": company_id,
        "vacancyId": vacancy_id,
        "estado": "nueva",
        "score": None,
        "scoreDetalle": None,
        "scoreProfileVersion": None,
        "cvAtsTexto": None,
        "cvGeneratedAt": None,
        "appliedAt": None,
        "createdAt": now_iso,
        "updatedAt": now_iso,
    }
    put_item("usuario_vacante", uv_item)

    logger.info(
        "manual_vacancy_uv_created",
        context={"user_id": user_id, "vacancy_id": vacancy_id},
    )

    # Publish exactly one ScoringMessage to SQS scoring queue
    _publish_scoring_message(user_id, vacancy_id)

    logger.info(
        "manual_vacancy_success",
        context={"user_id": user_id, "vacancy_id": vacancy_id},
    )

    return ManualVacancyResponse(
        vacancyId=vacancy_id,
        companyId=company_id,
        titulo=vacante_titulo,
        created=True,
    )


# ============================================================================
# Helper functions for Manual Vacancy
# ============================================================================


def _resolve_or_create_empresa(nombre_display: str, nombre_normalizado: str) -> str:
    """
    Resolve existing Empresa by normalized name or create a new one.

    Scans empresas table and compares normalized names. If found, reuses the
    existing companyId. If not found, creates new Empresa with plataforma=manual.

    NEVER creates or modifies a Suscripcion.

    Args:
        nombre_display: Display name (trimmed, original casing)
        nombre_normalizado: Normalized name (trimmed + lowercased)

    Returns:
        companyId (str): The resolved or newly created company ID
    """
    # Scan all empresas to find by normalized name
    all_empresas = scan_all_items("empresas")

    for empresa in all_empresas:
        existing_nombre = empresa.get("nombre", "")
        if existing_nombre.strip().lower() == nombre_normalizado:
            return empresa.get("companyId", "")

    # Not found - create new Empresa
    # companyId for manual empresas: SHA-256 of the normalized name
    company_id = hashlib.sha256(nombre_normalizado.encode("utf-8")).hexdigest()

    now_iso = datetime.utcnow().isoformat()
    empresa_item = {
        "companyId": company_id,
        "nombre": nombre_display,
        "careersUrl": "",
        "plataforma": "manual",
        "lastScannedAt": None,
        "lastScanStatus": None,
        "lastVacancyCount": 0,
        "consecutiveFailures": 0,
        "boardToken": None,
        "ultimoOrigenExitoso": None,
        "createdAt": now_iso,
    }
    put_item("empresas", empresa_item)

    logger.info(
        "manual_vacancy_empresa_created",
        context={"company_id": company_id},
    )

    return company_id


def _extract_vacancy_from_text(texto_pegado: str, user_id: str) -> BedRockExtractVacancyOutput:
    """
    Invoke Bedrock to extract vacancy fields from pasted text.

    Uses invoke_with_retry which handles one retry with error injection.
    On second validation failure, raises HTTP 400.
    On invocation failure (timeout/exception), raises HTTP 502.

    Args:
        texto_pegado: The pasted job posting text
        user_id: For logging purposes only

    Returns:
        Validated BedRockExtractVacancyOutput

    Raises:
        AppException: HTTP 400 if validation fails after retry
        AppException: HTTP 502 if Bedrock invocation fails
    """
    model_id = os.getenv("BEDROCK_MODEL_SMALL", "")

    prompt = (
        "You are a job posting parser. Extract the following fields from the job posting text below.\n"
        "Return ONLY a JSON object with these fields:\n"
        "- titulo: The job title (required, non-empty string)\n"
        "- descripcion: A summary of the job description and responsibilities (required, non-empty string)\n"
        "- modalidad: One of 'remote', 'hybrid', 'onsite', or 'sin_dato' if not specified\n"
        "- ubicacion: The job location, or empty string if not specified\n\n"
        "Job posting text:\n"
        f"{texto_pegado}\n\n"
        "Respond with ONLY the JSON object, no additional text."
    )

    try:
        bedrock_client = get_bedrock_client()
        result = bedrock_client.invoke_with_retry(
            prompt=prompt,
            response_model=BedRockExtractVacancyOutput,
            model_id=model_id,
        )
        return result
    except Exception as e:
        error_type = type(e).__name__
        # Distinguish validation errors from invocation errors
        from pydantic import ValidationError as PydanticValidationError
        if isinstance(e, PydanticValidationError):
            logger.error(
                "manual_vacancy_bedrock_validation_failed",
                context={"user_id": user_id, "model_id": model_id, "error_type": error_type},
            )
            raise AppException(
                error_code="validation_error",
                message="AI extraction failed to produce valid output after retry.",
                http_status=400,
            )
        else:
            logger.error(
                "manual_vacancy_bedrock_invocation_failed",
                context={"user_id": user_id, "model_id": model_id, "error_type": error_type},
            )
            raise AppException(
                error_code="ai_service_unavailable",
                message="AI service unavailable during vacancy extraction.",
                http_status=502,
            )


def _publish_scoring_message(user_id: str, vacancy_id: str) -> None:
    """
    Publish exactly one ScoringMessage to SQS scoring queue.

    Uses same pattern as enqueue_rescore in rescoring.py.

    Args:
        user_id: User ID from JWT
        vacancy_id: Vacancy ID (SHA-256 hash)
    """
    import boto3

    queue_url = os.environ.get("SQS_QUEUE_SCORING_URL", "")

    if not queue_url:
        logger.error(
            "manual_vacancy_sqs_publish_failed",
            context={"user_id": user_id, "vacancy_id": vacancy_id, "error": "SQS_QUEUE_SCORING_URL not set"},
        )
        return

    message = ScoringMessage(userId=user_id, vacancyId=vacancy_id)

    try:
        sqs_client = boto3.client("sqs")
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=message.model_dump_json(),
        )
        logger.info(
            "manual_vacancy_scoring_message_published",
            context={"user_id": user_id, "vacancy_id": vacancy_id},
        )
    except Exception as e:
        logger.error(
            "manual_vacancy_sqs_publish_failed",
            context={"user_id": user_id, "vacancy_id": vacancy_id, "error": str(e)[:200]},
        )


# ============================================================================
# POST /me/vacancies/{companyId}/{vacancyId}/apply - Mark vacancy as applied
# ============================================================================


@router.post("/{companyId}/{vacancyId}/apply", response_model=ApplyResponse)
async def apply_to_vacancy(
    companyId: str,
    vacancyId: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Mark a vacancy as applied for the authenticated user.

    Endpoint: POST /me/vacancies/{companyId}/{vacancyId}/apply
    Auth: Required (JWT)

    Path Parameters:
        - companyId (str): Company identifier
        - vacancyId (str): Vacancy identifier

    Processing:
        - If UsuarioVacante.estado is already 'aplicada', returns HTTP 200
          without modifying appliedAt (idempotent).
        - If estado is not 'aplicada', sets estado='aplicada' and
          appliedAt=now(), then updates in DynamoDB.
        - Behavior is identical regardless of Vacante.estado (abierta or cerrada).

    Response (HTTP 200):
        - vacancyId, companyId, estado, appliedAt

    Error Responses:
        - HTTP 401: Missing JWT claim
        - HTTP 404: UsuarioVacante not found for (userId, companyId, vacancyId)

    Requirements: 4.1, 4.2, 4.3, 9.1, 9.2, 9.3, 9.4, 11.1, 11.2, 11.3
    """
    logger.info(
        "apply_to_vacancy_start",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId},
    )

    # Read UsuarioVacante by (userId, {companyId}#{vacancyId})
    sk_value = f"{companyId}#{vacancyId}"
    uv_items = query_by_pk(
        "usuario_vacante", "userId", user_id, sk_name="sk", sk_value=sk_value
    )

    if not uv_items:
        logger.info(
            "apply_to_vacancy_not_found",
            context={"user_id": user_id, "reason": "usuario_vacante_missing"},
        )
        raise AppException(
            error_code="not_found",
            message="User-vacancy relationship not found",
            http_status=404,
        )

    usuario_vacante = uv_items[0]
    current_estado = usuario_vacante.get("estado", "")

    # If already aplicada, return 200 without modifying appliedAt (idempotent)
    if current_estado == "aplicada":
        logger.info(
            "apply_to_vacancy_already_applied",
            context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId},
        )
        return ApplyResponse(
            vacancyId=vacancyId,
            companyId=companyId,
            estado="aplicada",
            appliedAt=_to_str_or_none(usuario_vacante.get("appliedAt")),
        )

    # Set estado=aplicada and appliedAt=now()
    now_iso = datetime.utcnow().isoformat()
    update_item(
        "usuario_vacante",
        key={"userId": user_id, "sk": sk_value},
        updates={"estado": "aplicada", "appliedAt": now_iso, "updatedAt": now_iso},
    )

    logger.info(
        "apply_to_vacancy_success",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId},
    )

    return ApplyResponse(
        vacancyId=vacancyId,
        companyId=companyId,
        estado="aplicada",
        appliedAt=now_iso,
    )


# ============================================================================
# POST /me/vacancies/{companyId}/{vacancyId}/cv - Generate ATS-optimized CV
# ============================================================================


@router.post("/{companyId}/{vacancyId}/cv")
async def generate_cv_ats(
    companyId: str,
    vacancyId: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Generate an ATS-optimized CV text for a specific vacancy.

    Endpoint: POST /me/vacancies/{companyId}/{vacancyId}/cv
    Auth: Required (JWT)

    Path Parameters:
        - companyId (str): Company identifier
        - vacancyId (str): Vacancy identifier

    Processing:
        1. Verify UsuarioVacante exists (HTTP 404 if not)
        2. Check Vacante.cerrada (HTTP 409 if closed)
        3. Detect language from Vacante.titulo + descripcion
        4. Invoke Bedrock with profile + vacancy data
        5. Persist cvAtsTexto and cvGeneratedAt
        6. Return text/plain response

    Response (HTTP 200):
        - Plain text CV-ATS content (Content-Type: text/plain)

    Error Responses:
        - HTTP 401: Missing JWT claim
        - HTTP 404: UsuarioVacante not found
        - HTTP 400: Bedrock validation failed after retry
        - HTTP 409: Vacancy is closed
        - HTTP 502: Bedrock invocation failed

    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 9.1, 9.2, 9.3, 9.4,
                  10.1, 10.2, 10.3, 10.4, 11.1, 11.2, 11.3, 11.4
    """
    logger.info(
        "generate_cv_ats_start",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId},
    )

    # Step 1: Read UsuarioVacante — HTTP 404 if missing (BEFORE evaluating Vacante.estado)
    sk_value = f"{companyId}#{vacancyId}"
    uv_items = query_by_pk(
        "usuario_vacante", "userId", user_id, sk_name="sk", sk_value=sk_value
    )
    if not uv_items:
        logger.info(
            "generate_cv_ats_not_found",
            context={"user_id": user_id, "reason": "usuario_vacante_missing"},
        )
        raise AppException(
            error_code="not_found",
            message="User-vacancy relationship not found",
            http_status=404,
        )

    # Step 2: Read Vacante — check cerrada field → HTTP 409 if closed
    vacante_items = query_by_pk(
        "vacantes", "companyId", companyId, sk_name="vacancyId", sk_value=vacancyId
    )
    if not vacante_items:
        logger.info(
            "generate_cv_ats_not_found",
            context={"user_id": user_id, "reason": "vacante_missing"},
        )
        raise AppException(
            error_code="not_found",
            message="Vacancy not found",
            http_status=404,
        )

    vacante = vacante_items[0]

    if vacante.get("cerrada", False):
        logger.info(
            "generate_cv_ats_vacancy_closed",
            context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId},
        )
        raise AppException(
            error_code="vacancy_closed",
            message="Cannot generate CV for a closed vacancy",
            http_status=409,
        )

    # Step 3: Read Perfiles
    perfil_items = query_by_pk("perfiles", "userId", user_id, limit=1)
    if not perfil_items:
        logger.info(
            "generate_cv_ats_not_found",
            context={"user_id": user_id, "reason": "perfil_missing"},
        )
        raise AppException(
            error_code="not_found",
            message="User profile not found",
            http_status=404,
        )

    perfil = perfil_items[0]

    # Step 4: Detect language
    idioma = detect_language(
        vacante.get("titulo", ""),
        vacante.get("descripcion", ""),
    )

    # Step 5: Build prompt and invoke Bedrock
    cv_text = _invoke_bedrock_for_cv(
        perfil=perfil,
        vacante=vacante,
        idioma=idioma,
        user_id=user_id,
    )

    # Step 6: Persist cvAtsTexto and cvGeneratedAt
    now_iso = datetime.utcnow().isoformat()
    update_item(
        "usuario_vacante",
        key={"userId": user_id, "sk": sk_value},
        updates={
            "cvAtsTexto": cv_text,
            "cvGeneratedAt": now_iso,
            "updatedAt": now_iso,
        },
    )

    logger.info(
        "generate_cv_ats_success",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId},
    )

    # Step 7: Return plain text
    return PlainTextResponse(content=cv_text, status_code=200)


def _invoke_bedrock_for_cv(
    perfil: dict,
    vacante: dict,
    idioma: str,
    user_id: str,
) -> str:
    """
    Invoke Bedrock to generate ATS-optimized CV text.

    Uses BEDROCK_MODEL_MID for mid-tier generation.
    invoke_with_retry handles one retry with error injection on validation failure.

    Args:
        perfil: User profile dict from DynamoDB
        vacante: Vacancy dict from DynamoDB
        idioma: Detected language ("es" or "en")
        user_id: For logging only

    Returns:
        Generated CV text (validated, non-empty)

    Raises:
        AppException: HTTP 400 if validation fails after retry
        AppException: HTTP 502 if Bedrock invocation fails
    """
    model_id = os.getenv("BEDROCK_MODEL_MID", "")

    # Prepare profile data
    perfil_estructurado = perfil.get("perfilEstructurado", {})
    resumen_matching = perfil.get("resumenParaMatching", "")

    # Prepare vacancy data
    vacancy_info = {
        "titulo": vacante.get("titulo", ""),
        "descripcion": vacante.get("descripcion", ""),
        "requisitos": vacante.get("requisitos", []),
        "ubicacion": vacante.get("ubicacion", ""),
        "modalidad": vacante.get("modalidad", ""),
    }

    # Build language instruction
    if idioma == "en":
        lang_instruction = "Generate the CV text in ENGLISH."
    else:
        lang_instruction = "Generate the CV text in SPANISH."

    prompt = (
        "You are an expert career consultant specializing in ATS-optimized resumes.\n"
        "Generate a plain-text CV/resume optimized for Applicant Tracking Systems (ATS).\n\n"
        "RULES:\n"
        "- Output ONLY plain text. No tables, no columns, no markdown formatting.\n"
        "- Use keywords from the job posting to maximize ATS matching.\n"
        "- Be concise and keyword-rich.\n"
        "- Include relevant experience, skills, and education from the user's profile.\n"
        "- Tailor the CV specifically to this vacancy's requirements.\n"
        f"- {lang_instruction}\n\n"
        "USER PROFILE (structured):\n"
        f"{json.dumps(perfil_estructurado, ensure_ascii=False, default=str)}\n\n"
        "USER MATCHING SUMMARY:\n"
        f"{resumen_matching}\n\n"
        "VACANCY DETAILS:\n"
        f"{json.dumps(vacancy_info, ensure_ascii=False)}\n\n"
        "Respond with ONLY a JSON object: {\"texto\": \"<the full ATS CV text>\"}\n"
        "The 'texto' field must contain the complete CV text as a single string."
    )

    try:
        bedrock_client = get_bedrock_client()
        result = bedrock_client.invoke_with_retry(
            prompt=prompt,
            response_model=CVATSOutput,
            model_id=model_id,
        )
        return result.texto
    except Exception as e:
        error_type = type(e).__name__
        from pydantic import ValidationError as PydanticValidationError

        if isinstance(e, PydanticValidationError):
            logger.error(
                "generate_cv_ats_bedrock_validation_failed",
                context={"user_id": user_id, "model_id": model_id, "error_type": error_type},
            )
            raise AppException(
                error_code="validation_error",
                message="AI CV generation failed to produce valid output after retry.",
                http_status=400,
            )
        else:
            logger.error(
                "generate_cv_ats_bedrock_invocation_failed",
                context={"user_id": user_id, "model_id": model_id, "error_type": error_type},
            )
            raise AppException(
                error_code="ai_service_unavailable",
                message="AI service unavailable during CV generation.",
                http_status=502,
            )
