"""
Unit tests for Board API Client extractor.

Tests cover:
- Greenhouse API: successful extraction, missing URL exclusion
- Lever API: successful extraction, missing URL exclusion
- HTTP error handling (4xx/5xx)
- Timeout handling
- Invalid JSON handling
- Missing boardToken handling

Requirements validated: 3.1-3.6, 2.8
"""

from unittest.mock import patch, MagicMock

import pytest
import requests

from backend.shared.board_api_client import board_api_client
from backend.shared.models import Empresa, PlatformaEnum


def _make_empresa(plataforma: str, board_token: str = "test-token") -> Empresa:
    """Helper to create an Empresa for testing."""
    return Empresa(
        companyId="a" * 64,
        nombre="Test Company",
        careersUrl="https://example.com/careers",
        plataforma=PlatformaEnum(plataforma),
        boardToken=board_token,
    )


class TestGreenhouseExtraction:
    """Tests for Greenhouse board API extraction (Requirement 3.1)."""

    @patch("backend.shared.board_api_client.requests.get")
    def test_successful_extraction(self, mock_get: MagicMock) -> None:
        """Greenhouse API returns jobs wrapped in {jobs: [...]}."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [
                {
                    "title": "Software Engineer",
                    "absolute_url": "https://boards.greenhouse.io/company/jobs/123",
                    "location": {"name": "Remote"},
                },
                {
                    "title": "Product Manager",
                    "absolute_url": "https://boards.greenhouse.io/company/jobs/456",
                    "location": {"name": "New York"},
                },
            ]
        }
        mock_get.return_value = mock_response

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        assert result.error is None
        assert result.origen == "board_api"
        assert len(result.vacancies) == 2
        assert result.vacancies[0].titulo == "Software Engineer"
        assert result.vacancies[0].url == "https://boards.greenhouse.io/company/jobs/123"
        assert result.vacancies[0].modalidad == "sin_dato"
        assert result.vacancies[0].ubicacion == "Remote"
        assert result.vacancies[1].titulo == "Product Manager"

    @patch("backend.shared.board_api_client.requests.get")
    def test_excludes_entries_without_url(self, mock_get: MagicMock) -> None:
        """Requirement 3.6: entries without URL are excluded silently."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [
                {
                    "title": "Software Engineer",
                    "absolute_url": "https://boards.greenhouse.io/company/jobs/123",
                },
                {
                    "title": "No URL Job",
                    "absolute_url": "",
                },
                {
                    "title": "Also No URL",
                    # absolute_url key missing entirely
                },
            ]
        }
        mock_get.return_value = mock_response

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        assert result.error is None
        assert len(result.vacancies) == 1
        assert result.vacancies[0].titulo == "Software Engineer"

    @patch("backend.shared.board_api_client.requests.get")
    def test_modalidad_always_sin_dato(self, mock_get: MagicMock) -> None:
        """Requirement 3.5: modalidad always defaults to sin_dato."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [
                {
                    "title": "Remote Engineer",
                    "absolute_url": "https://boards.greenhouse.io/company/jobs/789",
                    "location": {"name": "Remote"},
                    "employment_type": "FULL_TIME",
                },
            ]
        }
        mock_get.return_value = mock_response

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        assert result.vacancies[0].modalidad == "sin_dato"

    @patch("backend.shared.board_api_client.requests.get")
    def test_empty_jobs_list(self, mock_get: MagicMock) -> None:
        """No jobs in response → empty vacancies, no error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jobs": []}
        mock_get.return_value = mock_response

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        assert result.error is None
        assert result.origen == "board_api"
        assert len(result.vacancies) == 0

    @patch("backend.shared.board_api_client.requests.get")
    def test_uses_correct_endpoint(self, mock_get: MagicMock) -> None:
        """Requirement 3.1: Uses Greenhouse endpoint with boardToken."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jobs": []}
        mock_get.return_value = mock_response

        empresa = _make_empresa("greenhouse", board_token="mycompany")
        board_api_client(empresa)

        mock_get.assert_called_once_with(
            "https://boards-api.greenhouse.io/v1/boards/mycompany/jobs",
            timeout=10,
        )


class TestLeverExtraction:
    """Tests for Lever board API extraction (Requirement 3.2)."""

    @patch("backend.shared.board_api_client.requests.get")
    def test_successful_extraction(self, mock_get: MagicMock) -> None:
        """Lever API returns a flat array of postings."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "text": "Backend Developer",
                "hostedUrl": "https://jobs.lever.co/company/abc-123",
                "categories": {"location": "San Francisco"},
            },
            {
                "text": "Frontend Developer",
                "hostedUrl": "https://jobs.lever.co/company/def-456",
                "categories": {"location": "Remote"},
            },
        ]
        mock_get.return_value = mock_response

        empresa = _make_empresa("lever")
        result = board_api_client(empresa)

        assert result.error is None
        assert result.origen == "board_api"
        assert len(result.vacancies) == 2
        assert result.vacancies[0].titulo == "Backend Developer"
        assert result.vacancies[0].url == "https://jobs.lever.co/company/abc-123"
        assert result.vacancies[0].modalidad == "sin_dato"
        assert result.vacancies[0].ubicacion == "San Francisco"

    @patch("backend.shared.board_api_client.requests.get")
    def test_excludes_entries_without_url(self, mock_get: MagicMock) -> None:
        """Requirement 3.6: entries without hostedUrl are excluded."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "text": "Backend Developer",
                "hostedUrl": "https://jobs.lever.co/company/abc-123",
            },
            {
                "text": "No URL Job",
                "hostedUrl": "",
            },
            {
                "text": "Missing Field",
            },
        ]
        mock_get.return_value = mock_response

        empresa = _make_empresa("lever")
        result = board_api_client(empresa)

        assert result.error is None
        assert len(result.vacancies) == 1
        assert result.vacancies[0].titulo == "Backend Developer"

    @patch("backend.shared.board_api_client.requests.get")
    def test_uses_correct_endpoint(self, mock_get: MagicMock) -> None:
        """Requirement 3.2: Uses Lever endpoint with boardToken."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        empresa = _make_empresa("lever", board_token="mycompany")
        board_api_client(empresa)

        mock_get.assert_called_once_with(
            "https://api.lever.co/v0/postings/mycompany",
            timeout=10,
        )


