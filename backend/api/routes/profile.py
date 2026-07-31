"""
Profile management endpoints.

Provides:
- POST /me/profile/parse: Parse CV text → PerfilEstructurado (Bedrock)
- GET /me/profile: Retrieve saved profile
- PUT /me/profile: Save structured profile
- POST /me/profile/roles/suggest: Suggest job roles from resumen (Bedrock)
- PUT /me/profile/roles: Save active roles

All endpoints requiring authentication extract userId from JWT via Depends(get_current_user_id).

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 11.1, 11.2, 11.3, 11.4, 11.5,
              12.1, 12.2, 12.3, 12.4, 12.5, 19.1, 19.2, 19.3, 19.4
"""

import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import boto3
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from backend.shared.logging_config import get_contextual_logger
from backend.shared.bedrock import get_bedrock_client
from backend.shared.validators import validate_cv_text
from backend.shared.errors import (
    ValidationError as ValidationErrorException,
    AIServiceUnavailable,
    CVTooLarge,
    ProfileNotFound,
    ResumeNotReady,
)
from backend.shared.models import (
    PerfilEstructurado,
    RolesSuggestions,
    ProfileResponse,
)
from backend.shared.db import (
    query_by_pk,
    put_item,
    update_item,
    get_dynamodb_table,
)
from backend.api.routes.auth import get_current_user_id
from backend.api.models.requests import ParseCVRequest, SaveProfileRequest, SetRolesRequest

# Initialize logger
logger = get_contextual_logger(__name__)

# Create router for profile endpoints
router = APIRouter(prefix="/me/profile", tags=["profile"])

# Create router for roles endpoints (separate prefix)
roles_router = APIRouter(prefix="/me/profile/roles", tags=["roles"])


# ============================================================================
# Shared helper: async resumenParaMatching generation trigger
# ============================================================================


