"""
Extraction interfaces and helpers for the scan worker cascade.

Lightweight data classes for extraction results and pure functions for
URL normalization and vacancy ID computation.

Requirements: 1.1
"""

import hashlib
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, Field


class VacancyExtracted(BaseModel):
    """Lightweight extraction result for a single vacancy.

    NOT the full Vacante model — this is the intermediate representation
    produced by extractors before upserting into DynamoDB.
    """

    titulo: str = Field(..., description="Job title")
    descripcion: str = Field(default="", description="Job description")
    url: str = Field(..., description="Job posting URL")
    modalidad: str = Field(
        default="sin_dato",
        description="Work modality (remote/hybrid/onsite/sin_dato)",
    )
    ubicacion: str = Field(default="", description="Job location")

    model_config = ConfigDict(extra="ignore")


class ExtractionResult(BaseModel):
    """Result of running one extraction method (board_api, json_ld, html_llm).

    Contains the list of extracted vacancies, the method origin, and an
    optional error message when the method failed.
    """

    vacancies: List[VacancyExtracted] = Field(
        default_factory=list, description="Extracted vacancies"
    )
    origen: str = Field(..., description="Extraction method origin (board_api, json_ld, html_llm)")
    error: Optional[str] = Field(
        default=None, description="Error message if extraction failed"
    )

    model_config = ConfigDict(extra="ignore")


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication purposes.

    Normalization rules:
    - Lowercase scheme and host
    - Remove fragment (#...)
    - Remove trailing slash from path

    Args:
        url: The URL to normalize.

    Returns:
        Normalized URL string.

    Example:
        >>> normalize_url("HTTPS://Example.COM/jobs/#apply")
        'https://example.com/jobs'
    """
    parsed = urlparse(url)
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        parsed.params,
        parsed.query,
        "",  # no fragment
    ))
    return normalized


def compute_vacancyId(url: str) -> str:
    """Compute the deduplication key for a vacancy from its URL.

    Returns a 64-character lowercase hexadecimal SHA-256 hash of the
    normalized URL. This is the ONLY valid dedup key — never use
    company+title+location (LLM output is non-deterministic).

    Args:
        url: The job posting URL.

    Returns:
        64-char lowercase hex SHA-256 hash of the normalized URL.

    Example:
        >>> len(compute_vacancyId("https://example.com/jobs/123"))
        64
    """
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
