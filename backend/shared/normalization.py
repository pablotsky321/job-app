"""
Pure text processing functions for HTML and content normalization.

No AWS calls, no network calls. 100% testable with deterministic inputs/outputs.

**Requirements: 5.3, 7.5**

Functions:
- html_to_clean_text(html: str) -> str: BeautifulSoup with html.parser
- normalize_whitespace(text: str) -> str: Strip and collapse multiple spaces
- extract_page_title(html: str) -> str | None: Extract <title> tag content
- extract_json_ld(html: str) -> dict | None: Parse application/ld+json block
- extract_careers_url_from_html(html: str, base_url: str) -> str | None: Find href matching 'career' or 'job'
- detect_language(titulo: str, descripcion: str) -> str: Heuristic language detection (es/en)
"""

import json
from typing import Any, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup


def html_to_clean_text(html: str) -> str:
    """
    Parse HTML with BeautifulSoup (html.parser, NOT lxml).
    Extract clean text, preserve structure with newlines between blocks.
    Remove script/style tags.

    Args:
        html: HTML string

    Returns:
        Cleaned text with block structure preserved via newlines

    Example:
        >>> html_to_clean_text("<h1>Jobs</h1><p>Apply now</p>")
        "Jobs\nApply now"
    """
    if not html or not isinstance(html, str):
        return ""

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()

        # Get text, preserving structure with newlines
        text = soup.get_text(separator="\n")

        # Normalize to single newlines and clean up
        lines = [line.strip() for line in text.split("\n")]
        # Filter out empty lines to avoid excessive newlines
        text = "\n".join(line for line in lines if line)

        return text
    except Exception:
        # If BeautifulSoup fails, return empty string
        return ""


def normalize_whitespace(text: str) -> str:
    """
    Strip leading/trailing whitespace and collapse multiple consecutive spaces.

    Args:
        text: Input string

    Returns:
        Normalized string

    Example:
        >>> normalize_whitespace("  hello   world  ")
        "hello world"
    """
    if not text or not isinstance(text, str):
        return ""

    # Strip leading/trailing whitespace
    text = text.strip()

    # Collapse multiple spaces into single space
    while "  " in text:
        text = text.replace("  ", " ")

    return text


def extract_page_title(html: str) -> Optional[str]:
    """
    Extract <title> tag content from HTML.

    Args:
        html: HTML string

    Returns:
        Title tag content or None if not found

    Example:
        >>> extract_page_title("<title>Company Careers</title>")
        "Company Careers"
    """
    if not html or not isinstance(html, str):
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")

        if title_tag and title_tag.string:
            title_text = str(title_tag.string).strip()
            return title_text if title_text else None

        return None
    except Exception:
        return None


def extract_json_ld(html: str) -> Optional[dict]:
    """
    Find and parse application/ld+json block in HTML.

    Searches for <script type="application/ld+json">...</script> block,
    parses as JSON, and returns the parsed dict.

    Args:
        html: HTML string

    Returns:
        Parsed JSON-LD dict or None if not found or malformed

    Example:
        >>> html = '<script type="application/ld+json">{"@type": "Organization"}</script>'
        >>> extract_json_ld(html)
        {"@type": "Organization"}
    """
    if not html or not isinstance(html, str):
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Find all script tags with type="application/ld+json"
        json_ld_scripts = soup.find_all(
            "script", {"type": "application/ld+json"}
        )

        if json_ld_scripts:
            for script in json_ld_scripts:
                if script.string:
                    try:
                        json_data = json.loads(script.string)
                        # Return first valid JSON-LD block found
                        if isinstance(json_data, dict):
                            return json_data
                    except json.JSONDecodeError:
                        # Skip malformed JSON-LD blocks
                        continue

        return None
    except Exception:
        return None


def extract_careers_url_from_html(html: str, base_url: str) -> Optional[str]:
    """
    Find href matching 'career' or 'job' keywords in HTML.
    Resolve relative URLs to absolute using base_url.

    Searches for <a> tags with href containing 'career' or 'job' (case-insensitive).
    Returns the first match found, resolved to an absolute URL.

    Args:
        html: HTML string
        base_url: Base URL for resolving relative links (e.g., 'https://example.com')

    Returns:
        Absolute URL of the first matching href or None if not found

    Example:
        >>> html = '<a href="/careers">Join us</a>'
        >>> extract_careers_url_from_html(html, "https://example.com")
        "https://example.com/careers"
    """
    if not html or not isinstance(html, str):
        return None

    if not base_url or not isinstance(base_url, str):
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Find all <a> tags
        links = soup.find_all("a", href=True)

        for link in links:
            href = link.get("href", "").strip()

            if not href:
                continue

            # Check if href contains 'career' or 'job' (case-insensitive)
            href_lower = href.lower()
            if "career" in href_lower or "job" in href_lower:
                # Resolve relative URLs to absolute
                absolute_url = urljoin(base_url, href)
                return absolute_url

        return None
    except Exception:
        return None


import re as _re


# ============================================================================
# LANGUAGE DETECTION HEURISTIC
# ============================================================================

# Spanish indicator words (common in job postings)
_SPANISH_INDICATORS = {
    "empresa", "experiencia", "requisitos", "trabajo", "ingeniero",
    "desarrollador", "ubicación", "ubicacion", "modalidad",
    "responsabilidades", "habilidades", "conocimientos", "años",
    "remoto", "híbrido", "hibrido", "presencial", "puesto",
    "vacante", "descripción", "descripcion", "salario", "beneficios",
    "contrato", "jornada", "funciones", "perfil", "profesional",
}

# English indicator words (common in job postings)
_ENGLISH_INDICATORS = {
    "company", "experience", "requirements", "work", "engineer",
    "developer", "location", "responsibilities", "skills",
    "knowledge", "years", "remote", "hybrid", "onsite", "position",
    "vacancy", "description", "salary", "benefits", "contract",
    "schedule", "role", "team", "about", "qualifications",
    "proficiency", "collaborate", "opportunity", "apply",
}


def detect_language(titulo: str, descripcion: str) -> str:
    """
    Detect language of a vacancy from its title and description using keyword heuristics.

    Counts matches of Spanish and English indicator words in the combined text.
    Returns "en" if English indicators win, otherwise defaults to "es" (Spanish).

    Args:
        titulo: Vacancy title
        descripcion: Vacancy description

    Returns:
        "en" if English detected, "es" otherwise (default for tie, empty, or ambiguous)

    Requirements: 5.3

    Examples:
        >>> detect_language("Desarrollador Backend", "Requisitos: experiencia en Python")
        "es"
        >>> detect_language("Backend Developer", "Requirements: experience with Python")
        "en"
        >>> detect_language("", "")
        "es"
    """
    # Combine and normalize text
    combined = f"{titulo or ''} {descripcion or ''}".lower()

    if not combined.strip():
        return "es"

    # Tokenize: split on non-alphanumeric (supports accented chars)
    words = set(_re.findall(r"[a-záéíóúñü]+", combined))

    spanish_count = len(words & _SPANISH_INDICATORS)
    english_count = len(words & _ENGLISH_INDICATORS)

    # English wins only if strictly more matches than Spanish
    if english_count > spanish_count:
        return "en"

    # Default: Spanish (tie, undetermined, empty)
    return "es"
