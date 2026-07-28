"""
Unit tests for backend/shared/html_llm_extractor.py.

Tests mock Bedrock responses and HTTP fetches — NO real AWS calls.
Validates:
- Successful extraction flow (fetch → clean → Bedrock → map)
- HTTP fetch failures (timeout, 4xx/5xx)
- Bedrock validation failures (invalid JSON, Pydantic errors)
- Mapping logic (modalidad defaults, empty titulo filtering)
- Error wrapping in ExtractionResult (never raises)

Requirements: 5.2-5.6, 2.8
"""

from unittest.mock import MagicMock, patch

import pytest
import requests
from pydantic import ValidationError

from backend.shared.extraction import ExtractionResult, VacancyExtracted
from backend.shared.html_llm_extractor import (
    LlmExtractionResponse,
    LlmVacancyItem,
    html_llm_extractor,
    _map_llm_response_to_vacancies,
)
from backend.shared.models import Empresa, PlatformaEnum


# =============================================================================
# Helpers
# =============================================================================


def _make_empresa(careers_url: str = "https://example.com/careers") -> Empresa:
    """Create a minimal Empresa for testing."""
    return Empresa(
        companyId="abc123" * 10 + "abcd",
        nombre="Test Corp",
        careersUrl=careers_url,
        plataforma=PlatformaEnum.HTML,
    )


# =============================================================================
# LlmExtractionResponse model tests
# =============================================================================


class TestLlmExtractionResponse:
    def test_valid_response_with_vacancies(self):
        data = {
            "vacancies": [
                {
                    "titulo": "Backend Dev",
                    "descripcion": "Build APIs",
                    "url": "https://example.com/job/1",
                    "modalidad": "remote",
                    "ubicacion": "LATAM",
                }
            ]
        }
        result = LlmExtractionResponse.model_validate(data)
        assert len(result.vacancies) == 1
        assert result.vacancies[0].titulo == "Backend Dev"

    def test_valid_response_empty_vacancies(self):
        data = {"vacancies": []}
        result = LlmExtractionResponse.model_validate(data)
        assert result.vacancies == []

    def test_defaults_for_optional_fields(self):
        data = {
            "vacancies": [
                {"titulo": "Dev", "url": "https://example.com/job/1"}
            ]
        }
        result = LlmExtractionResponse.model_validate(data)
        assert result.vacancies[0].modalidad == "sin_dato"
        assert result.vacancies[0].ubicacion == ""
        assert result.vacancies[0].descripcion == ""

    def test_extra_fields_ignored(self):
        data = {
            "vacancies": [
                {
                    "titulo": "Dev",
                    "url": "https://x.com/job",
                    "salary": "100k",
                }
            ],
            "metadata": "ignored",
        }
        result = LlmExtractionResponse.model_validate(data)
        assert len(result.vacancies) == 1


# =============================================================================
# _map_llm_response_to_vacancies tests
# =============================================================================


class TestMapLlmResponseToVacancies:
    def test_maps_valid_items(self):
        response = LlmExtractionResponse(
            vacancies=[
                LlmVacancyItem(
                    titulo="Software Engineer",
                    descripcion="Build things",
                    url="https://example.com/job/1",
                    modalidad="remote",
                    ubicacion="US",
                ),
                LlmVacancyItem(
                    titulo="Product Manager",
                    descripcion="Manage products",
                    url="https://example.com/job/2",
                    modalidad="hybrid",
                    ubicacion="Madrid",
                ),
            ]
        )
        result = _map_llm_response_to_vacancies(response)
        assert len(result) == 2
        assert result[0].titulo == "Software Engineer"
        assert result[1].titulo == "Product Manager"

    def test_filters_empty_titulo(self):
        response = LlmExtractionResponse(
            vacancies=[
                LlmVacancyItem(titulo="", url="https://x.com/job/1"),
                LlmVacancyItem(titulo="Valid", url="https://x.com/job/2"),
            ]
        )
        result = _map_llm_response_to_vacancies(response)
        assert len(result) == 1
        assert result[0].titulo == "Valid"

    def test_filters_whitespace_only_titulo(self):
        response = LlmExtractionResponse(
            vacancies=[
                LlmVacancyItem(titulo="   ", url="https://x.com/job/1"),
            ]
        )
        result = _map_llm_response_to_vacancies(response)
        assert len(result) == 0

    def test_modalidad_defaults_to_sin_dato(self):
        """Requirement 5.6: modalidad='sin_dato' when not specified."""
        response = LlmExtractionResponse(
            vacancies=[
                LlmVacancyItem(titulo="Dev", url="https://x.com/job/1", modalidad=""),
            ]
        )
        result = _map_llm_response_to_vacancies(response)
        assert result[0].modalidad == "sin_dato"

    def test_strips_whitespace_from_fields(self):
        response = LlmExtractionResponse(
            vacancies=[
                LlmVacancyItem(
                    titulo="  Dev  ",
                    descripcion="  Build  ",
                    url="  https://x.com/job/1  ",
                    modalidad="remote",
                    ubicacion="  NY  ",
                ),
            ]
        )
        result = _map_llm_response_to_vacancies(response)
        assert result[0].titulo == "Dev"
        assert result[0].descripcion == "Build"
        assert result[0].url == "https://x.com/job/1"
        assert result[0].ubicacion == "NY"