def _trigger_async_resumen_generation(user_id: str) -> str:
    """
    Dispara la generación asíncrona de resumenParaMatching invocando la propia
    Lambda "api" con InvocationType='Event'.

    Garantía de no propagación de excepciones: TODO el cuerpo de esta función
    (tanto la escritura de resumenGenerationStatus='pending' como el intento de
    lambda.invoke) está envuelto en un único try/except externo. Ningún fallo en
    ningún paso de este helper puede propagarse al caller (save_profile /
    suggest_roles) ni romper su respuesta HTTP — ese caller ya completó su
    propio trabajo principal (guardar el perfil, o evaluar el bloqueo de
    roles/suggest) antes de invocar este helper, y ese trabajo principal nunca
    debe fallar por un problema en este flujo secundario de generación de
    resumen.

    Orden de escritura (crítico para evitar una carrera con el propio worker
    asíncrono, Requirement 2 Criterios 1, 2, 10):
    1. Escribe resumenGenerationStatus='pending' PRIMERO, antes de intentar
       cualquier invocación. Esto es necesario porque, una vez despachada la
       invocación asíncrona, esa Lambda separada puede completar (escribiendo
       'complete' o 'failed') en cualquier momento — incluso antes de que este
       helper termine de ejecutarse. Si este helper escribiera su propio status
       DESPUÉS de invocar, esa escritura tardía podría sobreescribir el
       resultado correcto del worker con 'pending', dejando al usuario
       atascado indefinidamente sin que ningún retry lo detecte (el status
       nunca quedaría en 'failed').
    2. Intenta lambda.invoke(). Si el despacho se completa sin excepción, no
       se requiere ninguna escritura adicional: el status ya quedó en
       'pending' en el paso 1, que es el valor correcto mientras la
       generación está en curso.
    3. Si CUALQUIER paso anterior (la escritura de 'pending' O el invoke) lanza
       una excepción, el except externo la captura, la loguea, e intenta una
       segunda escritura que sobreescribe el status a 'failed' (Requirement
       2.10) — en este punto se asume que la generación no quedará en curso,
       es un fallo confirmado, no un estado en progreso. Esa segunda escritura
       está a su vez envuelta en su propio try/except interno: si también
       falla (ej. la misma causa de throttling que afectó al paso 1), se
       loguea ese fallo secundario y la función retorna igualmente sin
       propagar ninguna excepción.

    Compartida entre:
    - save_profile (PUT /me/profile) — Requirement 2, Criterios 1, 2, 10
    - suggest_roles (POST /me/profile/roles/suggest) — Requirement 3, Criterio 7

    Args:
        user_id: userId extraído del JWT (nunca de body/query).

    Returns:
        El valor final conocido de resumenGenerationStatus tras esta función:
        'pending' si ambos pasos (escritura + invoke) tuvieron éxito; 'failed'
        si algún paso falló y la escritura de 'failed' tuvo éxito; 'unknown' si
        algún paso falló Y la propia escritura de 'failed' también falló. 'unknown'
        significa que esta función no pudo CONFIRMAR qué quedó persistido en
        DynamoDB tras el fallo — no implica necesariamente que el estado real sea
        indeterminado en la práctica. Por ejemplo, si el Paso 1 escribió 'pending'
        con éxito y solo la segunda escritura de 'failed' falló después, el valor
        realmente persistido en DynamoDB sigue siendo 'pending'; este helper
        simplemente no tiene forma de verificarlo en ese momento, de modo que
        reporta 'unknown' en vez de asumir cuál de los valores posibles quedó
        almacenado.
    """
    perfiles_table = get_dynamodb_table("DYNAMODB_TABLE_PERFILES")

    try:
        # Paso 1: 'pending' PRIMERO, antes de cualquier intento de invocar.
        perfiles_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET resumenGenerationStatus = :status",
            ExpressionAttributeValues={":status": "pending"},
        )

        # Paso 2: intentar el despacho asíncrono.
        lambda_client = boto3.client("lambda")
        lambda_client.invoke(
            FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
            InvocationType="Event",
            Payload=json.dumps(
                {"mode": "async_resumen_generation", "userId": user_id}
            ).encode("utf-8"),
        )
        logger.info(
            "async_resumen_dispatch_status",
            context={"user_id": user_id, "status": "pending"},
        )
        return "pending"

    except Exception as e:
        # Paso 3: algo del bloque anterior (escritura de 'pending' o invoke)
        # falló con certeza -> intentar sobreescribir a 'failed'.
        logger.error(
            "async_resumen_dispatch_failed",
            context={"user_id": user_id, "error_type": type(e).__name__},
        )
        try:
            perfiles_table.update_item(
                Key={"userId": user_id},
                UpdateExpression="SET resumenGenerationStatus = :status",
                ExpressionAttributeValues={":status": "failed"},
            )
            return "failed"
        except Exception as inner_e:
            # Incluso la escritura de 'failed' falló (ej. mismo throttling
            # sostenido). No se propaga: el caller nunca debe romper su
            # respuesta HTTP por este flujo secundario.
            logger.error(
                "async_resumen_failed_status_write_also_failed",
                context={"user_id": user_id, "error_type": type(inner_e).__name__},
            )
            return "unknown"


# ============================================================================
# Shared helper: pure decision function for POST /me/profile/roles/suggest
# ============================================================================


class RolesSuggestDecision(str, Enum):
    """Resultado de la decisión de bloqueo de POST /me/profile/roles/suggest.

    Requirement 3.4.
    """

    ALLOW = "allow"
    BLOCK = "block"
    BLOCK_AND_RETRY = "block_and_retry"


def decide_roles_suggest_action(
    resumen_para_matching: Optional[str],
    resumen_generation_status: Optional[str],
) -> RolesSuggestDecision:
    """
    Decide si POST /me/profile/roles/suggest debe permitir, bloquear, o bloquear
    Y disparar un retry de generación.

    Pura: no llama a DynamoDB ni a Bedrock. Requirement 3.4.

    Cubre exhaustivamente (Requirements 3.1, 3.2, 3.3, 3.6, 3.7):
        resumenParaMatching is not None                        → ALLOW
            (independientemente de resumenGenerationStatus: 'pending', 'failed',
             'complete', o None — Criterios 3.2, 3.3, 3.6)
        resumenParaMatching is None AND status == 'failed'     → BLOCK_AND_RETRY
        resumenParaMatching is None AND status != 'failed'     → BLOCK
            (incluye status is None — Criterio 3.1)

    Args:
        resumen_para_matching: Valor actual de Perfiles.resumenParaMatching
            (None si aún no se generó ningún resumen).
        resumen_generation_status: Valor actual de Perfiles.resumenGenerationStatus
            ('pending' | 'complete' | 'failed' | None).

    Returns:
        RolesSuggestDecision.ALLOW, .BLOCK, o .BLOCK_AND_RETRY según las reglas
        anteriores.
    """
    if resumen_para_matching is not None:
        return RolesSuggestDecision.ALLOW
    if resumen_generation_status == "failed":
        return RolesSuggestDecision.BLOCK_AND_RETRY
    return RolesSuggestDecision.BLOCK


