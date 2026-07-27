"""
Unit tests for backend/shared/validators.py pure functions.

Tests cover:
- URL normalization (scheme/host lowercasing, fragment removal, trailing slash)
- Company ID computation (SHA-256 hash, deterministic)
- Platform detection (hostname-only check for greenhouse/lever/html)
- CV text validation (non-empty, size limit <50KB)
- Roles list validation (1-10 items, ≤50 chars each)
- Company URL format validation (http/https, non-empty)

Requirements: 7.2, 7.3, 7.4, 1.1, 1.5, 5.1, 7.1
"""

import pytest
from backend.shared.validators import (
    normalize_url,
    compute_company_id,
    detect_platform_hostname_only,
    validate_cv_text,
    validate_roles_list,
    validate_empresa_url,
)


# ============================================================================
# normalize_url tests
# ============================================================================


class TestNormalizeUrl:
    """Test normalize_url function."""

    def test_normalize_url_lowercase_scheme(self):
        """Test that scheme is lowercased."""
        assert normalize_url("HTTPS://example.com/careers") == "https://example.com/careers"
        assert normalize_url("HTTP://example.com/careers") == "http://example.com/careers"

    def test_normalize_url_lowercase_host(self):
        """Test that hostname is lowercased."""
        assert normalize_url("https://EXAMPLE.COM/careers") == "https://example.com/careers"
        assert normalize_url("https://Example.Com/careers") == "https://example.com/careers"

    def test_normalize_url_remove_fragment(self):
        """Test that URL fragments are removed."""
        assert (
            normalize_url("https://example.com/careers/#jobs") == "https://example.com/careers"
        )
        assert (
            normalize_url("https://example.com/careers#section") == "https://example.com/careers"
        )

    def test_normalize_url_remove_trailing_slash(self):
        """Test that trailing slashes are removed."""
        assert normalize_url("https://example.com/careers/") == "https://example.com/careers"
        assert normalize_url("https://example.com/") == "https://example.com"

    def test_normalize_url_preserve_path_structure(self):
        """Test that path structure is preserved (except trailing /)."""
        assert (
            normalize_url("https://example.com/careers/openings") == "https://example.com/careers/openings"
        )
        assert (
            normalize_url("https://example.com/a/b/c/") == "https://example.com/a/b/c"
        )

    def test_normalize_url_mixed_transformations(self):
        """Test combining multiple normalizations."""
        url = "HTTPS://EXAMPLE.COM/careers/#jobs"
        assert normalize_url(url) == "https://example.com/careers"

    def test_normalize_url_missing_scheme(self):
        """Test that missing scheme raises ValueError."""
        with pytest.raises(ValueError, match="scheme"):
            normalize_url("example.com/careers")

    def test_normalize_url_missing_hostname(self):
        """Test that missing hostname raises ValueError."""
        with pytest.raises(ValueError, match="hostname"):
            normalize_url("https://")

    def test_normalize_url_empty_string(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError):
            normalize_url("")

    def test_normalize_url_preserves_query_string(self):
        """Test that query parameters are preserved."""
        assert (
            normalize_url("https://example.com/careers?page=1") == "https://example.com/careers?page=1"
        )

    def test_normalize_url_idempotent(self):
        """Test that normalizing twice produces same result (idempotent)."""
        url = "HTTPS://EXAMPLE.COM/careers/#jobs"
        first_pass = normalize_url(url)
        second_pass = normalize_url(first_pass)
        assert first_pass == second_pass


# ============================================================================
# compute_company_id tests
# ============================================================================


class TestComputeCompanyId:
    """Test compute_company_id function."""

    def test_compute_company_id_returns_64_hex_chars(self):
        """Test that company ID is 64-character hexadecimal string."""
        company_id = compute_company_id("https://example.com/careers")
        assert len(company_id) == 64
        assert all(c in "0123456789abcdef" for c in company_id)

    def test_compute_company_id_deterministic(self):
        """Test that same URL always produces same hash."""
        url = "https://example.com/careers"
        id1 = compute_company_id(url)
        id2 = compute_company_id(url)
        id3 = compute_company_id(url)
        assert id1 == id2 == id3

    def test_compute_company_id_different_urls_different_hashes(self):
        """Test that different URLs produce different hashes."""
        id1 = compute_company_id("https://example.com/careers")
        id2 = compute_company_id("https://different.com/careers")
        assert id1 != id2

    def test_compute_company_id_normalized_equivalence(self):
        """Test that equivalent URLs (after normalization) have same hash."""
        # These should normalize to the same URL and thus same hash
        url1 = "HTTPS://EXAMPLE.COM/careers#jobs"
        url2 = "https://example.com/careers/"
        id1 = compute_company_id(url1)
        id2 = compute_company_id(url2)
        assert id1 == id2

    def test_compute_company_id_malformed_url(self):
        """Test that malformed URL raises ValueError."""
        with pytest.raises(ValueError):
            compute_company_id("not a valid url")

    def test_compute_company_id_missing_scheme(self):
        """Test that URL without scheme raises ValueError."""
        with pytest.raises(ValueError):
            compute_company_id("example.com/careers")