# =============================================================================
# html_llm_extractor integration tests (mocked HTTP + Bedrock)
# =============================================================================


class TestHtmlLlmExtractor:
    """Test the full html_llm_extractor function with mocked dependencies."""

    @patch("backend.shared.html_llm_extractor.get_bedrock_client")
    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_successful_extraction(self, mock_get, mock_bedrock):
        """Happy path: fetch → clean → Bedrock → valid response."""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.text = "<html><body><h1>Jobs</h1><p>Backend Developer - Remote</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Mock Bedrock response
        mock_client = MagicMock()
        mock_client.model_small = "test-model-id"
        mock_client.invoke_with_retry.return_value = LlmExtractionResponse(
            vacancies=[
                LlmVacancyItem(
                    titulo="Backend Developer",
                    descripcion="Build APIs",
                    url="https://example.com/job/1",
                    modalidad="remote",
                    ubicacion="Remote",
                )
            ]
        )
        mock_bedrock.return_value = mock_client

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert isinstance(result, ExtractionResult)
        assert result.error is None
        assert result.origen == "html_llm"
        assert len(result.vacancies) == 1
        assert result.vacancies[0].titulo == "Backend Developer"
        assert result.vacancies[0].modalidad == "remote"

    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_fetch_timeout_returns_error(self, mock_get):
        """Requirement 5.2: Timeout → error in ExtractionResult."""
        mock_get.side_effect = requests.Timeout("Connection timed out")

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert result.error is not None
        assert "Timeout" in result.error
        assert result.origen == "html_llm"
        assert result.vacancies == []

    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_fetch_http_error_returns_error(self, mock_get):
        """Requirement 5.2: HTTP 4xx/5xx → error in ExtractionResult."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert result.error is not None
        assert "HTTPError" in result.error
        assert result.origen == "html_llm"
        assert result.vacancies == []

    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_fetch_connection_error_returns_error(self, mock_get):
        """Connection error → error in ExtractionResult."""
        mock_get.side_effect = requests.ConnectionError("DNS resolution failed")

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert result.error is not None
        assert "ConnectionError" in result.error
        assert result.origen == "html_llm"
        assert result.vacancies == []

    @patch("backend.shared.html_llm_extractor.get_bedrock_client")
    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_bedrock_validation_error_returns_error(self, mock_get, mock_bedrock):
        """Requirement 5.5: After retry exhausted, ValidationError → error result."""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Jobs page</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Mock Bedrock raising ValidationError (after its own internal retry)
        mock_client = MagicMock()
        mock_client.model_small = "test-model-id"
        mock_client.invoke_with_retry.side_effect = ValidationError.from_exception_data(
            title="LlmExtractionResponse",
            line_errors=[
                {
                    "type": "missing",
                    "loc": ("vacancies",),
                    "msg": "Field required",
                    "input": {},
                }
            ],
        )
        mock_bedrock.return_value = mock_client

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert result.error is not None
        assert "validation" in result.error.lower() or "Validation" in result.error
        assert result.origen == "html_llm"
        assert result.vacancies == []

    @patch("backend.shared.html_llm_extractor.get_bedrock_client")
    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_bedrock_service_error_returns_error(self, mock_get, mock_bedrock):
        """Bedrock service error (e.g., throttling) → error result."""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Jobs</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Mock Bedrock raising generic exception
        mock_client = MagicMock()
        mock_client.model_small = "test-model-id"
        mock_client.invoke_with_retry.side_effect = RuntimeError("Bedrock throttling")
        mock_bedrock.return_value = mock_client

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert result.error is not None
        assert "RuntimeError" in result.error
        assert result.origen == "html_llm"
        assert result.vacancies == []

    @patch("backend.shared.html_llm_extractor.get_bedrock_client")
    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_empty_html_after_clean_returns_empty_no_error(self, mock_get, mock_bedrock):
        """If HTML is only scripts/styles → empty text → return empty, no Bedrock call."""
        mock_response = MagicMock()
        mock_response.text = "<html><head><script>var x=1;</script><style>body{}</style></head><body></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert result.error is None
        assert result.origen == "html_llm"
        assert result.vacancies == []
        # Bedrock should NOT have been called
        mock_bedrock.assert_not_called()

    @patch("backend.shared.html_llm_extractor.get_bedrock_client")
    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_bedrock_returns_zero_vacancies(self, mock_get, mock_bedrock):
        """Valid response from Bedrock with empty vacancies list."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>No jobs available</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        mock_client = MagicMock()
        mock_client.model_small = "test-model-id"
        mock_client.invoke_with_retry.return_value = LlmExtractionResponse(vacancies=[])
        mock_bedrock.return_value = mock_client

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert result.error is None
        assert result.origen == "html_llm"
        assert result.vacancies == []

    @patch("backend.shared.html_llm_extractor.get_bedrock_client")
    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_modalidad_sin_dato_when_not_specified(self, mock_get, mock_bedrock):
        """Requirement 5.6: modalidad defaults to sin_dato."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Jobs</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        mock_client = MagicMock()
        mock_client.model_small = "test-model-id"
        mock_client.invoke_with_retry.return_value = LlmExtractionResponse(
            vacancies=[
                LlmVacancyItem(
                    titulo="Engineer",
                    url="https://example.com/job/1",
                    modalidad="sin_dato",
                    ubicacion="",
                )
            ]
        )
        mock_bedrock.return_value = mock_client

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert result.vacancies[0].modalidad == "sin_dato"

    @patch("backend.shared.html_llm_extractor.get_bedrock_client")
    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_invoke_uses_model_small(self, mock_get, mock_bedrock):
        """Tech rule: Uses BEDROCK_MODEL_SMALL (never hardcoded)."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Jobs</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        mock_client = MagicMock()
        mock_client.model_small = "us.anthropic.claude-3-haiku"
        mock_client.invoke_with_retry.return_value = LlmExtractionResponse(vacancies=[])
        mock_bedrock.return_value = mock_client

        empresa = _make_empresa()
        html_llm_extractor(empresa)

        # Verify invoke_with_retry was called with the model_small from client
        call_kwargs = mock_client.invoke_with_retry.call_args
        assert call_kwargs.kwargs["model_id"] == "us.anthropic.claude-3-haiku"
        assert call_kwargs.kwargs["response_model"] == LlmExtractionResponse
        assert call_kwargs.kwargs["max_retries"] == 1

    @patch("backend.shared.html_llm_extractor.get_bedrock_client")
    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_value_error_from_json_parsing_returns_error(self, mock_get, mock_bedrock):
        """ValueError from JSON decode in Bedrock client → error result."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Jobs</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        mock_client = MagicMock()
        mock_client.model_small = "test-model-id"
        mock_client.invoke_with_retry.side_effect = ValueError(
            "Failed to decode JSON from Bedrock response"
        )
        mock_bedrock.return_value = mock_client

        empresa = _make_empresa()
        result = html_llm_extractor(empresa)

        assert result.error is not None
        assert "ValueError" in result.error
        assert result.origen == "html_llm"
        assert result.vacancies == []

    @patch("backend.shared.html_llm_extractor.get_bedrock_client")
    @patch("backend.shared.html_llm_extractor.requests.get")
    def test_never_raises_to_caller(self, mock_get, mock_bedrock):
        """The function never raises — all exceptions become error field."""
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Jobs</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        mock_client = MagicMock()
        mock_client.model_small = "test-model-id"
        mock_client.invoke_with_retry.side_effect = Exception("Unexpected internal error")
        mock_bedrock.return_value = mock_client

        empresa = _make_empresa()
        # Should NOT raise
        result = html_llm_extractor(empresa)

        assert isinstance(result, ExtractionResult)
        assert result.error is not None
        assert result.origen == "html_llm"
