"""
Board API Client extractor for Greenhouse and Lever platforms.

Queries public JSON APIs to extract job postings without spending Bedrock tokens.
This is the FIRST method in the Cascada_Descubrimiento for greenhouse/lever platforms.

Requirements: 3.1-3.6, 2.8
"""

import json
import logging
import sys
from typing import List

import requests

from backend.shared.extraction import ExtractionResult, VacancyExtracted
from backend.shared.models import Empresa

logger = logging.getLogger(__name__)

# API endpoints (public, no auth required per tech rule 7)
GREENHOUSE_API_URL = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
LEVER_API_URL = "https://api.lever.co/v0/postings/{board_token}"

# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT_SECONDS = 10


def _parse_greenhouse_jobs(data: list) -> List[VacancyExtracted]:
    """Parse Greenhouse API response into VacancyExtracted list.

    Greenhouse returns: {"jobs": [{"title": ..., "absolute_url": ..., ...}, ...]}
    Each job MUST have a URL to be included (Requirement 3.6).
    modalidad defaults to 'sin_dato' (Requirement 3.5).
    """
    vacancies: List[VacancyExtracted] = []
    for job in data:
        url = job.get("absolute_url", "")
        titulo = job.get("title", "")

        # Requirement 3.6: exclude entries without URL
        if not url:
            continue

        # titulo is required by VacancyExtracted
        if not titulo:
            continue

        vacancies.append(
            VacancyExtracted(
                titulo=titulo,
                descripcion="",
                url=url,
                modalidad="sin_dato",  # Requirement 3.5: never infer
                ubicacion=job.get("location", {}).get("name", "") if isinstance(job.get("location"), dict) else "",
            )
        )
    return vacancies


def _parse_lever_jobs(data: list) -> List[VacancyExtracted]:
    """Parse Lever API response into VacancyExtracted list.

    Lever returns: [{"text": ..., "hostedUrl": ..., "categories": {...}, ...}, ...]
    Each job MUST have a URL to be included (Requirement 3.6).
    modalidad defaults to 'sin_dato' (Requirement 3.5).
    """
    vacancies: List[VacancyExtracted] = []
    for job in data:
        url = job.get("hostedUrl", "")
        titulo = job.get("text", "")

        # Requirement 3.6: exclude entries without URL
        if not url:
            continue

        # titulo is required by VacancyExtracted
        if not titulo:
            continue

        categories = job.get("categories", {}) if isinstance(job.get("categories"), dict) else {}
        ubicacion = categories.get("location", "")

        vacancies.append(
            VacancyExtracted(
                titulo=titulo,
                descripcion="",
                url=url,
                modalidad="sin_dato",  # Requirement 3.5: never infer
                ubicacion=ubicacion,
            )
        )
    return vacancies


def board_api_client(empresa: Empresa) -> ExtractionResult:
    """Extract job vacancies from Greenhouse or Lever public board API.

    This function:
    - Reads boardToken from Empresa (Requirement 3.1, 3.2)
    - Makes an HTTP GET request to the appropriate API
    - Parses the JSON response
    - Maps entries to VacancyExtracted with modalidad='sin_dato' (Requirement 3.5)
    - Excludes entries without URL (Requirement 3.6)
    - Returns ExtractionResult with error on HTTP/timeout/parse failures (Requirement 3.3, 3.4)

    Args:
        empresa: Company record with plataforma and boardToken.

    Returns:
        ExtractionResult with vacancies on success, or error message on failure.
        Never raises to caller — errors are captured in ExtractionResult.error.
    """
    origen = "board_api"

    # Validate boardToken exists
    if not empresa.boardToken:
        logger.warning(
            "board_api_no_token",
            extra={"companyId": empresa.companyId, "plataforma": empresa.plataforma.value},
        )
        return ExtractionResult(
            vacancies=[],
            origen=origen,
            error="boardToken is missing for empresa",
        )

    # Build URL based on platform
    if empresa.plataforma.value == "greenhouse":
        api_url = GREENHOUSE_API_URL.format(board_token=empresa.boardToken)
    elif empresa.plataforma.value == "lever":
        api_url = LEVER_API_URL.format(board_token=empresa.boardToken)
    else:
        return ExtractionResult(
            vacancies=[],
            origen=origen,
            error=f"Unsupported plataforma for board API: {empresa.plataforma.value}",
        )

    # Make HTTP request
    try:
        response = requests.get(api_url, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        # Requirement 3.3: timeout → error
        logger.warning(
            "board_api_timeout",
            extra={"companyId": empresa.companyId, "url": api_url},
        )
        return ExtractionResult(
            vacancies=[],
            origen=origen,
            error="HTTP request timed out",
        )
    except requests.exceptions.ConnectionError as e:
        logger.warning(
            "board_api_connection_error",
            extra={"companyId": empresa.companyId, "error": str(e)[:100]},
        )
        return ExtractionResult(
            vacancies=[],
            origen=origen,
            error=f"Connection error: {str(e)[:100]}",
        )
    except requests.exceptions.RequestException as e:
        logger.warning(
            "board_api_request_error",
            extra={"companyId": empresa.companyId, "error": str(e)[:100]},
        )
        return ExtractionResult(
            vacancies=[],
            origen=origen,
            error=f"Request error: {str(e)[:100]}",
        )

    # Requirement 3.3: HTTP 4xx/5xx → error
    if response.status_code >= 400:
        logger.warning(
            "board_api_http_error",
            extra={
                "companyId": empresa.companyId,
                "status_code": response.status_code,
            },
        )
        return ExtractionResult(
            vacancies=[],
            origen=origen,
            error=f"HTTP {response.status_code}",
        )

    # Requirement 3.4: parse JSON
    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "board_api_invalid_json",
            extra={"companyId": empresa.companyId, "error": str(e)[:100]},
        )
        return ExtractionResult(
            vacancies=[],
            origen=origen,
            error="Invalid JSON response",
        )

    # Parse platform-specific response format
    try:
        if empresa.plataforma.value == "greenhouse":
            # Greenhouse wraps jobs in {"jobs": [...]}
            jobs_list = data.get("jobs", []) if isinstance(data, dict) else []
            vacancies = _parse_greenhouse_jobs(jobs_list)
        else:
            # Lever returns a flat array of postings
            jobs_list = data if isinstance(data, list) else []
            vacancies = _parse_lever_jobs(jobs_list)
    except Exception as e:
        logger.warning(
            "board_api_parse_error",
            extra={"companyId": empresa.companyId, "error": str(e)[:100]},
        )
        return ExtractionResult(
            vacancies=[],
            origen=origen,
            error=f"Parse error: {str(e)[:100]}",
        )

    logger.info(
        "board_api_success",
        extra={
            "companyId": empresa.companyId,
            "plataforma": empresa.plataforma.value,
            "vacancies_count": len(vacancies),
        },
    )

    return ExtractionResult(vacancies=vacancies, origen=origen, error=None)
