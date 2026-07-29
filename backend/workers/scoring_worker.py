"""
Scoring_Worker Lambda — SQS_Scoring consumer.

Standalone Lambda triggered by SQS_Scoring queue. One message per (userId, vacancyId) pair.
Applies Prefiltro_Cargos, invokes Bedrock_Client for scoring, persists UsuarioVacante.

IDEMPOTENT: scoreProfileVersion check prevents redundant scoring (Requirement 13.6).
NEVER logs raw LLM response, CV text, or scoreDetalle content (resumen/coincidencias/faltantes).
Only logs: score number, veredicto string.

Reserved concurrency: 3 (enforced via Terraform, not code).

Requirements: 13, 16, 17, 21
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

from pydantic import ValidationError

from backend.shared.bedrock import get_bedrock_client
from backend.shared.db import get_dynamodb_table
from backend.shared.logging_config import get_contextual_logger, RequestContext
from backend.shared.models import (
    ScoringMessage,
    ScoringResult,
    UsuarioVacante,
)
from backend.shared.prefiltro_cargos import pasa_prefiltro_cargos

logger = get_contextual_logger(__name__)


# ============================================================================
# SCORING PROMPT BUILDER
# ============================================================================


def _build_scoring_prompt(
    titulo: str,
    descripcion: str,
    requisitos: list,
    resumen_para_matching: str,
    cargos_activos: list,
) -> str:
    """
    Build the scoring prompt for Bedrock_Client.

    Includes vacancy details and user profile summary.
    """
    requisitos_text = "\n".join(f"- {r}" for r in requisitos) if requisitos else "No especificados"
    cargos_text = ", ".join(cargos_activos) if cargos_activos else "No especificados"

    prompt = f"""Eres un evaluador experto de compatibilidad laboral. Analiza el perfil del candidato
contra la vacante y genera un score de match.

## Vacante
- Título: {titulo}
- Descripción: {descripcion}
- Requisitos:
{requisitos_text}

## Perfil del candidato
- Cargos activos buscados: {cargos_text}
- Resumen profesional:
{resumen_para_matching}

## Instrucciones
Evalúa la compatibilidad del candidato con la vacante y responde ÚNICAMENTE con un JSON válido:

{{
  "score": <int 0-100>,
  "veredicto": "<excelente|buen_encaje|parcial|bajo>",
  "coincidencias": ["<skill/requisito que coincide>", ...],
  "faltantes": ["<skill/requisito que falta>", ...],
  "resumen": "<breve explicación del match en 1-2 oraciones>"
}}

Criterios de veredicto:
- excelente: score >= 80
- buen_encaje: score 60-79
- parcial: score 40-59
- bajo: score < 40