# ============================================================================
# POST /me/profile/parse - Parse CV into Structured Profile
# ============================================================================


@router.post("/parse", response_model=PerfilEstructurado)
async def parse_cv(
    request: ParseCVRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Parse raw CV text into structured profile.

    Endpoint: POST /me/profile/parse
    Auth: Required (JWT)

    Request Body:
        - cvText (str): Raw CV text, max 50KB

    Response (HTTP 200):
        - PerfilEstructurado: Parsed and validated profile

    Error Responses:
        - HTTP 400: Validation error (invalid input, schema mismatch after retry)
        - HTTP 413: CV exceeds 50KB limit
        - HTTP 502: Bedrock timeout or service error

    Logic:
    1. Validate cvText (non-empty, <50KB)
    2. If invalid: Return HTTP 413 (if size) or HTTP 400 (if other)
    3. Invoke Bedrock SMALL model with CV parsing prompt
    4. Validate response against PerfilEstructurado schema
    5. If validation fails: Retry once with error injected into prompt
    6. If retry fails: Return HTTP 400 or HTTP 502 as appropriate
    7. Return parsed PerfilEstructurado (not persisted)
    8. Log attempt count, model used, success/failure status

    Requirements:
    - 1.1: Accept POST with cvText (≤50KB)
    - 1.2: Invoke Bedrock SMALL model from env var
    - 1.3: Validate response against PerfilEstructurado, retry once on failure
    - 1.4: Return HTTP 200 with PerfilEstructurado on success
    - 1.5: Return HTTP 413 on >50KB
    - 1.6: Return HTTP 502 on Bedrock timeout/failure
    - 1.7: Log model used, attempt count, status (no CV text content)
    """
    logger.info(
        "parse_cv_start",
        context={
            "user_id": user_id,
            "request_size_bytes": len(request.cvText.encode("utf-8")),
        },
    )

    # Step 1: Validate CV text size and content
    is_valid, error_msg = validate_cv_text(request.cvText)
    if not is_valid:
        if "exceeds" in error_msg:
            logger.warning(
                "parse_cv_validation_failed_size",
                context={
                    "user_id": user_id,
                    "reason": error_msg,
                },
            )
            raise CVTooLarge()
        else:
            logger.warning(
                "parse_cv_validation_failed",
                context={
                    "user_id": user_id,
                    "reason": error_msg,
                },
            )
            raise ValidationErrorException(
                message="CV text validation failed",
                details=error_msg,
            )

    # Step 2: Prepare prompt for Bedrock
    prompt = _prepare_cv_parsing_prompt(request.cvText)

    # Step 3: Invoke Bedrock with retry
    try:
        bedrock_client = get_bedrock_client()
        perfil = bedrock_client.invoke_with_retry(
            prompt=prompt,
            response_model=PerfilEstructurado,
            model_id=bedrock_client.model_small,
            max_retries=1,
        )

        logger.info(
            "parse_cv_success",
            context={
                "user_id": user_id,
                "model": bedrock_client.model_small,
                "num_experiences": len(perfil.experiencia),
                "num_educations": len(perfil.educacion),
                "num_skills": len(perfil.skills),
            },
        )

        return perfil

    except ValidationError as ve:
        # Bedrock validation failed even after retry
        logger.error(
            "parse_cv_validation_failed_bedrock",
            context={
                "user_id": user_id,
                "error": str(ve),
            },
        )
        raise AIServiceUnavailable(
            message="Failed to parse CV: validation error",
            details="Bedrock response did not match expected schema",
        )

    except Exception as e:
        # Bedrock invocation failed (timeout, service error, etc.)
        error_type = type(e).__name__
        logger.error(
            "parse_cv_bedrock_error",
            context={
                "user_id": user_id,
                "error_type": error_type,
                "error": str(e),
            },
        )
        raise AIServiceUnavailable(
            message="AI service failed to process CV",
            details=f"Bedrock invocation failed: {error_type}",
        )


# ============================================================================
# GET /me/profile - Retrieve Saved Profile
# ============================================================================


@router.get("", response_model=ProfileResponse)
async def get_profile(
    user_id: str = Depends(get_current_user_id),
):
    """
    Retrieve the user's saved profile.

    Endpoint: GET /me/profile
    Auth: Required (JWT)

    Response (HTTP 200):
        - perfilEstructurado: Structured profile
        - resumenParaMatching: Summary text for matching (or null)
        - cargosSugeridos: Suggested roles (or empty list)
        - cargosActivos: User-selected active roles (or empty list)
        - profileVersion: Version number
        - updatedAt: Timestamp of last update
        - resumenGenerating: Boolean flag (read-only from DB)

    Error Responses:
        - HTTP 404: Profile not found

    Logic:
    1. Query Perfiles table by userId (pk)
    2. If not found: Return HTTP 404 with profile_not_found
    3. Return all stored fields (including resumenGenerationStatus → resumenGenerating)
    4. Log retrieval status

    Requirements:
    - 2.1, 2.2: Query Perfiles by userId
    - 2.3: Return perfilEstructurado
    - 2.4: Return resumenParaMatching (may be null)
    - 2.5: Return cargosActivos, cargosSugeridos, profileVersion, updatedAt
    - 3.5: Return resumenGenerating (true if resumenGenerationStatus == 'pending', else false)
    - 3.7: Return 404 with profile_not_found if missing
    """
    logger.info(
        "get_profile_start",
        context={"user_id": user_id},
    )

    try:
        # Query DynamoDB Perfiles table by pk=userId
        perfiles_table = get_dynamodb_table("DYNAMODB_TABLE_PERFILES")
        
        response = perfiles_table.get_item(
            Key={"userId": user_id}
        )
        
        if "Item" not in response:
            logger.warning(
                "get_profile_not_found",
                context={"user_id": user_id},
            )
            raise ProfileNotFound()
        
        item = response["Item"]
        
        # Build response with all required fields
        profile_data = {
            "perfilEstructurado": item.get("perfilEstructurado"),
            "resumenParaMatching": item.get("resumenParaMatching"),
            "cargosSugeridos": item.get("cargosSugeridos", []),
            "cargosActivos": item.get("cargosActivos", []),
            "profileVersion": item.get("profileVersion", 1),
            "updatedAt": item.get("updatedAt"),
            "resumenGenerating": item.get("resumenGenerationStatus") == "pending",
        }
        
        logger.info(
            "get_profile_success",
            context={
                "user_id": user_id,
                "profile_version": profile_data["profileVersion"],
            },
        )
        
        return profile_data

    except ProfileNotFound:
        raise
    except Exception as e:
        logger.error(
            "get_profile_error",
            context={
                "user_id": user_id,
                "error": str(e),
            },
        )
        raise


# ============================================================================
# PUT /me/profile - Save Structured Profile
# ============================================================================


@router.put("", response_model=dict)
async def save_profile(
    request: SaveProfileRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Save a structured profile for the user.

    Endpoint: PUT /me/profile
    Auth: Required (JWT)

    Request Body:
        - perfilEstructurado: Structured profile (PerfilEstructurado model)

    Response (HTTP 200):
        - profileVersion: Updated version number
        - updatedAt: Timestamp of update

    Error Responses:
        - HTTP 400: Validation error

    Logic:
    1. Validate request body (already done by Pydantic)
    2. Get current profile to determine next version
    3. Persist ONLY perfilEstructurado, profileVersion (incremented), updatedAt
    4. Disparar la generación asíncrona de resumenParaMatching vía
       _trigger_async_resumen_generation (invocación Event, no bloqueante)
    5. Return HTTP 200 with version info immediately — la respuesta HTTP sigue
       siendo solo {"profileVersion", "updatedAt"}; el disparo asíncrono nunca
       la modifica ni puede fallarla (ver _trigger_async_resumen_generation)
    6. Never modify resumenParaMatching, resumenGenerationStatus, cargosSugeridos
       directamente en este endpoint (el worker asíncrono es quien los escribe)
    7. Log save operation

    Requirements:
    - 2.1: Validate body against SaveProfileRequest; disparar el trigger
      asíncrono de resumenParaMatching tras persistir el perfil
    - 2.2: El disparo es no bloqueante (invocación Event) y no altera la
      respuesta HTTP de este endpoint
    - 2.3: Persist perfilEstructurado
    - 2.4: Increment profileVersion
    - 2.5: Update updatedAt timestamp
    - 3.1: Return HTTP 200 with version/timestamp
    - 3.2: Perform write atomically, return immediately
    - 3.3: Log profile save operation
    - 10.1: Perform DynamoDB write
    - 10.2: Increment version atomically
    - 10.3: Never enqueue background tasks in this endpoint
    - 10.4: Never modify resumenParaMatching or resumenGenerationStatus
    - 10.5: Return only version and updatedAt (worker owns other fields)
    """
    logger.info(
        "save_profile_start",
        context={
            "user_id": user_id,
        },
    )

    try:
        # Step 1: Get current profile to determine next version
        perfiles_table = get_dynamodb_table("DYNAMODB_TABLE_PERFILES")
        
        get_response = perfiles_table.get_item(
            Key={"userId": user_id}
        )
        
        current_version = 1
        
        if "Item" in get_response:
            item = get_response["Item"]
            current_version = item.get("profileVersion", 1)
        
        # Step 2: Prepare update
        new_version = current_version + 1
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Step 3: Update ONLY perfilEstructurado, profileVersion, updatedAt
        # Use update_item with attribute updates to preserve other fields
        perfiles_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET perfilEstructurado = :perfil, profileVersion = :ver, updatedAt = :ts",
            ExpressionAttributeValues={
                ":perfil": request.perfilEstructurado.model_dump(),
                ":ver": new_version,
                ":ts": updated_at,
            },
            ReturnValues="ALL_NEW",
        )
        
        # Step 4: Return response with version info only
        response_data = {
            "profileVersion": new_version,
            "updatedAt": updated_at,
        }
        
        logger.info(
            "save_profile_success",
            context={
                "user_id": user_id,
                "new_version": new_version,
            },
        )
        
        # Step 5: Disparar generación asíncrona de resumenParaMatching.
        # _trigger_async_resumen_generation nunca lanza excepciones (ver su
        # propio docstring), por lo que se llama directamente sin try/except
        # adicional aquí; su resultado no afecta la respuesta HTTP.
        _trigger_async_resumen_generation(user_id)
        
        return response_data

    except Exception as e:
        logger.error(
            "save_profile_error",
            context={
                "user_id": user_id,
                "error": str(e),
            },
        )
        raise ValidationErrorException(
            message="Failed to save profile",
            details=str(e),
        )


