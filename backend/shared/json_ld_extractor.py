"""
JSON-LD Extractor for the scan worker cascade.

Fetches a company's careers URL, parses HTML for application/ld+json blocks
containing JobPosting schema, and maps them to VacancyExtracted results.

Handles:
- Standalone JobPosting objects
- Arrays of JobPosting objects
- @graph arrays containing JobPosting objects
- HTTP errors, timeouts, connection errors
- Missing or malformed ld+json blocks

Requirements: 4.1-4.5, 2.8
"""

import json
from typing import List

import requests
from bs4 import BeautifulSoup

from backend.shared.extraction import ExtractionResult, VacancyExtracted
from backend.shared.logging_config import get_contextual_logger
from backend.shared.models import Empresa

logger = get_contextual_logger(__name__)

_TIMEOUT_SECONDS = 10


def _extract_job_postings_from_data(data) -> List[dict]:
    """Extract all JobPosting objects from a parsed JSON-LD structure.

    Handles:
    - A single dict with @type == "JobPosting"
    - A list of objects, each potentially a JobPosting
    - A dict with @graph containing a list of objects

    Args:
        data: Parsed JSON data (dict or list).

    Returns:
        List of dicts that are JobPosting objects.
    """
    postings: List[dict] = []

    if isinstance(data, dict):
        # Check if this object itself is a JobPosting
        obj_type = data.get("@type", "")
        if obj_type == "JobPosting" or (
            isinstance(obj_type, list) and "JobPosting" in obj_type
        ):
            postings.append(data)
        # Check @graph array
        elif "@graph" in data and isinstance(data["@graph"], list):
            for item in data["@graph"]:
                if isinstance(item, dict):
                    item_type = item.get("@type", "")
                    if item_type == "JobPosting" or (
                        isinstance(item_type, list) and "JobPosting" in item_type
                    ):
                        postings.append(item)

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                item_type = item.get("@type", "")
                if item_type == "JobPosting" or (
                    isinstance(item_type, list) and "JobPosting" in item_type
                ):
                    postings.append(item)
                # Also check nested @graph in array items
                elif "@graph" in item and isinstance(item["@graph"], list):
                    for graph_item in item["@graph"]:
                        if isinstance(graph_item, dict):
                            gi_type = graph_item.get("@type", "")
                            if gi_type == "JobPosting" or (
                                isinstance(gi_type, list)
                                and "JobPosting" in gi_type
                            ):
                                postings.append(graph_item)

    return postings


def _map_modalidad(job_posting: dict) -> str:
    """Map employmentType to modalidad value.

    ONLY maps to remote/hybrid/presencial if the source EXPLICITLY states it.
    If not present or not recognized, returns 'sin_dato'.
    PROHIBITED to infer.

    Args:
        job_posting: A JobPosting JSON-LD dict.

    Returns:
        One of: 'remoto', 'hibrido', 'presencial', 'sin_dato'
    """
    employment_type = job_posting.get("employmentType")
    job_location_type = job_posting.get("jobLocationType", "")
    applicant_location = job_posting.get("applicantLocationRequirements")

    # Check jobLocationType for TELECOMMUTE (schema.org standard for remote)
    if isinstance(job_location_type, str) and job_location_type.upper() == "TELECOMMUTE":
        return "remoto"

    # Check employmentType if it's a string or list
    if employment_type:
        if isinstance(employment_type, str):
            types = [employment_type.upper()]
        elif isinstance(employment_type, list):
            types = [t.upper() for t in employment_type if isinstance(t, str)]
        else:
            types = []

        for t in types:
            if "REMOTE" in t or "TELECOMMUTE" in t:
                return "remoto"

    # If applicantLocationRequirements is present, it often indicates remote
    # But we only map if explicitly stated as remote — don't infer
    return "sin_dato"


def _extract_ubicacion(job_posting: dict) -> str:
    """Extract location from a JobPosting.

    Args:
        job_posting: A JobPosting JSON-LD dict.

    Returns:
        Location string or empty string if not present.
    """
    job_location = job_posting.get("jobLocation")
    if not job_location:
        return ""

    # jobLocation can be a Place object or a list of Place objects
    if isinstance(job_location, list):
        locations = []
        for loc in job_location:
            loc_str = _extract_single_location(loc)
            if loc_str:
                locations.append(loc_str)
        return ", ".join(locations) if locations else ""

    return _extract_single_location(job_location)


def _extract_single_location(location) -> str:
    """Extract location string from a single Place object.

    Args:
        location: A Place JSON-LD dict or string.

    Returns:
        Location string or empty string.
    """
    if isinstance(location, str):
        return location

    if not isinstance(location, dict):
        return ""

    # Try address first (more specific)
    address = location.get("address")
    if address:
        if isinstance(address, str):
            return address
        if isinstance(address, dict):
            parts = []
            locality = address.get("addressLocality", "")
            region = address.get("addressRegion", "")
            country = address.get("addressCountry", "")
            if isinstance(country, dict):
                country = country.get("name", "")
            if locality:
                parts.append(locality)
            if region:
                parts.append(region)
            if country:
                parts.append(country)
            return ", ".join(parts) if parts else ""

    # Fallback to name
    name = location.get("name", "")
    return name if isinstance(name, str) else ""


