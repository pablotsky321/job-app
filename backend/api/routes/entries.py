"""
Entries (question bank and interview notes) endpoints.

Provides:
- GET /me/vacancies/{companyId}/{vacancyId}/entries: List entries for a vacancy
- POST /me/vacancies/{companyId}/{vacancyId}/entries: Create a new entry
- POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer: Generate suggested answer

Requirements: 6.1-6.11, 9.1-9.4, 10.1-10.4, 11.1-11.4
"""

import os
from datetime import datetime

from ulid import ULID
from fastapi import APIRouter, Depends
from pydantic import ValidationError as PydanticValidationError

from backend.shared.logging_config import get_contextual_logger
from backend.shared.errors import AppException
from backend.shared.db import query_by_pk, put_item
from backend.shared.bedrock import get_bedrock_client
from backend.shared.normalization import detect_language
from backend.shared.models import SuggestedAnswerOutput
from backend.api.models.requests import CreateEntryRequest
from backend.api.routes.auth import get_current_user_id

logger = get_contextual_logger(__name__)

entries_router = APIRouter(prefix="/me/vacancies", tags=["entries"])


# ============================================================================
# GET /me/vacancies/{companyId}/{vacancyId}/entries
# ============================================================================


@entries_router.get("/{companyId}/{vacancyId}/entries")
async def list_entries(
    companyId: str,
    vacancyId: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    List all entries (questions/notes) for a specific vacancy.

    Returns entries ordered by createdAt ascending.
    Returns HTTP 200 with empty list when there are none.
    Returns HTTP 404 if UsuarioVacante or Vacante don't exist.

    Requirements: 6.1, 6.2, 6.3
    """
    logger.info(
        "list_entries_start",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId},
    )

    # Verify UsuarioVacante exists
    sk_value = f"{companyId}#{vacancyId}"
    uv_items = query_by_pk(
        "usuario_vacante", "userId", user_id, sk_name="sk", sk_value=sk_value
    )
    if not uv_items:
        raise AppException(
            error_code="not_found",
            message="User-vacancy relationship not found",
            http_status=404,
        )

    # Verify Vacante exists
    vacante_items = query_by_pk(
        "vacantes", "companyId", companyId, sk_name="vacancyId", sk_value=vacancyId
    )
    if not vacante_items:
        raise AppException(
            error_code="not_found",
            message="Vacancy not found",
            http_status=404,
        )

    # Query entries by pk
    pk_value = f"{user_id}#{companyId}#{vacancyId}"
    entries = query_by_pk("entradas", "pk", pk_value, limit=1000)

    # Sort by createdAt ascending
    entries.sort(key=lambda e: e.get("createdAt", ""))

    logger.info(
        "list_entries_success",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId, "count": len(entries)},
    )

    return {"entries": entries}


# ============================================================================
# POST /me/vacancies/{companyId}/{vacancyId}/entries
# ============================================================================


@entries_router.post("/{companyId}/{vacancyId}/entries", status_code=201)
async def create_entry(
    companyId: str,
    vacancyId: str,
    body: CreateEntryRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Create a new entry (question or interview note) for a vacancy.

    Validates tipo is one of 'preguntas' or 'nota_entrevista'.
    Returns HTTP 404 if UsuarioVacante or Vacante don't exist.
    The service NEVER exposes update or delete operations on Entrada.

    Requirements: 6.4, 6.5, 6.6
    """
    logger.info(
        "create_entry_start",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId, "tipo": body.tipo},
    )

    # Validate tipo
    valid_tipos = ("preguntas", "nota_entrevista")
    if body.tipo not in valid_tipos:
        raise AppException(
            error_code="validation_error",
            message=f"tipo must be one of: {', '.join(valid_tipos)}",
            http_status=400,
        )

    # Verify UsuarioVacante exists
    sk_value = f"{companyId}#{vacancyId}"
    uv_items = query_by_pk(
        "usuario_vacante", "userId", user_id, sk_name="sk", sk_value=sk_value
    )
    if not uv_items:
        raise AppException(
            error_code="not_found",
            message="User-vacancy relationship not found",
            http_status=404,
        )

    # Verify Vacante exists
    vacante_items = query_by_pk(
        "vacantes", "companyId", companyId, sk_name="vacancyId", sk_value=vacancyId
    )
    if not vacante_items:
        raise AppException(
            error_code="not_found",
            message="Vacancy not found",
            http_status=404,
        )

    # Create the Entrada
    pk_value = f"{user_id}#{companyId}#{vacancyId}"
    entry_id = str(ULID())
    now_iso = datetime.utcnow().isoformat()

    entry_item = {
        "pk": pk_value,
        "entryId": entry_id,
        "tipo": body.tipo,
        "contenido": body.contenido,
        "createdAt": now_iso,
    }
    put_item("entradas", entry_item)

    logger.info(
        "create_entry_success",
        context={"user_id": user_id, "entry_id": entry_id, "tipo": body.tipo},
    )

    return entry_item


# ============================================================================
# POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer
# ============================================================================


