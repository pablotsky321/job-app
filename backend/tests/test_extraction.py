"""
Unit tests for backend/shared/extraction.py.

Validates:
- normalize_url: lowercase scheme/host, remove fragment, remove trailing slash
- compute_vacancyId: deterministic, 64 hex chars, normalizes case and fragments
- VacancyExtracted and ExtractionResult models

Requirements: 1.1
"""

from backend.shared.extraction import (
    VacancyExtracted,
    ExtractionResult,
    compute_vacancyId,
    normalize_url,
)


# =============================================================================
# normalize_url tests
# =============================================================================


class TestNormalizeUrl:
    def test_lowercases_scheme(self):
        assert normalize_url("HTTPS://example.com/path") == "https://example.com/path"

    def test_lowercases_host(self):
        assert normalize_url("https://Example.COM/path") == "https://example.com/path"

    def test_lowercases_scheme_and_host(self):
        assert normalize_url("HTTP://Example.COM/path") == "http://example.com/path"

    def test_removes_fragment(self):
        assert normalize_url("https://example.com/jobs#apply") == "https://example.com/jobs"

    def test_removes_trailing_slash(self):
        assert normalize_url("https://example.com/jobs/") == "https://example.com/jobs"

    def test_removes_fragment_and_trailing_slash(self):
        result = normalize_url("https://Example.COM/jobs/#section")
        assert result == "https://example.com/jobs"

    def test_preserves_path_case(self):
        # Path is NOT lowercased — only scheme and host are
        assert normalize_url("https://example.com/Jobs/Senior") == "https://example.com/Jobs/Senior"

    def test_preserves_query_params(self):
        result = normalize_url("https://example.com/jobs?page=2&sort=date")
        assert result == "https://example.com/jobs?page=2&sort=date"

    def test_empty_path(self):
        result = normalize_url("https://example.com")
        assert result == "https://example.com"

    def test_http_and_https_produce_different_results(self):
        http = normalize_url("http://example.com/jobs")
        https = normalize_url("https://example.com/jobs")
        assert http != https


# =============================================================================
# compute_vacancyId tests
# =============================================================================


class TestComputeVacancyId:
    def test_returns_64_hex_chars(self):
        result = compute_vacancyId("https://example.com/jobs/123")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_lowercase_output(self):
        result = compute_vacancyId("https://example.com/jobs/123")
        assert result == result.lower()

    def test_deterministic_same_url(self):
        url = "https://boards.greenhouse.io/company/jobs/12345"
        assert compute_vacancyId(url) == compute_vacancyId(url)

    def test_normalizes_case_in_host(self):
        # Example.COM and example.com should produce same hash
        id1 = compute_vacancyId("https://Example.COM/jobs/123")
        id2 = compute_vacancyId("https://example.com/jobs/123")
        assert id1 == id2

    def test_normalizes_https_http_scheme_case(self):
        # HTTPS and https should produce same hash
        id1 = compute_vacancyId("HTTPS://example.com/jobs/123")
        id2 = compute_vacancyId("https://example.com/jobs/123")
        assert id1 == id2

    def test_normalizes_fragment_removal(self):
        # With and without fragment should produce same hash
        id1 = compute_vacancyId("https://example.com/jobs/123#apply")
        id2 = compute_vacancyId("https://example.com/jobs/123")
        assert id1 == id2

    def test_normalizes_trailing_slash(self):
        # With and without trailing slash should produce same hash
        id1 = compute_vacancyId("https://example.com/jobs/123/")
        id2 = compute_vacancyId("https://example.com/jobs/123")
        assert id1 == id2

    def test_different_urls_produce_different_ids(self):
        id1 = compute_vacancyId("https://example.com/jobs/123")
        id2 = compute_vacancyId("https://example.com/jobs/456")
        assert id1 != id2

    def test_different_schemes_produce_different_ids(self):
        # http vs https are different protocols, different IDs
        id1 = compute_vacancyId("http://example.com/jobs/123")
        id2 = compute_vacancyId("https://example.com/jobs/123")
        assert id1 != id2


# =============================================================================
# VacancyExtracted model tests
# =============================================================================


class TestVacancyExtracted:
    def test_minimal_required_fields(self):
        v = VacancyExtracted(titulo="Software Engineer", url="https://example.com/job/1")
        assert v.titulo == "Software Engineer"
        assert v.url == "https://example.com/job/1"
        assert v.descripcion == ""
        assert v.modalidad == "sin_dato"
        assert v.ubicacion == ""

    def test_all_fields(self):
        v = VacancyExtracted(
            titulo="Backend Dev",
            descripcion="Build APIs",
            url="https://example.com/job/2",
            modalidad="remote",
            ubicacion="LATAM",
        )
        assert v.titulo == "Backend Dev"
        assert v.descripcion == "Build APIs"
        assert v.modalidad == "remote"
        assert v.ubicacion == "LATAM"

    def test_extra_fields_ignored(self):
        v = VacancyExtracted(
            titulo="Dev",
            url="https://example.com/job/3",
            unknown_field="should be ignored",
        )
        assert v.titulo == "Dev"
        assert not hasattr(v, "unknown_field")


# =============================================================================
# ExtractionResult model tests
# =============================================================================


class TestExtractionResult:
    def test_successful_result(self):
        vacancies = [
            VacancyExtracted(titulo="Dev", url="https://example.com/job/1"),
            VacancyExtracted(titulo="PM", url="https://example.com/job/2"),
        ]
        result = ExtractionResult(vacancies=vacancies, origen="board_api")
        assert len(result.vacancies) == 2
        assert result.origen == "board_api"
        assert result.error is None

    def test_error_result(self):
        result = ExtractionResult(
            vacancies=[],
            origen="json_ld",
            error="HTTP 500 from server",
        )
        assert len(result.vacancies) == 0
        assert result.origen == "json_ld"
        assert result.error == "HTTP 500 from server"

    def test_default_empty_vacancies(self):
        result = ExtractionResult(origen="html_llm")
        assert result.vacancies == []
        assert result.error is None

    def test_extra_fields_ignored(self):
        result = ExtractionResult(
            origen="board_api",
            extra_field="ignored",
        )
        assert result.origen == "board_api"
        assert not hasattr(result, "extra_field")
