"""
HTML + LLM extractor for vacancy discovery.

Last-resort extraction method in the Cascada_Descubrimiento: fetches the
careers page, cleans the HTML, and submits the text to Bedrock (BEDROCK_MODEL_SMALL)
to extract structured job postings.

Uses BedrockClient.invoke_with_retry which already handles:
- Pydantic validation of the LLM response
- One retry with the validation error injected into the prompt
- Raises ValidationError on second failure

This module wraps those semantics into ExtractionResult (never raises to caller).

Requirements: 5.2-5.6, 2.8
Tech rules:
- Bedrock model IDs from env vars via bedrock.py (NEVER hardcoded)
- All LLM responses validated with Pydantic (never raw json.loads)
- On validation failure: one retry with error injected, then controlled error
- Structured JSON logging (never log full HTML or LLM responses)
- requests library for HTTP fetch with 10 second timeout
"""

from typing import List

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.shared.bedrock import get_bedrock_client
from backend.shared.extraction import ExtractionResult, VacancyExtracted
from backend.shared.html_cleaner import html_to_clean_text
from backend.shared.logging_config import get_contextual_logger
from backend.shared.models import Empresa

logger = get_contextual_logger(__name__)

# HTTP fetch timeout in seconds (Requirement 5.2)
_FETCH_TIMEOUT_SECONDS = 10


# =============================================================================
# Pydantic model for LLM response validation (Requirement 5.3)
# =============================================================================


class LlmVacancyItem(BaseModel):
    """A single vacancy extracted by the LLM."""

    titulo: str = Field(..., description="Job title")
    descripcion: str = Field(default="", description="Brief description")
    url: str = Field(default="", description="Job posting URL")
    modalidad: str = Field(default="sin_dato", description="Work modality")
    ubicacion: str = Field(default="", description="Location")

    model_config = ConfigDict(extra="ignore")


class LlmExtractionResponse(BaseModel):
    """Expected structure of the Bedrock response for vacancy extraction."""

    vacancies: List[LlmVacancyItem] = Field(
        default_factory=list, description="List of extracted vacancies"
    )

    model_config = ConfigDict(extra="ignore")


# =============================================================================
# Prompt template
# =============================================================================

_EXTRACTION_PROMPT = """You are a structured data extraction assistant.

Below is the cleaned text from a company's careers/jobs page. Extract ALL job vacancies you can find.

For each vacancy, provide:
- titulo: the job title (required)
- descripcion: a brief description of the role (if available)
- url: the URL to the specific job posting (if available, otherwise empty string)
- modalidad: work modality (remote, hybrid, onsite). If not specified, use "sin_dato"
- ubicacion: job location (if available, otherwise empty string)

Return your response as valid JSON with this exact structure:
{{
  "vacancies": [
    {{
      "titulo": "Job Title",
      "descripcion": "Brief description",
      "url": "https://...",
      "modalidad": "sin_dato",
      "ubicacion": "Location or empty"
    }}
  ]
}}

If no job vacancies are found, return: {{"vacancies": []}}

IMPORTANT:
- Only return the JSON object, no additional text.
- If work modality is not explicitly stated, use "sin_dato". Do NOT guess or infer.
- Include ALL job postings found, even if they seem similar.

--- CAREERS PAGE TEXT ---
{clean_text}
--- END ---
"""


# =============================================================================
# Main extractor function
# =============================================================================