@entries_router.post("/{companyId}/{vacancyId}/entries/{entryId}/answer", status_code=201)
async def generate_answer(
    companyId: str,
    vacancyId: str,
    entryId: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Generate a suggested answer for an interview question entry.

    - Reads the referenced Entrada → HTTP 404 if not found or doesn't belong to this user/vacancy
    - HTTP 400 if Entrada.tipo != 'preguntas'
    - HTTP 409 if Vacante.cerrada == True
    - Detects language, invokes Bedrock, validates output
    - On success: creates a NEW append-only Entrada with tipo=nota_entrevista
    - NEVER modifies the referenced Entrada

    Requirements: 6.7, 6.8, 6.9, 6.10, 6.11
    """
    logger.info(
        "generate_answer_start",
        context={"user_id": user_id, "company_id": companyId, "vacancy_id": vacancyId, "entry_id": entryId},
    )

    # Read the referenced Entrada
    pk_value = f"{user_id}#{companyId}#{vacancyId}"
    entry_items = query_by_pk(
        "entradas", "pk", pk_value, sk_name="entryId", sk_value=entryId
    )
    if not entry_items:
        raise AppException(
            error_code="not_found",
            message="Entry not found",
            http_status=404,
        )

    entrada = entry_items[0]

    # Validate tipo == 'preguntas'
    if entrada.get("tipo") != "preguntas":
        raise AppException(
            error_code="validation_error",
            message="Only entries with tipo='preguntas' can generate answers",
            http_status=400,
        )

    # Check Vacante.cerrada
    vacante_items = query_by_pk(
        "vacantes", "companyId", companyId, sk_name="vacancyId", sk_value=vacancyId
    )
    if not vacante_items:
        raise AppException(
            error_code="not_found",
            message="Vacancy not found",
            http_status=404,
        )

    vacante = vacante_items[0]
    if vacante.get("cerrada", False):
        raise AppException(
            error_code="conflict",
            message="Cannot generate answers for a closed vacancy",
            http_status=409,
        )

    # Get user profile for resumenParaMatching
    perfil_items = query_by_pk("perfiles", "userId", user_id, limit=1)
    resumen = ""
    if perfil_items:
        resumen = perfil_items[0].get("resumenParaMatching", "") or ""

    # Detect language
    pregunta = entrada.get("contenido", "")
    vacante_titulo = vacante.get("titulo", "")
    vacante_descripcion = vacante.get("descripcion", "")
    idioma = detect_language(vacante_titulo, vacante_descripcion)

    # Build prompt
    prompt = _build_answer_prompt(pregunta, resumen, vacante_titulo, vacante_descripcion, idioma)

    # Invoke Bedrock
    model_id = os.getenv("BEDROCK_MODEL_SMALL", "")

    try:
        bedrock_client = get_bedrock_client()
        result = bedrock_client.invoke_with_retry(
            prompt=prompt,
            response_model=SuggestedAnswerOutput,
            model_id=model_id,
        )
    except PydanticValidationError:
        logger.error(
            "generate_answer_validation_failed",
            context={"user_id": user_id, "entry_id": entryId},
        )
        raise AppException(
            error_code="validation_error",
            message="AI failed to produce a valid answer after retry.",
            http_status=400,
        )
    except Exception as e:
        logger.error(
            "generate_answer_bedrock_failed",
            context={"user_id": user_id, "entry_id": entryId, "error_type": type(e).__name__},
        )
        raise AppException(
            error_code="ai_service_unavailable",
            message="AI service unavailable during answer generation.",
            http_status=502,
        )

    # Create a NEW append-only Entrada with the answer
    contenido_respuesta = f"{pregunta}\n\nRespuesta sugerida:\n{result.respuesta}"
    new_entry_id = str(ULID())
    now_iso = datetime.utcnow().isoformat()

    new_entry_item = {
        "pk": pk_value,
        "entryId": new_entry_id,
        "tipo": "nota_entrevista",
        "contenido": contenido_respuesta,
        "createdAt": now_iso,
    }
    put_item("entradas", new_entry_item)

    logger.info(
        "generate_answer_success",
        context={"user_id": user_id, "entry_id": entryId, "new_entry_id": new_entry_id},
    )

    return new_entry_item


# ============================================================================
# Helper functions
# ============================================================================


def _build_answer_prompt(
    pregunta: str,
    resumen_perfil: str,
    vacante_titulo: str,
    vacante_descripcion: str,
    idioma: str,
) -> str:
    """Build the Bedrock prompt for generating a suggested interview answer."""
    idioma_instruction = "Respond in Spanish." if idioma == "es" else "Respond in English."

    prompt = (
        f"You are a career coach helping a candidate prepare for a job interview.\n"
        f"{idioma_instruction}\n\n"
        f"The candidate's profile summary:\n{resumen_perfil}\n\n"
        f"The job posting:\n"
        f"Title: {vacante_titulo}\n"
        f"Description: {vacante_descripcion}\n\n"
        f"Interview question:\n{pregunta}\n\n"
        f"Generate a suggested answer that:\n"
        f"- Is tailored to the candidate's experience and the job requirements\n"
        f"- Is concise but comprehensive\n"
        f"- Highlights relevant skills and experience from the candidate's profile\n"
        f"- Sounds natural and professional\n\n"
        f"Return ONLY a JSON object with this field:\n"
        f'- respuesta: The suggested answer text (non-empty string)\n\n'
        f"Respond with ONLY the JSON object, no additional text."
    )
    return prompt
