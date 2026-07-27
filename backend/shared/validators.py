"""
Pure validation functions for backend-core.

NO AWS calls, NO network calls, 100% deterministic, fully testable.

Functions validate:
- URL normalization and deduplication (SHA-256 hashing)
- Platform detection from hostname only (no HTTP fetch)
- CV text constraints (non-empty, size limit)
- Roles list constraints (count, length)
- Company URL format

Requirements: 7.2, 7.3, 7.4, 1.1, 1.5, 5.1, 7.1
"""

import hashlib
from typing import List, Tuple
from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.

    Transformations:
    - Lowercase scheme and host (case-insensitive per RFC 3986)
    - Remove fragment (#)
    - Remove trailing slash
    - Return absolute URL

    Args:
        url: URL string to normalize

    Returns:
        Normalized URL (absolute, lowercase scheme/host, no fragment, no trailing /)

    Example:
        >>> normalize_url("https://EXAMPLE.COM/careers/#jobs")
        'https://example.com/careers'

    Raises:
        ValueError: If URL is malformed (missing scheme or netloc)
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Failed to parse URL: {e}")

    # Validate required components
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("URL must have a scheme (http/https) and hostname")

    # Normalize scheme and netloc to lowercase
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Reconstruct URL without fragment, with lowercase scheme/netloc
    normalized = urlunparse((scheme, netloc, parsed.path, parsed.params, parsed.query, ""))

    # Remove trailing slash
    if normalized.endswith("/"):
        normalized = normalized[:-1]

    return normalized


def compute_company_id(url: str) -> str:
    """
    Compute SHA-256 hash of normalized URL.

    Used as unique company identifier (deduplication key).
    Result is a 64-character hexadecimal string.

    Args:
        url: Company careers URL

    Returns:
        SHA-256 hash as 64-character hex string

    Example:
        >>> company_id = compute_company_id("https://example.com/careers")
        >>> len(company_id)
        64
        >>> all(c in '0123456789abcdef' for c in company_id)
        True

    Raises:
        ValueError: If URL is malformed (invalid scheme or netloc)
    """
    normalized = normalize_url(url)
    sha256_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return sha256_hash


def detect_platform_hostname_only(url: str) -> str:
    """
    Detect job posting platform from URL hostname only.

    Fully pure, no network calls, no HTTP fetch, no JSON-LD inspection.

    Platform detection logic (order matters):
    1. If hostname contains 'greenhouse' (case-insensitive) → 'greenhouse'
    2. Else if hostname contains 'lever' (case-insensitive) → 'lever'
    3. Else → 'html'

    Args:
        url: Career page URL

    Returns:
        Platform string: 'greenhouse' | 'lever' | 'html'

    Example:
        >>> detect_platform_hostname_only("https://company.greenhouse.io/jobs")
        'greenhouse'
        >>> detect_platform_hostname_only("https://company.lever.co/careers")
        'lever'
        >>> detect_platform_hostname_only("https://example.com/careers")
        'html'

    Raises:
        ValueError: If URL is malformed (missing scheme or hostname)
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Failed to parse URL: {e}")

    # Validate required components
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("URL must have a scheme (http/https) and hostname")

    hostname = parsed.netloc.lower()

    # Check for platform keywords in hostname
    if "greenhouse" in hostname:
        return "greenhouse"
    elif "lever" in hostname:
        return "lever"
    else:
        return "html"


def validate_cv_text(text: str) -> Tuple[bool, str | None]:
    """
    Validate CV text: non-empty, <50KB.

    Args:
        text: Raw CV text

    Returns:
        Tuple of (is_valid: bool, error_message: str | None)
        - If valid: (True, None)
        - If invalid: (False, error_message_string)

    Example:
        >>> is_valid, error = validate_cv_text("")
        >>> is_valid
        False
        >>> is_valid, error = validate_cv_text("Valid CV text")
        >>> is_valid
        True
    """
    if not text or not text.strip():
        return False, "CV text cannot be empty"

    # Check size: <50KB (50 * 1024 bytes)
    size_bytes = len(text.encode("utf-8"))
    max_size_bytes = 50 * 1024

    if size_bytes > max_size_bytes:
        size_kb = size_bytes / 1024
        return False, f"CV text exceeds 50KB limit (actual: {size_kb:.1f}KB)"

    return True, None


def validate_roles_list(roles: List[str]) -> Tuple[bool, str | None]:
    """
    Validate cargosActivos: 1-10 items, each ≤50 chars, non-empty.

    Args:
        roles: List of role strings

    Returns:
        Tuple of (is_valid: bool, error_message: str | None)
        - If valid: (True, None)
        - If invalid: (False, error_message_string)

    Example:
        >>> is_valid, error = validate_roles_list([])
        >>> is_valid
        False
        >>> is_valid, error = validate_roles_list(["Role1", "Role2"])
        >>> is_valid
        True
        >>> is_valid, error = validate_roles_list(["A" * 51])
        >>> is_valid
        False
    """
    # Check count: 1-10 items (note: empty list is invalid)
    if not isinstance(roles, list):
        return False, "Roles must be a list"

    if len(roles) == 0:
        return False, "At least one role must be specified"

    if len(roles) > 10:
        return False, f"Maximum 10 roles allowed (actual: {len(roles)})"

    # Validate each role
    for idx, role in enumerate(roles):
        if not isinstance(role, str):
            return False, f"Role at index {idx} is not a string"

        if not role or not role.strip():
            return False, f"Role at index {idx} cannot be empty"

        if len(role) > 50:
            return False, f"Role at index {idx} exceeds 50 character limit (actual: {len(role)})"

    return True, None


def validate_empresa_url(url: str) -> Tuple[bool, str | None]:
    """
    Validate company URL format: http/https, non-empty.

    Args:
        url: Company careers URL

    Returns:
        Tuple of (is_valid: bool, error_message: str | None)
        - If valid: (True, None)
        - If invalid: (False, error_message_string)

    Example:
        >>> is_valid, error = validate_empresa_url("https://example.com/careers")
        >>> is_valid
        True
        >>> is_valid, error = validate_empresa_url("invalid")
        >>> is_valid
        False
    """
    if not url or not url.strip():
        return False, "URL cannot be empty"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Failed to parse URL: {e}"

    # Check scheme is http or https
    if parsed.scheme not in ("http", "https"):
        return False, "URL must use http or https scheme"

    # Check netloc (hostname) is present
    if not parsed.netloc:
        return False, "URL must have a valid hostname"

    return True, None
