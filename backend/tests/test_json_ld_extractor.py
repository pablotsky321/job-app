"""
Tests for JSON-LD Extractor.

Pure HTML parsing tests without boto3. HTTP responses are mocked.
Tests cover:
- Standalone JobPosting objects
- Arrays of JobPosting objects
- @graph nesting
- HTTP errors (4xx/5xx), timeouts, connection errors
- Missing ld+json blocks → zero vacancies
- JobPosting without URL or title → excluded without error
- modalidad defaults to 'sin_dato' when not specified

Requirements: 4.1-4.5, 2.8
"""

from unittest.mock import patch, MagicMock
import json

import pytest

from backend.shared.json_ld_extractor import (
    json_ld_extractor,
    _extract_job_postings_from_data,
    _map_job_posting_to_vacancy,
    _map_modalidad,
    _extract_ubicacion,
)
from backend.shared.extraction import VacancyExtracted
from backend.shared.models import Empresa, PlatformaEnum


def _make_empresa(careers_url="https://example.com/careers") -> Empresa:
    """Helper to create a test Empresa."""
    from datetime import datetime

    return Empresa(
        companyId="a" * 64,
        nombre="Test Company",
        careersUrl=careers_url,
        plataforma=PlatformaEnum.JSONLD,
        createdAt=datetime(2024, 1, 1),
    )