Responde SOLO con el JSON, sin texto adicional."""

    return prompt


# ============================================================================
# DDB HELPERS (thin wrappers for table access)
# ============================================================================


def _get_perfil(user_id: str) -> Dict[str, Any]:
    """Fetch user profile from Perfiles table."""
    table = get_dynamodb_table("DYNAMODB_TABLE_PERFILES")
    response = table.get_item(Key={"userId": user_id})
    return response.get("Item")


def _get_vacante(vacancy_id: str) -> Dict[str, Any]:
    """Fetch vacancy from Vacantes table."""
    table = get_dynamodb_table("DYNAMODB_TABLE_VACANTES")
    response = table.get_item(Key={"vacanteSha256": vacancy_id})
    return response.get("Item")


def _get_usuario_vacante(user_id: str, vacancy_id: str) -> Dict[str, Any]:
    """Fetch existing UsuarioVacante record."""
    table = get_dynamodb_table("DYNAMODB_TABLE_USUARIO_VACANTE")
    response = table.get_item(Key={"userId": user_id, "vacancyId": vacancy_id})
    return response.get("Item")


def _put_usuario_vacante(item: Dict[str, Any]) -> None:
    """Persist UsuarioVacante record."""
    table = get_dynamodb_table("DYNAMODB_TABLE_USUARIO_VACANTE")
    table.put_item(Item=item)


# ============================================================================
# MAIN HANDLER
# ============================================================================


def handler(event: Dict[str, Any], context: Any) -> None:
    """
    Lambda entry point for Scoring_Worker.

    Processes SQS_Scoring messages. Each message contains (userId, vacancyId).

    Flow per message:
    1. Extract userId, vacancyId from ScoringMessage
    2. Fetch Perfil, check scoreProfileVersion vs profileVersion (idempotence)
    3. If already scored at current version → skip
    4. Fetch Vacante
    5. Apply pasa_prefiltro_cargos
    6. If filtered → persist UsuarioVacante with estado='filtered_out'
    7. If passes → invoke Bedrock with scoring prompt
    8. Validate response against ScoringResult
    9. On success → persist UsuarioVacante with score, scoreDetalle, estado='scored'

    Requirements: 13.6-13.8, 16.1-16.7, 17.1-17.5, 21.2, 21.4
    """
    for record in event["Records"]:
        _process_scoring_record(record)


def _process_scoring_record(record: Dict[str, Any]) -> None:
    """Process a single SQS_Scoring record."""
    body = json.loads(record["body"])
    msg = ScoringMessage(**body)
    user_id = msg.userId
    vacancy_id = msg.vacancyId

    with RequestContext(
        request_id=record.get("messageId", "unknown"),
        user_id=user_id,
    ):
        logger.info("scoring_worker_start", context={
            "userId": user_id,
            "vacancyId": vacancy_id,
        })

        try:
            # Step 1: Fetch Perfil
            perfil = _get_perfil(user_id)
            if not perfil:
                logger.error("scoring_perfil_not_found", context={
                    "userId": user_id,
                    "vacancyId": vacancy_id,
                })
                raise ValueError(f"Perfil not found for userId={user_id}")

            profile_version = perfil.get("profileVersion", 0)
            cargos_activos = perfil.get("cargosActivos", [])
            resumen_para_matching = perfil.get("resumenParaMatching", "") or ""

            # Step 2: Idempotence check (Requirement 13.6)
            existing_uv = _get_usuario_vacante(user_id, vacancy_id)
            if existing_uv:
                existing_score_version = existing_uv.get("scoreProfileVersion")
                if existing_score_version == profile_version:
                    logger.info("scoring_skipped_current_version", context={
                        "userId": user_id,
                        "vacancyId": vacancy_id,
                        "scoreProfileVersion": existing_score_version,
                    })
                    return  # Skip — already scored at this profile version

            # Step 3: Fetch Vacante
            vacante = _get_vacante(vacancy_id)
            if not vacante:
                logger.error("scoring_vacante_not_found", context={
                    "userId": user_id,
                    "vacancyId": vacancy_id,
                })
                raise ValueError(f"Vacante not found for vacancyId={vacancy_id}")

            titulo = vacante.get("titulo", "")
            descripcion = vacante.get("descripcion", "")
            requisitos = vacante.get("requisitos", [])

            # Step 4: Prefiltro_Cargos (Requirement 16)
            if not pasa_prefiltro_cargos(titulo, cargos_activos):
                # Filtered out — persist estado='filtered_out'
                now = datetime.now(timezone.utc).isoformat()
                _put_usuario_vacante({
                    "userId": user_id,
                    "vacancyId": vacancy_id,
                    "estado": "filtered_out",
                    "updatedAt": now,
                })
                logger.info("scoring_filtered_by_prefiltro", context={
                    "userId": user_id,
                    "vacancyId": vacancy_id,
                })
                return

            # Step 5: Build scoring prompt and invoke Bedrock
            prompt = _build_scoring_prompt(
                titulo=titulo,
                descripcion=descripcion,
                requisitos=requisitos,
                resumen_para_matching=resumen_para_matching,
                cargos_activos=cargos_activos,
            )

            bedrock_client = get_bedrock_client()
            model_id = os.getenv("BEDROCK_MODEL_MID")

            # Use invoke_with_retry which handles validation retry internally
            scoring_result = bedrock_client.invoke_with_retry(
                prompt=prompt,
                response_model=ScoringResult,
                model_id=model_id,
                max_retries=1,
            )

            # Step 6: Persist scored UsuarioVacante (Requirement 17.5)
            now = datetime.now(timezone.utc).isoformat()
            _put_usuario_vacante({
                "userId": user_id,
                "vacancyId": vacancy_id,
                "score": scoring_result.score,
                "scoreDetalle": scoring_result.model_dump(),
                "scoreProfileVersion": profile_version,
                "estado": "scored",
                "updatedAt": now,
            })

            # Log only score and veredicto (Requirement 21.4)
            logger.info("scoring_complete", context={
                "userId": user_id,
                "vacancyId": vacancy_id,
                "score": scoring_result.score,
                "veredicto": scoring_result.veredicto,
            })

        except ValidationError as ve:
            # Both attempts failed validation (Requirement 17.3, 17.4)
            # Log error without raw response
            logger.error("scoring_validation_failed_final", context={
                "userId": user_id,
                "vacancyId": vacancy_id,
                "error": str(ve)[:200],
            })
            # Raise to trigger SQS retry
            raise

        except Exception as e:
            logger.error("scoring_worker_error", context={
                "userId": user_id,
                "vacancyId": vacancy_id,
                "error": str(e)[:200],
            })
            # Raise to trigger SQS retry
            raise