def _extract_url(job_posting: dict) -> str:
    """Extract URL from a JobPosting.

    Tries 'url' field first, then 'sameAs', then falls back to empty string.

    Args:
        job_posting: A JobPosting JSON-LD dict.

    Returns:
        URL string or empty string if not found.
    """
    url = job_posting.get("url", "")
    if url and isinstance(url, str):
        return url.strip()

    same_as = job_posting.get("sameAs", "")
    if same_as and isinstance(same_as, str):
        return same_as.strip()

    return ""


def _map_job_posting_to_vacancy(job_posting: dict) -> VacancyExtracted | None:
    """Map a single JobPosting JSON-LD object to VacancyExtracted.

    Requirements 4.4, 4.5:
    - modalidad defaults to 'sin_dato' when not specified
    - Exclude if no URL or no title (without error)

    Args:
        job_posting: A JobPosting JSON-LD dict.

    Returns:
        VacancyExtracted or None if title/url missing.
    """
    title = job_posting.get("title", "") or job_posting.get("name", "")
    if not title or not isinstance(title, str) or not title.strip():
        return None

    url = _extract_url(job_posting)
    if not url:
        return None

    description = job_posting.get("description", "")
    if not isinstance(description, str):
        description = ""

    modalidad = _map_modalidad(job_posting)
    ubicacion = _extract_ubicacion(job_posting)

    return VacancyExtracted(
        titulo=title.strip(),
        descripcion=description.strip(),
        url=url,
        modalidad=modalidad,
        ubicacion=ubicacion,
    )


def json_ld_extractor(empresa: Empresa) -> ExtractionResult:
    """Extract job postings from JSON-LD blocks in a company's careers page.

    Fetches the careersUrl, parses HTML for application/ld+json script tags,
    locates JobPosting blocks (standalone, array, or @graph), and maps them
    to VacancyExtracted objects.

    Requirements:
    - 4.1: Fetch careersUrl, locate ld+json JobPosting blocks
    - 4.2: Handle HTTP errors, timeouts, connection errors
    - 4.3: If no JobPosting block found → return zero vacancies
    - 4.4: Map to VacancyExtracted with modalidad='sin_dato' default
    - 4.5: Exclude JobPostings without URL or title

    Args:
        empresa: Empresa model with careersUrl.

    Returns:
        ExtractionResult with vacancies, origen='json_ld', and optional error.
    """
    try:
        response = requests.get(
            empresa.careersUrl,
            timeout=_TIMEOUT_SECONDS,
            headers={"User-Agent": "JobAppBot/1.0"},
        )
    except requests.exceptions.Timeout:
        logger.warning(
            "json_ld_fetch_timeout",
            context={
                "companyId": empresa.companyId,
                "careersUrl": empresa.careersUrl,
            },
        )
        return ExtractionResult(
            vacancies=[],
            origen="json_ld",
            error="timeout_fetching_careers_url",
        )
    except requests.exceptions.ConnectionError:
        logger.warning(
            "json_ld_connection_error",
            context={
                "companyId": empresa.companyId,
                "careersUrl": empresa.careersUrl,
            },
        )
        return ExtractionResult(
            vacancies=[],
            origen="json_ld",
            error="connection_error",
        )
    except requests.exceptions.RequestException as e:
        logger.warning(
            "json_ld_request_error",
            context={
                "companyId": empresa.companyId,
                "error": str(e)[:100],
            },
        )
        return ExtractionResult(
            vacancies=[],
            origen="json_ld",
            error="request_error",
        )

    # Requirement 4.2: HTTP 4xx/5xx → error
    if response.status_code >= 400:
        logger.warning(
            "json_ld_http_error",
            context={
                "companyId": empresa.companyId,
                "status_code": response.status_code,
            },
        )
        return ExtractionResult(
            vacancies=[],
            origen="json_ld",
            error=f"http_error_{response.status_code}",
        )

    # Parse HTML with BeautifulSoup (html.parser only, NO lxml)
    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Locate all application/ld+json script tags
    json_ld_scripts = soup.find_all("script", {"type": "application/ld+json"})

    all_postings: List[dict] = []

    for script in json_ld_scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            # Skip malformed JSON-LD blocks
            continue

        postings = _extract_job_postings_from_data(data)
        all_postings.extend(postings)

    # Requirement 4.3: If no JobPosting block found → return zero vacancies
    if not all_postings:
        logger.info(
            "json_ld_no_postings_found",
            context={
                "companyId": empresa.companyId,
                "ld_json_blocks_count": len(json_ld_scripts),
            },
        )
        return ExtractionResult(vacancies=[], origen="json_ld", error=None)

    # Requirement 4.4, 4.5: Map each posting, exclude those without title/url
    vacancies: List[VacancyExtracted] = []
    excluded_count = 0

    for posting in all_postings:
        vacancy = _map_job_posting_to_vacancy(posting)
        if vacancy is not None:
            vacancies.append(vacancy)
        else:
            excluded_count += 1

    if excluded_count > 0:
        logger.info(
            "json_ld_excluded_postings",
            context={
                "companyId": empresa.companyId,
                "excluded": excluded_count,
                "included": len(vacancies),
            },
        )

    logger.info(
        "json_ld_extraction_complete",
        context={
            "companyId": empresa.companyId,
            "vacancies_count": len(vacancies),
        },
    )

    return ExtractionResult(vacancies=vacancies, origen="json_ld", error=None)