def html_llm_extractor(empresa: Empresa) -> ExtractionResult:
    """
    Extract vacancies from a company's careers page using HTML cleaning + LLM.

    Steps:
    1. Fetch careersUrl with 10s timeout
    2. Clean HTML via html_to_clean_text
    3. Invoke Bedrock (BEDROCK_MODEL_SMALL) with cleaned text
    4. Validate response against LlmExtractionResponse Pydantic model
    5. Map to VacancyExtracted list

    On any failure, returns ExtractionResult with error (never raises).

    Args:
        empresa: Company with careersUrl to fetch.

    Returns:
        ExtractionResult with vacancies on success, or error on failure.
    """
    # Step 1: Fetch careersUrl (Requirement 5.2)
    try:
        html = _fetch_careers_page(empresa.careersUrl)
    except Exception as e:
        logger.warning(
            "html_llm_fetch_failed",
            context={
                "companyId": empresa.companyId,
                "error_type": type(e).__name__,
                "error": str(e)[:200],
            },
        )
        return ExtractionResult(
            vacancies=[],
            origen="html_llm",
            error=f"Fetch failed: {type(e).__name__}: {str(e)[:200]}",
        )

    # Step 2: Clean HTML
    clean_text = html_to_clean_text(html)

    if not clean_text.strip():
        logger.info(
            "html_llm_empty_after_clean",
            context={"companyId": empresa.companyId},
        )
        return ExtractionResult(vacancies=[], origen="html_llm", error=None)

    # Step 3+4: Invoke Bedrock with validation retry (Requirements 5.3, 5.4, 5.5)
    try:
        llm_response = _invoke_bedrock_extraction(clean_text, empresa.companyId)
    except (ValidationError, ValueError) as e:
        logger.warning(
            "html_llm_bedrock_validation_failed",
            context={
                "companyId": empresa.companyId,
                "error_type": type(e).__name__,
                "error": str(e)[:200],
            },
        )
        return ExtractionResult(
            vacancies=[],
            origen="html_llm",
            error=f"Bedrock validation failed: {type(e).__name__}: {str(e)[:200]}",
        )
    except Exception as e:
        logger.warning(
            "html_llm_bedrock_error",
            context={
                "companyId": empresa.companyId,
                "error_type": type(e).__name__,
                "error": str(e)[:200],
            },
        )
        return ExtractionResult(
            vacancies=[],
            origen="html_llm",
            error=f"Bedrock error: {type(e).__name__}: {str(e)[:200]}",
        )

    # Step 5: Map to VacancyExtracted (Requirement 5.6)
    vacancies = _map_llm_response_to_vacancies(llm_response)

    logger.info(
        "html_llm_extraction_success",
        context={
            "companyId": empresa.companyId,
            "vacancies_count": len(vacancies),
        },
    )

    return ExtractionResult(vacancies=vacancies, origen="html_llm", error=None)


# =============================================================================
# Internal helpers
# =============================================================================


def _fetch_careers_page(url: str) -> str:
    """
    Fetch careers page HTML with 10-second timeout.

    Raises on HTTP 4xx/5xx or connection/timeout errors (Requirement 5.2).

    Args:
        url: The careers page URL to fetch.

    Returns:
        Raw HTML string.

    Raises:
        requests.HTTPError: On 4xx/5xx response.
        requests.Timeout: On timeout.
        requests.ConnectionError: On connection failure.
    """
    response = requests.get(url, timeout=_FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def _invoke_bedrock_extraction(clean_text: str, company_id: str) -> LlmExtractionResponse:
    """
    Invoke Bedrock with cleaned text and validate response.

    Uses BedrockClient.invoke_with_retry which handles:
    - First invocation with extraction prompt
    - Pydantic validation against LlmExtractionResponse
    - On validation failure: retry once with error in prompt
    - On second failure: raises ValidationError

    Args:
        clean_text: Cleaned HTML text to extract vacancies from.
        company_id: Company ID for logging context.

    Returns:
        Validated LlmExtractionResponse.

    Raises:
        ValidationError: If response fails validation after retry.
        ValueError: If JSON parsing fails.
        Exception: On Bedrock service errors.
    """
    client = get_bedrock_client()
    prompt = _EXTRACTION_PROMPT.format(clean_text=clean_text)

    return client.invoke_with_retry(
        prompt=prompt,
        response_model=LlmExtractionResponse,
        model_id=client.model_small,
        max_retries=1,
    )


def _map_llm_response_to_vacancies(
    llm_response: LlmExtractionResponse,
) -> List[VacancyExtracted]:
    """
    Map validated LLM response items to VacancyExtracted list.

    Requirement 5.6: modalidad defaults to 'sin_dato' when not specified.
    Vacancies without titulo are excluded.

    Args:
        llm_response: Validated Pydantic model from Bedrock.

    Returns:
        List of VacancyExtracted instances.
    """
    vacancies: List[VacancyExtracted] = []

    for item in llm_response.vacancies:
        # Skip entries without a title (minimal required field)
        if not item.titulo or not item.titulo.strip():
            continue

        # Requirement 5.6: modalidad = 'sin_dato' when not specified
        modalidad = item.modalidad if item.modalidad else "sin_dato"

        vacancies.append(
            VacancyExtracted(
                titulo=item.titulo.strip(),
                descripcion=item.descripcion.strip() if item.descripcion else "",
                url=item.url.strip() if item.url else "",
                modalidad=modalidad,
                ubicacion=item.ubicacion.strip() if item.ubicacion else "",
            )
        )

    return vacancies