def _make_response(status_code: int, html: str) -> MagicMock:
    """Create a mock requests.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = html
    return mock_resp


def _html_with_json_ld(json_data) -> str:
    """Create an HTML page with a single ld+json script block."""
    json_str = json.dumps(json_data)
    return f"""
    <html>
    <head>
        <script type="application/ld+json">{json_str}</script>
    </head>
    <body><h1>Careers</h1></body>
    </html>
    """


def _html_with_multiple_json_ld(json_data_list: list) -> str:
    """Create an HTML page with multiple ld+json script blocks."""
    scripts = ""
    for data in json_data_list:
        scripts += f'<script type="application/ld+json">{json.dumps(data)}</script>\n'
    return f"<html><head>{scripts}</head><body></body></html>"


# ---------------------------------------------------------------------------
# Tests: _extract_job_postings_from_data
# ---------------------------------------------------------------------------


class TestExtractJobPostingsFromData:
    """Tests for extracting JobPosting objects from parsed JSON-LD data."""

    def test_standalone_job_posting(self):
        data = {"@type": "JobPosting", "title": "Dev", "url": "https://x.com/j/1"}
        result = _extract_job_postings_from_data(data)
        assert len(result) == 1
        assert result[0]["title"] == "Dev"

    def test_array_of_job_postings(self):
        data = [
            {"@type": "JobPosting", "title": "Dev1", "url": "https://x.com/j/1"},
            {"@type": "JobPosting", "title": "Dev2", "url": "https://x.com/j/2"},
        ]
        result = _extract_job_postings_from_data(data)
        assert len(result) == 2

    def test_graph_nesting(self):
        data = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "JobPosting", "title": "Dev1", "url": "https://x.com/j/1"},
                {"@type": "Organization", "name": "Corp"},
                {"@type": "JobPosting", "title": "Dev2", "url": "https://x.com/j/2"},
            ],
        }
        result = _extract_job_postings_from_data(data)
        assert len(result) == 2
        assert result[0]["title"] == "Dev1"
        assert result[1]["title"] == "Dev2"

    def test_non_job_posting_objects_ignored(self):
        data = {"@type": "Organization", "name": "Corp"}
        result = _extract_job_postings_from_data(data)
        assert len(result) == 0

    def test_job_posting_with_type_as_list(self):
        data = {"@type": ["JobPosting", "Thing"], "title": "Dev", "url": "https://x.com/j/1"}
        result = _extract_job_postings_from_data(data)
        assert len(result) == 1

    def test_empty_graph(self):
        data = {"@graph": []}
        result = _extract_job_postings_from_data(data)
        assert len(result) == 0

    def test_mixed_array(self):
        data = [
            {"@type": "JobPosting", "title": "Dev", "url": "https://x.com/j/1"},
            {"@type": "Organization", "name": "Corp"},
            {"@type": "BreadcrumbList"},
        ]
        result = _extract_job_postings_from_data(data)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Tests: _map_modalidad
# ---------------------------------------------------------------------------


class TestMapModalidad:
    """Tests for mapping employmentType to modalidad."""

    def test_no_employment_type_returns_sin_dato(self):
        assert _map_modalidad({}) == "sin_dato"

    def test_telecommute_job_location_type(self):
        assert _map_modalidad({"jobLocationType": "TELECOMMUTE"}) == "remoto"

    def test_remote_employment_type_string(self):
        assert _map_modalidad({"employmentType": "REMOTE"}) == "remoto"

    def test_remote_in_list(self):
        assert _map_modalidad({"employmentType": ["FULL_TIME", "REMOTE"]}) == "remoto"

    def test_full_time_only_returns_sin_dato(self):
        assert _map_modalidad({"employmentType": "FULL_TIME"}) == "sin_dato"

    def test_part_time_returns_sin_dato(self):
        assert _map_modalidad({"employmentType": "PART_TIME"}) == "sin_dato"


# ---------------------------------------------------------------------------
# Tests: _extract_ubicacion
# ---------------------------------------------------------------------------


class TestExtractUbicacion:
    """Tests for extracting location from JobPosting."""

    def test_no_job_location(self):
        assert _extract_ubicacion({}) == ""

    def test_string_location(self):
        """If jobLocation is a plain string, treat it as the location."""
        assert _extract_ubicacion({"jobLocation": "Remote"}) == "Remote"

    def test_place_with_address_object(self):
        data = {
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "San Francisco",
                    "addressRegion": "CA",
                    "addressCountry": "US",
                },
            }
        }
        result = _extract_ubicacion(data)
        assert "San Francisco" in result
        assert "CA" in result
        assert "US" in result

    def test_place_with_address_string(self):
        data = {
            "jobLocation": {
                "@type": "Place",
                "address": "New York, NY",
            }
        }
        assert _extract_ubicacion(data) == "New York, NY"

    def test_place_with_name_only(self):
        data = {"jobLocation": {"@type": "Place", "name": "London Office"}}
        assert _extract_ubicacion(data) == "London Office"

    def test_multiple_locations(self):
        data = {
            "jobLocation": [
                {"@type": "Place", "name": "NYC"},
                {"@type": "Place", "name": "SF"},
            ]
        }
        result = _extract_ubicacion(data)
        assert "NYC" in result
        assert "SF" in result


# ---------------------------------------------------------------------------
# Tests: _map_job_posting_to_vacancy
# ---------------------------------------------------------------------------


class TestMapJobPostingToVacancy:
    """Tests for mapping a single JobPosting to VacancyExtracted."""

    def test_valid_posting_with_title_and_url(self):
        posting = {
            "@type": "JobPosting",
            "title": "Software Engineer",
            "url": "https://example.com/jobs/1",
            "description": "Build stuff",
        }
        result = _map_job_posting_to_vacancy(posting)
        assert result is not None
        assert result.titulo == "Software Engineer"
        assert result.url == "https://example.com/jobs/1"
        assert result.descripcion == "Build stuff"
        assert result.modalidad == "sin_dato"

    def test_posting_with_name_instead_of_title(self):
        """Some sites use 'name' instead of 'title'."""
        posting = {
            "@type": "JobPosting",
            "name": "Backend Dev",
            "url": "https://example.com/jobs/2",
        }
        result = _map_job_posting_to_vacancy(posting)
        assert result is not None
        assert result.titulo == "Backend Dev"

    def test_posting_without_title_excluded(self):
        """Requirement 4.5: No title → exclude."""
        posting = {"@type": "JobPosting", "url": "https://example.com/jobs/1"}
        result = _map_job_posting_to_vacancy(posting)
        assert result is None

    def test_posting_without_url_excluded(self):
        """Requirement 4.5: No URL → exclude."""
        posting = {"@type": "JobPosting", "title": "Dev"}
        result = _map_job_posting_to_vacancy(posting)
        assert result is None

    def test_posting_with_empty_title_excluded(self):
        posting = {"@type": "JobPosting", "title": "   ", "url": "https://x.com/j/1"}
        result = _map_job_posting_to_vacancy(posting)
        assert result is None

    def test_posting_with_empty_url_excluded(self):
        posting = {"@type": "JobPosting", "title": "Dev", "url": ""}
        result = _map_job_posting_to_vacancy(posting)
        assert result is None

    def test_modalidad_defaults_sin_dato(self):
        """Requirement 4.4: modalidad = 'sin_dato' when not specified."""
        posting = {
            "@type": "JobPosting",
            "title": "Dev",
            "url": "https://x.com/j/1",
        }
        result = _map_job_posting_to_vacancy(posting)
        assert result.modalidad == "sin_dato"

    def test_posting_with_sameAs_as_url(self):
        """Falls back to sameAs when url is missing."""
        posting = {
            "@type": "JobPosting",
            "title": "Dev",
            "sameAs": "https://x.com/j/1",
        }
        result = _map_job_posting_to_vacancy(posting)
        assert result is not None
        assert result.url == "https://x.com/j/1"


# ---------------------------------------------------------------------------
# Tests: json_ld_extractor (integration with mocked HTTP)
# ---------------------------------------------------------------------------


class TestJsonLdExtractor:
    """Integration tests for the full json_ld_extractor function."""

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_successful_extraction_standalone(self, mock_get):
        """Requirement 4.1: Fetch, locate JobPosting, extract vacancies."""
        html = _html_with_json_ld({
            "@type": "JobPosting",
            "title": "Senior Dev",
            "url": "https://example.com/jobs/senior-dev",
            "description": "We need a senior developer",
        })
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert result.origen == "json_ld"
        assert len(result.vacancies) == 1
        assert result.vacancies[0].titulo == "Senior Dev"
        assert result.vacancies[0].url == "https://example.com/jobs/senior-dev"

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_successful_extraction_array(self, mock_get):
        """Requirement 4.1: Handle array of JobPostings."""
        html = _html_with_json_ld([
            {"@type": "JobPosting", "title": "Dev1", "url": "https://x.com/j/1"},
            {"@type": "JobPosting", "title": "Dev2", "url": "https://x.com/j/2"},
        ])
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert len(result.vacancies) == 2

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_successful_extraction_graph(self, mock_get):
        """Requirement 4.1: Handle @graph nesting."""
        html = _html_with_json_ld({
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "Organization", "name": "Corp"},
                {"@type": "JobPosting", "title": "Dev", "url": "https://x.com/j/1"},
            ],
        })
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert len(result.vacancies) == 1
        assert result.vacancies[0].titulo == "Dev"

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_timeout_returns_error(self, mock_get):
        """Requirement 4.2: Timeout → error."""
        import requests as req_lib

        mock_get.side_effect = req_lib.exceptions.Timeout("timed out")

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error == "timeout_fetching_careers_url"
        assert result.origen == "json_ld"
        assert len(result.vacancies) == 0

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_connection_error_returns_error(self, mock_get):
        """Requirement 4.2: Connection error → error."""
        import requests as req_lib

        mock_get.side_effect = req_lib.exceptions.ConnectionError("refused")

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error == "connection_error"
        assert result.origen == "json_ld"
        assert len(result.vacancies) == 0

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_http_404_returns_error(self, mock_get):
        """Requirement 4.2: HTTP 4xx → error."""
        mock_get.return_value = _make_response(404, "Not Found")

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error == "http_error_404"
        assert len(result.vacancies) == 0

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_http_500_returns_error(self, mock_get):
        """Requirement 4.2: HTTP 5xx → error."""
        mock_get.return_value = _make_response(500, "Server Error")

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error == "http_error_500"
        assert len(result.vacancies) == 0

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_no_json_ld_blocks_returns_zero_vacancies(self, mock_get):
        """Requirement 4.3: No ld+json blocks → zero vacancies, no error."""
        html = "<html><body><h1>Careers</h1><p>No jobs here</p></body></html>"
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert result.origen == "json_ld"
        assert len(result.vacancies) == 0

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_json_ld_without_job_posting_returns_zero(self, mock_get):
        """Requirement 4.3: ld+json blocks but no JobPosting → zero vacancies."""
        html = _html_with_json_ld({"@type": "Organization", "name": "Corp"})
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert len(result.vacancies) == 0

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_malformed_json_ld_returns_zero(self, mock_get):
        """Malformed JSON in ld+json block → zero vacancies (no error)."""
        html = '<html><head><script type="application/ld+json">{ invalid json }</script></head></html>'
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert len(result.vacancies) == 0

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_posting_without_title_excluded(self, mock_get):
        """Requirement 4.5: JobPosting without title → excluded."""
        html = _html_with_json_ld({
            "@type": "JobPosting",
            "url": "https://x.com/j/1",
            "description": "No title here",
        })
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert len(result.vacancies) == 0

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_posting_without_url_excluded(self, mock_get):
        """Requirement 4.5: JobPosting without URL → excluded."""
        html = _html_with_json_ld({
            "@type": "JobPosting",
            "title": "Dev",
        })
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert len(result.vacancies) == 0

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_mixed_valid_and_invalid_postings(self, mock_get):
        """Valid postings extracted, invalid ones excluded without error."""
        html = _html_with_json_ld([
            {"@type": "JobPosting", "title": "Dev", "url": "https://x.com/j/1"},
            {"@type": "JobPosting", "title": "", "url": "https://x.com/j/2"},  # Empty title
            {"@type": "JobPosting", "title": "PM"},  # No URL
            {"@type": "JobPosting", "title": "QA", "url": "https://x.com/j/3"},
        ])
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert len(result.vacancies) == 2
        assert result.vacancies[0].titulo == "Dev"
        assert result.vacancies[1].titulo == "QA"

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_multiple_ld_json_blocks(self, mock_get):
        """Handle multiple ld+json blocks in the same page."""
        html = _html_with_multiple_json_ld([
            {"@type": "Organization", "name": "Corp"},
            {"@type": "JobPosting", "title": "Dev", "url": "https://x.com/j/1"},
            [
                {"@type": "JobPosting", "title": "PM", "url": "https://x.com/j/2"},
            ],
        ])
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.error is None
        assert len(result.vacancies) == 2

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_modalidad_sin_dato_default(self, mock_get):
        """Requirement 4.4: modalidad defaults to 'sin_dato'."""
        html = _html_with_json_ld({
            "@type": "JobPosting",
            "title": "Dev",
            "url": "https://x.com/j/1",
            "employmentType": "FULL_TIME",
        })
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.vacancies[0].modalidad == "sin_dato"

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_modalidad_remote_telecommute(self, mock_get):
        """Remote job detected via jobLocationType TELECOMMUTE."""
        html = _html_with_json_ld({
            "@type": "JobPosting",
            "title": "Remote Dev",
            "url": "https://x.com/j/1",
            "jobLocationType": "TELECOMMUTE",
        })
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.vacancies[0].modalidad == "remoto"

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_ubicacion_extracted(self, mock_get):
        """Location extracted from jobLocation."""
        html = _html_with_json_ld({
            "@type": "JobPosting",
            "title": "Dev",
            "url": "https://x.com/j/1",
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "Madrid",
                    "addressCountry": "ES",
                },
            },
        })
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert "Madrid" in result.vacancies[0].ubicacion

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_request_uses_10s_timeout(self, mock_get):
        """Verify the request is made with 10 second timeout."""
        html = _html_with_json_ld({
            "@type": "JobPosting",
            "title": "Dev",
            "url": "https://x.com/j/1",
        })
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        json_ld_extractor(empresa)

        mock_get.assert_called_once_with(
            empresa.careersUrl,
            timeout=10,
            headers={"User-Agent": "JobAppBot/1.0"},
        )

    @patch("backend.shared.json_ld_extractor.requests.get")
    def test_origen_is_json_ld(self, mock_get):
        """Requirement 2.8: origen = 'json_ld'."""
        html = _html_with_json_ld({
            "@type": "JobPosting",
            "title": "Dev",
            "url": "https://x.com/j/1",
        })
        mock_get.return_value = _make_response(200, html)

        empresa = _make_empresa()
        result = json_ld_extractor(empresa)

        assert result.origen == "json_ld"