# ============================================================================
# POST /me/profile/roles/suggest - Suggest Job Roles from Resume
# ============================================================================


@roles_router.post("/suggest", response_model=dict)
async def suggest_roles(
    user_id: str = Depends(get_current_user_id),
):
    """
    Suggest job roles based on the user's resume.

    Endpoint: POST /me/profile/roles/suggest
    Auth: Required (JWT)

    Response (HTTP 200):
        - suggestions: List of suggested job roles
        - suggestedAt: Timestamp of suggestion

    Error Responses:
        - HTTP 424: Resume not ready (resumenParaMatching is null)
        - HTTP 400: Validation error after retry
        - HTTP 502: Bedrock failure/timeout

    Lógica de bloqueo corregida (Requirement 3):
    - resumenParaMatching existe → SIEMPRE permite (200), sin importar si
      resumenGenerationStatus es 'pending', 'failed', 'complete' o None. Una
      regeneración en curso o fallida en segundo plano NUNCA bloquea al usuario
      mientras exista un resumen previo utilizable (Criterios 3.2, 3.3, 3.6).
    - resumenParaMatching es None Y resumenGenerationStatus == 'failed' → bloquea
      (424) Y dispara automáticamente un retry de generación asíncrona vía
      _trigger_async_resumen_generation, dejando resumenGenerationStatus en
      'pending' (o 'failed'/'unknown' si el propio despacho del retry vuelve a
      fallar) antes de responder (Criterio 3.7).
    - resumenParaMatching es None Y resumenGenerationStatus no es 'failed'
      (incluye None) → bloquea (424) sin disparar ningún retry (Criterio 3.1).
    - Esta ruta NUNCA reintenta la llamada por su cuenta ni implementa un loop:
      dispara como máximo una invocación asíncrona por request, y responde
      (Criterio 3.8).

    La decisión de bloqueo/permiso se delega a la función pura
    decide_roles_suggest_action(resumenParaMatching, resumenGenerationStatus),
    que retorna RolesSuggestDecision.ALLOW | .BLOCK | .BLOCK_AND_RETRY.

    Logic:
    1. Query Perfiles by userId
    2. decision = decide_roles_suggest_action(resumen, generation_status)
       - BLOCK_AND_RETRY: dispara _trigger_async_resumen_generation(user_id) y
         luego levanta ResumeNotReady() (HTTP 424)
       - BLOCK: levanta ResumeNotReady() (HTTP 424) directamente, sin trigger
       - ALLOW: continúa con el flujo existente (pasos 3-8 abajo)
    3. Invoke Bedrock SMALL model with role suggestion prompt
    4. Validate response against RolesSuggestions schema
    5. If validation fails: Retry once with error injected
    6. If retry fails: Return HTTP 400
    7. Return suggestions (not persisted)
    8. Log operation

    Requirements:
    - 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8, 3.9: Corrected block/allow decision,
      automatic retry trigger on BLOCK_AND_RETRY, no client/server retry loop,
      docstring accurately reflects the corrected logic
    - 4.1: Check resumenParaMatching and generation status
    - 4.2: Return HTTP 424 if resume not ready
    - 4.3: Invoke Bedrock SMALL model
    - 4.4: Validate against RolesSuggestions
    - 4.5: Retry once on validation failure
    - 4.6: Return HTTP 200 with suggestions on success
    - 4.7: Log suggestions attempt
    """
    logger.info(
        "suggest_roles_start",
        context={"user_id": user_id},
    )

    try:
        # Step 1: Query Perfiles to get resumenParaMatching
        perfiles_table = get_dynamodb_table("DYNAMODB_TABLE_PERFILES")
        
        response = perfiles_table.get_item(
            Key={"userId": user_id}
        )
        
        if "Item" not in response:
            logger.warning(
                "suggest_roles_profile_not_found",
                context={"user_id": user_id},
            )
            raise ResumeNotReady()
        
        item = response["Item"]
        resumen = item.get("resumenParaMatching")
        generation_status = item.get("resumenGenerationStatus")
        
        # Step 2: Decide block/allow via the pure decision function
        # (Requirements 3.1, 3.2, 3.3, 3.5, 3.6, 3.7)
        decision = decide_roles_suggest_action(resumen, generation_status)
        
        if decision == RolesSuggestDecision.BLOCK_AND_RETRY:
            logger.info(
                "suggest_roles_resume_not_ready",
                context={
                    "user_id": user_id,
                    "has_resumen": resumen is not None,
                    "generation_status": generation_status,
                    "decision": decision.value,
                },
            )
            _trigger_async_resumen_generation(user_id)
            raise ResumeNotReady()
        
        if decision == RolesSuggestDecision.BLOCK:
            logger.info(
                "suggest_roles_resume_not_ready",
                context={
                    "user_id": user_id,
                    "has_resumen": resumen is not None,
                    "generation_status": generation_status,
                    "decision": decision.value,
                },
            )
            raise ResumeNotReady()
        
        # Step 3: Prepare prompt for Bedrock
        prompt = _prepare_roles_suggestion_prompt(resumen)
        
        # Step 4: Invoke Bedrock with retry
        bedrock_client = get_bedrock_client()
        suggestions = bedrock_client.invoke_with_retry(
            prompt=prompt,
            response_model=RolesSuggestions,
            model_id=bedrock_client.model_small,
            max_retries=1,
        )
        
        suggested_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        response_data = {
            "suggestions": suggestions.suggestions,
            "suggestedAt": suggested_at,
        }
        
        logger.info(
            "suggest_roles_success",
            context={
                "user_id": user_id,
                "num_suggestions": len(suggestions.suggestions),
            },
        )
        
        return response_data

    except (ResumeNotReady, ProfileNotFound):
        raise
    except ValidationError as ve:
        # Pydantic validation failed after retry → HTTP 400
        logger.error(
            "suggest_roles_validation_error",
            context={
                "user_id": user_id,
                "error": str(ve),
            },
        )
        raise ValidationErrorException(
            message="Failed to validate role suggestions",
            details="Bedrock response did not match expected schema after retry",
        )
    except Exception as e:
        error_type = type(e).__name__
        logger.error(
            "suggest_roles_error",
            context={
                "user_id": user_id,
                "error_type": error_type,
                "error": str(e),
            },
        )
        raise AIServiceUnavailable(
            message="Failed to suggest roles",
            details=f"Bedrock invocation failed: {error_type}",
        )