class TestHttpErrorHandling:
    """Tests for HTTP error handling (Requirement 3.3)."""

    @patch("backend.shared.board_api_client.requests.get")
    def test_http_404(self, mock_get: MagicMock) -> None:
        """HTTP 4xx returns ExtractionResult with error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        assert result.error == "HTTP 404"
        assert result.origen == "board_api"
        assert len(result.vacancies) == 0

    @patch("backend.shared.board_api_client.requests.get")
    def test_http_500(self, mock_get: MagicMock) -> None:
        """HTTP 5xx returns ExtractionResult with error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        assert result.error == "HTTP 500"
        assert len(result.vacancies) == 0

    @patch("backend.shared.board_api_client.requests.get")
    def test_timeout(self, mock_get: MagicMock) -> None:
        """Timeout returns ExtractionResult with error (Requirement 3.3)."""
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        assert result.error == "HTTP request timed out"
        assert result.origen == "board_api"
        assert len(result.vacancies) == 0

    @patch("backend.shared.board_api_client.requests.get")
    def test_connection_error(self, mock_get: MagicMock) -> None:
        """Connection error returns ExtractionResult with error."""
        mock_get.side_effect = requests.exceptions.ConnectionError("DNS resolution failed")

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        assert "Connection error" in result.error
        assert len(result.vacancies) == 0


class TestInvalidJson:
    """Tests for invalid JSON handling (Requirement 3.4)."""

    @patch("backend.shared.board_api_client.requests.get")
    def test_invalid_json_response(self, mock_get: MagicMock) -> None:
        """Non-JSON response body returns error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("No JSON object could be decoded")
        mock_get.return_value = mock_response

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        assert result.error == "Invalid JSON response"
        assert result.origen == "board_api"
        assert len(result.vacancies) == 0

    @patch("backend.shared.board_api_client.requests.get")
    def test_unexpected_json_structure(self, mock_get: MagicMock) -> None:
        """Greenhouse returns unexpected format (no 'jobs' key) → empty list, no error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "format"}
        mock_get.return_value = mock_response

        empresa = _make_empresa("greenhouse")
        result = board_api_client(empresa)

        # No error because JSON parsed successfully, just no jobs found
        assert result.error is None
        assert len(result.vacancies) == 0


class TestMissingBoardToken:
    """Tests for missing boardToken."""

    def test_no_board_token(self) -> None:
        """Missing boardToken returns error without making HTTP call."""
        empresa = Empresa(
            companyId="a" * 64,
            nombre="Test Company",
            careersUrl="https://example.com/careers",
            plataforma=PlatformaEnum.GREENHOUSE,
            boardToken=None,
        )
        result = board_api_client(empresa)

        assert "boardToken is missing" in result.error
        assert result.origen == "board_api"
        assert len(result.vacancies) == 0

    def test_empty_board_token(self) -> None:
        """Empty string boardToken returns error."""
        empresa = Empresa(
            companyId="a" * 64,
            nombre="Test Company",
            careersUrl="https://example.com/careers",
            plataforma=PlatformaEnum.GREENHOUSE,
            boardToken="",
        )
        result = board_api_client(empresa)

        assert "boardToken is missing" in result.error


class TestUnsupportedPlatform:
    """Tests for unsupported platform."""

    def test_html_platform_not_supported(self) -> None:
        """Board API client only supports greenhouse/lever."""
        empresa = Empresa(
            companyId="a" * 64,
            nombre="Test Company",
            careersUrl="https://example.com/careers",
            plataforma=PlatformaEnum.HTML,
            boardToken="some-token",
        )
        result = board_api_client(empresa)

        assert "Unsupported plataforma" in result.error
        assert result.origen == "board_api"