# ============================================================================
# detect_platform_hostname_only tests
# ============================================================================


class TestDetectPlatformHostnameOnly:
    """Test detect_platform_hostname_only function."""

    def test_detect_platform_greenhouse(self):
        """Test detection of Greenhouse URLs."""
        assert detect_platform_hostname_only("https://company.greenhouse.io/jobs") == "greenhouse"
        assert (
            detect_platform_hostname_only("https://COMPANY.GREENHOUSE.IO/careers") == "greenhouse"
        )
        assert detect_platform_hostname_only("https://example.greenhouse.com") == "greenhouse"

    def test_detect_platform_lever(self):
        """Test detection of Lever URLs."""
        assert detect_platform_hostname_only("https://company.lever.co/careers") == "lever"
        assert detect_platform_hostname_only("https://COMPANY.LEVER.CO/jobs") == "lever"
        assert detect_platform_hostname_only("https://example.lever.com") == "lever"

    def test_detect_platform_html(self):
        """Test detection of generic HTML URLs (neither greenhouse nor lever)."""
        assert detect_platform_hostname_only("https://example.com/careers") == "html"
        assert detect_platform_hostname_only("https://company.org/jobs") == "html"
        assert detect_platform_hostname_only("https://jobs.example.io") == "html"

    def test_detect_platform_greenhouse_priority(self):
        """Test that greenhouse takes priority if both keywords in hostname."""
        # (unlikely in practice, but greenhouse check comes first)
        assert (
            detect_platform_hostname_only("https://company.greenhouse.lever.com") == "greenhouse"
        )

    def test_detect_platform_missing_scheme(self):
        """Test that missing scheme raises ValueError."""
        with pytest.raises(ValueError, match="scheme"):
            detect_platform_hostname_only("example.com/careers")

    def test_detect_platform_missing_hostname(self):
        """Test that missing hostname raises ValueError."""
        with pytest.raises(ValueError, match="hostname"):
            detect_platform_hostname_only("https://")

    def test_detect_platform_case_insensitive(self):
        """Test that platform detection is case-insensitive."""
        assert detect_platform_hostname_only("https://COMPANY.GREENHOUSE.IO") == "greenhouse"
        assert detect_platform_hostname_only("https://company.Lever.co") == "lever"
        assert detect_platform_hostname_only("https://Example.Com") == "html"

    def test_detect_platform_empty_string(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError):
            detect_platform_hostname_only("")


# ============================================================================
# validate_cv_text tests
# ============================================================================


class TestValidateCvText:
    """Test validate_cv_text function."""

    def test_validate_cv_text_valid(self):
        """Test that valid CV text passes validation."""
        is_valid, error = validate_cv_text("Valid CV text with some content")
        assert is_valid is True
        assert error is None

    def test_validate_cv_text_empty_string(self):
        """Test that empty string fails validation."""
        is_valid, error = validate_cv_text("")
        assert is_valid is False
        assert error is not None
        assert "empty" in error.lower()

    def test_validate_cv_text_whitespace_only(self):
        """Test that whitespace-only string fails validation."""
        is_valid, error = validate_cv_text("   ")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_validate_cv_text_exceeds_50kb(self):
        """Test that CV larger than 50KB fails validation."""
        # Create a string larger than 50KB
        large_text = "x" * (50 * 1024 + 1)
        is_valid, error = validate_cv_text(large_text)
        assert is_valid is False
        assert "50KB" in error or "50" in error

    def test_validate_cv_text_exactly_50kb(self):
        """Test that CV exactly 50KB passes validation."""
        # Create a string exactly 50KB
        text = "x" * (50 * 1024)
        is_valid, error = validate_cv_text(text)
        assert is_valid is True
        assert error is None

    def test_validate_cv_text_just_under_50kb(self):
        """Test that CV just under 50KB passes validation."""
        text = "x" * (50 * 1024 - 10)
        is_valid, error = validate_cv_text(text)
        assert is_valid is True
        assert error is None

    def test_validate_cv_text_unicode_characters(self):
        """Test that UTF-8 encoded unicode characters are counted in byte size."""
        # Unicode characters (emoji, accents) take multiple bytes
        text = "x" * (25 * 1024) + "🚀" * (12 * 1024)  # emoji takes 4 bytes each
        is_valid, error = validate_cv_text(text)
        # Should fail because emoji take multiple bytes
        assert is_valid is False

    def test_validate_cv_text_short_valid(self):
        """Test short CV text."""
        is_valid, error = validate_cv_text("Senior Engineer at Company X, 5 years experience")
        assert is_valid is True
        assert error is None


# ============================================================================
# validate_roles_list tests
# ============================================================================