# ============================================================================
# PUT /me/profile/roles - Save Active Roles
# ============================================================================


@roles_router.put("", response_model=dict)
async def save_roles(
    request: SetRolesRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Save user's active job roles/titles.

    Endpoint: PUT /me/profile/roles
    Auth: Required (JWT)

    Request Body:
        - cargosActivos: List of 1-10 job roles, each ≤50 chars (empty list allowed)

    Response (HTTP 200):
        - profileVersion: Updated version number
        - cargosActivos: Saved roles
        - updatedAt: Timestamp of update

    Error Responses:
        - HTTP 400: Validation error (invalid role list)

    Logic:
    1. Validate cargosActivos via validate_roles_list (1-10 items, ≤50 chars each)
    2. If invalid: Return HTTP 400
    3. Get current profile to determine next version
    4. Update ONLY cargosActivos, profileVersion (incremented), updatedAt
    5. Return HTTP 200 with version/roles/timestamp
    6. Log operation

    Requirements:
    - 5.1: Accept PUT with cargosActivos
    - 5.2: Validate roles list (1-10 items, ≤50 chars each)
    - 5.3: Return HTTP 400 on validation error
    - 5.4: Persist roles atomically
    - 5.5: Increment profileVersion
    - 5.6: Return HTTP 200 with version/roles/timestamp
    """
    logger.info(
        "save_roles_start",
        context={
            "user_id": user_id,
            "num_roles": len(request.cargosActivos),
        },
    )

    try:
        # Step 1: Validate roles list
        from backend.shared.validators import validate_roles_list
        
        is_valid, error_msg = validate_roles_list(request.cargosActivos)
        if not is_valid:
            logger.warning(
                "save_roles_validation_failed",
                context={
                    "user_id": user_id,
                    "reason": error_msg,
                },
            )
            raise ValidationErrorException(
                message="Invalid roles list",
                details=error_msg,
            )
        
        # Step 2: Get current profile for version tracking
        perfiles_table = get_dynamodb_table("DYNAMODB_TABLE_PERFILES")
        
        get_response = perfiles_table.get_item(
            Key={"userId": user_id}
        )
        
        current_version = 1
        if "Item" in get_response:
            current_version = get_response["Item"].get("profileVersion", 1)
        
        # Step 3: Update roles
        new_version = current_version + 1
        updated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        perfiles_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET cargosActivos = :roles, profileVersion = :ver, updatedAt = :ts",
            ExpressionAttributeValues={
                ":roles": request.cargosActivos,
                ":ver": new_version,
                ":ts": updated_at,
            },
        )
        
        response_data = {
            "profileVersion": new_version,
            "cargosActivos": request.cargosActivos,
            "updatedAt": updated_at,
        }
        
        logger.info(
            "save_roles_success",
            context={
                "user_id": user_id,
                "new_version": new_version,
                "num_roles": len(request.cargosActivos),
            },
        )
        
        return response_data

    except ValidationErrorException:
        raise
    except Exception as e:
        logger.error(
            "save_roles_error",
            context={
                "user_id": user_id,
                "error": str(e),
            },
        )
        raise ValidationErrorException(
            message="Failed to save roles",
            details=str(e),
        )


def _prepare_cv_parsing_prompt(cv_text: str) -> str:
    """
    Prepare the Bedrock prompt for CV parsing.

    Includes instructions to extract structured data from CV text
    and return valid JSON matching PerfilEstructurado schema.

    Args:
        cv_text: Raw CV text from user

    Returns:
        Formatted prompt string for Bedrock

    Req: 12.2 - includes schema in prompt for validation hints
    """
    prompt = f"""Extract the following information from the CV text and return a JSON object:

- experiencia: array of work experience entries, each with:
  - puesto (string): job title
  - empresa (string): company name
  - duracion (string): duration (e.g., "2 years", "Jan 2020 - Dec 2021")
  - descripcion (string): job description and responsibilities
  - tecnologias (array of strings, optional): technologies used

- educacion: array of education entries, each with:
  - titulo (string): degree or certification title
  - institucion (string): institution name
  - ano (string): year or year range
  - especializacion (string, optional): specialization or focus area

- proyectos: array of projects, each with (optional):
  - nombre (string): project name
  - descripcion (string): project description
  - tecnologias (array of strings, optional): technologies used
  - url (string, optional): project URL

- certificaciones: array of certifications, each with (optional):
  - nombre (string): certification name
  - emisor (string): issuing organization
  - ano (string): year obtained

- skills: array of technical skills (required)
- lenguajes: array of languages (optional)

CV Text:
{cv_text}

Return ONLY valid JSON matching the schema above. No explanation, no markdown formatting.
Start with {{ and end with }}.
"""
    return prompt


def _prepare_roles_suggestion_prompt(resumen_text: str) -> str:
    """
    Prepare the Bedrock prompt for role suggestions.

    Takes the resume summary text and generates role suggestions
    based on skills, experience, and background.

    Args:
        resumen_text: Resume summary text

    Returns:
        Formatted prompt string for Bedrock

    Req: 12.2 - includes schema in prompt for validation hints
    """
    prompt = f"""Based on this professional profile summary, suggest 5-7 job titles/roles that would be a good fit.
Return as JSON with a "suggestions" field containing an array of strings.

Profile Summary:
{resumen_text}

Return ONLY valid JSON: {{"suggestions": ["Role1", "Role2", ...]}}. No explanation."""
    return prompt


def _prepare_resumen_prompt(perfil_estructurado: dict) -> str:
    """
    Prepare the Bedrock prompt for resumenParaMatching generation.

    Takes the structured profile (perfilEstructurado) and asks Bedrock to
    produce a natural-language summary intended for role/vacancy matching.

    The "<=500 words" constraint is expressed as prompt text, not as a
    Pydantic max_length (Pydantic measures characters, not words, and the
    rest of the codebase — CVATSOutput, SuggestedAnswerOutput — doesn't
    enforce length limits on LLM-generated text via Pydantic either).

    Args:
        perfil_estructurado: Structured profile dict (matches PerfilEstructurado
            schema: experiencia, educacion, proyectos, certificaciones, skills,
            lenguajes)

    Returns:
        Formatted prompt string for Bedrock

    Requirements: 2.3
    """
    perfil_json = json.dumps(perfil_estructurado, ensure_ascii=False)

    prompt = f"""Based on the following structured professional profile, write a natural-language
summary of this person's background, skills, and experience, intended to be used
for matching against job vacancies.

The summary MUST be 500 words or fewer.

Structured Profile (JSON):
{perfil_json}

Return ONLY valid JSON: {{"resumen": "<summary text, 500 words or fewer>"}}. No explanation, no markdown formatting."""
    return prompt