class TestValidateRolesList:
    """Test validate_roles_list function."""

    def test_validate_roles_list_valid_single(self):
        """Test valid list with single role."""
        is_valid, error = validate_roles_list(["Software Engineer"])
        assert is_valid is True
        assert error is None

    def test_validate_roles_list_valid_multiple(self):
        """Test valid list with multiple roles."""
        is_valid, error = validate_roles_list(["Software Engineer", "DevOps Engineer", "Data Scientist"])
        assert is_valid is True
        assert error is None

    def test_validate_roles_list_valid_max_10(self):
        """Test valid list with exactly 10 roles (max)."""
        roles = [f"Role {i}" for i in range(1, 11)]
        is_valid, error = validate_roles_list(roles)
        assert is_valid is True
        assert error is None

    def test_validate_roles_list_empty_list(self):
        """Test that empty list fails validation."""
        is_valid, error = validate_roles_list([])
        assert is_valid is False
        assert "empty" in error.lower() or "at least" in error.lower()

    def test_validate_roles_list_exceeds_10(self):
        """Test that list with more than 10 items fails validation."""
        roles = [f"Role {i}" for i in range(1, 12)]  # 11 items
        is_valid, error = validate_roles_list(roles)
        assert is_valid is False
        assert "10" in error

    def test_validate_roles_list_role_too_long(self):
        """Test that role exceeding 50 chars fails validation."""
        roles = ["Short Role", "x" * 51]  # Second role is 51 chars
        is_valid, error = validate_roles_list(roles)
        assert is_valid is False
        assert "50" in error

    def test_validate_roles_list_role_exactly_50_chars(self):
        """Test that role with exactly 50 chars passes validation."""
        roles = ["x" * 50]
        is_valid, error = validate_roles_list(roles)
        assert is_valid is True
        assert error is None

    def test_validate_roles_list_empty_role_string(self):
        """Test that empty role string in list fails validation."""
        roles = ["Valid Role", ""]
        is_valid, error = validate_roles_list(roles)
        assert is_valid is False
        assert "empty" in error.lower()

    def test_validate_roles_list_whitespace_role(self):
        """Test that whitespace-only role string fails validation."""
        roles = ["Valid Role", "   "]
        is_valid, error = validate_roles_list(roles)
        assert is_valid is False

    def test_validate_roles_list_non_string_item(self):
        """Test that non-string item in list fails validation."""
        roles = ["Valid Role", 123]
        is_valid, error = validate_roles_list(roles)
        assert is_valid is False
        assert "string" in error.lower()

    def test_validate_roles_list_not_a_list(self):
        """Test that non-list input fails validation."""
        is_valid, error = validate_roles_list("NotAList")
        assert is_valid is False
        assert "list" in error.lower()


# ============================================================================
# validate_empresa_url tests
# ============================================================================


class TestValidateEmpresaUrl:
    """Test validate_empresa_url function."""

    def test_validate_empresa_url_valid_https(self):
        """Test valid HTTPS URL."""
        is_valid, error = validate_empresa_url("https://example.com/careers")
        assert is_valid is True
        assert error is None

    def test_validate_empresa_url_valid_http(self):
        """Test valid HTTP URL."""
        is_valid, error = validate_empresa_url("http://example.com/careers")
        assert is_valid is True
        assert error is None

    def test_validate_empresa_url_empty_string(self):
        """Test that empty string fails validation."""
        is_valid, error = validate_empresa_url("")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_validate_empresa_url_invalid_scheme(self):
        """Test that invalid scheme fails validation."""
        is_valid, error = validate_empresa_url("ftp://example.com/careers")
        assert is_valid is False
        assert "http" in error.lower()

    def test_validate_empresa_url_missing_scheme(self):
        """Test that URL without scheme fails validation."""
        is_valid, error = validate_empresa_url("example.com/careers")
        assert is_valid is False
        assert "http" in error.lower() or "scheme" in error.lower()

    def test_validate_empresa_url_missing_hostname(self):
        """Test that URL without hostname fails validation."""
        is_valid, error = validate_empresa_url("https://")
        assert is_valid is False
        assert "hostname" in error.lower()

    def test_validate_empresa_url_with_path(self):
        """Test valid URL with complex path."""
        is_valid, error = validate_empresa_url("https://example.com/careers/open-positions")
        assert is_valid is True
        assert error is None

    def test_validate_empresa_url_with_query_params(self):
        """Test valid URL with query parameters."""
        is_valid, error = validate_empresa_url("https://example.com/careers?dept=engineering")
        assert is_valid is True
        assert error is None

    def test_validate_empresa_url_with_fragment(self):
        """Test valid URL with fragment."""
        is_valid, error = validate_empresa_url("https://example.com/careers#jobs")
        assert is_valid is True
        assert error is None

    def test_validate_empresa_url_case_insensitive_scheme(self):
        """Test that HTTPS (uppercase) works correctly."""
        is_valid, error = validate_empresa_url("HTTPS://example.com/careers")
        assert is_valid is True
        assert error is None

    def test_validate_empresa_url_whitespace_only(self):
        """Test that whitespace-only string fails validation."""
        is_valid, error = validate_empresa_url("   ")
        assert is_valid is False
        assert "empty" in error.lower()
