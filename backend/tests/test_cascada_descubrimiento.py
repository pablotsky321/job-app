"""
Tests for Cascada_Descubrimiento orchestrator (pure function).

Verifies cascade order, stop logic, and routing by plataforma.
NO AWS calls — extractors are mocked to test orchestration logic only.

Requirements: 2.1-2.13
"""

from unittest.mock import patch

import pytest

from backend.shared.cascada_descubrimiento import cascada_descubrimiento
from backend.shared.extraction import ExtractionResult, VacancyExtracted
from backend.shared.models import Empresa, PlatformaEnum


# =============================================================================
# Fixtures / Helpers
# =============================================================================


def _make_empresa(plataforma: str, **kwargs) -> Empresa:
    """Create a minimal Empresa for testing."""
    defaults = {
        "companyId": "abc123",
        "nombre": "Test Company",
        "careersUrl": "https://example.com/careers",
        "plataforma": PlatformaEnum(plataforma),
        "boardToken": "test-token",
    }
    defaults.update(kwargs)
    return Empresa(**defaults)


def _make_extraction_result(
    n_vacancies: int = 0,
    origen: str = "board_api",
    error: str | None = None,
) -> ExtractionResult:
    """Create an ExtractionResult with N dummy vacancies."""
    vacancies = [
        VacancyExtracted(
            titulo=f"Job {i}",
            descripcion="desc",
            url=f"https://example.com/jobs/{i}",
            modalidad="sin_dato",
            ubicacion="Remote",
        )
        for i in range(n_vacancies)
    ]
    return ExtractionResult(vacancies=vacancies, origen=origen, error=error)


# =============================================================================
# Tests: Manual platform (Requirement 2.11, 2.13)
# =============================================================================


class TestManualPlatform:
    """Requirement 2.11: manual → skip all methods entirely."""

    def test_manual_returns_empty_tuple(self):
        empresa = _make_empresa("manual")
        result = cascada_descubrimiento(empresa)
        assert result == ([], None, None)

    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    def test_manual_never_calls_extractors(self, mock_html, mock_jsonld, mock_board):
        empresa = _make_empresa("manual")
        cascada_descubrimiento(empresa)
        mock_board.assert_not_called()
        mock_jsonld.assert_not_called()
        mock_html.assert_not_called()


# =============================================================================
# Tests: Greenhouse/Lever cascade order (Requirements 2.1-2.3)
# =============================================================================


class TestGreenhouseLeverCascade:
    """Requirements 2.1-2.3: greenhouse/lever → board_api → json_ld → html_llm."""

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_stops_at_board_api_when_vacancies_found(self, mock_board, mock_jsonld, mock_html):
        """Requirement 2.2: board_api returns N>0 → stop immediately."""
        mock_board.return_value = _make_extraction_result(3, origen="board_api")
        empresa = _make_empresa("greenhouse")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 3
        assert origen == "board_api"
        assert error is None
        mock_board.assert_called_once_with(empresa)
        mock_jsonld.assert_not_called()
        mock_html.assert_not_called()

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_falls_through_board_api_zero_vacancies_to_json_ld(
        self, mock_board, mock_jsonld, mock_html
    ):
        """Requirement 2.3: board_api returns 0 → try json_ld."""
        mock_board.return_value = _make_extraction_result(0, origen="board_api")
        mock_jsonld.return_value = _make_extraction_result(5, origen="json_ld")
        empresa = _make_empresa("lever")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 5
        assert origen == "json_ld"
        assert error is None
        mock_board.assert_called_once()
        mock_jsonld.assert_called_once()
        mock_html.assert_not_called()

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_falls_through_board_api_error_to_json_ld(
        self, mock_board, mock_jsonld, mock_html
    ):
        """Requirement 2.3: board_api error → try json_ld."""
        mock_board.return_value = _make_extraction_result(0, origen="board_api", error="timeout")
        mock_jsonld.return_value = _make_extraction_result(2, origen="json_ld")
        empresa = _make_empresa("greenhouse")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 2
        assert origen == "json_ld"
        assert error is None

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_falls_through_to_html_llm_when_all_prior_fail(
        self, mock_board, mock_jsonld, mock_html
    ):
        """Requirement 2.6, 2.7: all prior methods fail → html_llm is final."""
        mock_board.return_value = _make_extraction_result(0, origen="board_api", error="HTTP 404")
        mock_jsonld.return_value = _make_extraction_result(0, origen="json_ld")
        mock_html.return_value = _make_extraction_result(1, origen="html_llm")
        empresa = _make_empresa("greenhouse")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 1
        assert origen == "html_llm"
        assert error is None
        mock_board.assert_called_once()
        mock_jsonld.assert_called_once()
        mock_html.assert_called_once()

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_html_llm_result_accepted_even_with_zero_vacancies(
        self, mock_board, mock_jsonld, mock_html
    ):
        """Requirement 2.7: html_llm is final — 0 vacancies is accepted."""
        mock_board.return_value = _make_extraction_result(0, origen="board_api")
        mock_jsonld.return_value = _make_extraction_result(0, origen="json_ld")
        mock_html.return_value = _make_extraction_result(0, origen="html_llm")
        empresa = _make_empresa("lever")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert vacancies == []
        assert origen == "html_llm"
        assert error is None

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_html_llm_error_is_returned_as_final(
        self, mock_board, mock_jsonld, mock_html
    ):
        """Requirement 2.7: html_llm error is accepted as final outcome."""
        mock_board.return_value = _make_extraction_result(0, origen="board_api")
        mock_jsonld.return_value = _make_extraction_result(0, origen="json_ld", error="no postings")
        mock_html.return_value = _make_extraction_result(0, origen="html_llm", error="bedrock timeout")
        empresa = _make_empresa("greenhouse")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert vacancies == []
        assert origen == "html_llm"
        assert error == "bedrock timeout"


# =============================================================================
# Tests: HTML/JSONLD cascade order (Requirements 2.4-2.6)
# =============================================================================


class TestHtmlJsonldCascade:
    """Requirements 2.4-2.6: html/jsonld → json_ld → html_llm (no board_api)."""

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_html_platform_skips_board_api(self, mock_board, mock_jsonld, mock_html):
        """Requirement 2.4: html platform starts with json_ld."""
        mock_jsonld.return_value = _make_extraction_result(4, origen="json_ld")
        empresa = _make_empresa("html")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 4
        assert origen == "json_ld"
        mock_board.assert_not_called()

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_jsonld_platform_skips_board_api(self, mock_board, mock_jsonld, mock_html):
        """Requirement 2.4: jsonld platform starts with json_ld."""
        mock_jsonld.return_value = _make_extraction_result(2, origen="json_ld")
        empresa = _make_empresa("jsonld")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 2
        assert origen == "json_ld"
        mock_board.assert_not_called()

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_jsonld_falls_through_to_html_llm(self, mock_board, mock_jsonld, mock_html):
        """Requirement 2.6: json_ld returns 0 → try html_llm."""
        mock_jsonld.return_value = _make_extraction_result(0, origen="json_ld")
        mock_html.return_value = _make_extraction_result(7, origen="html_llm")
        empresa = _make_empresa("jsonld")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 7
        assert origen == "html_llm"
        assert error is None
        mock_board.assert_not_called()
        mock_jsonld.assert_called_once()
        mock_html.assert_called_once()


# =============================================================================
# Tests: Exception handling in extractors
# =============================================================================


class TestExtractorExceptions:
    """Verify cascade continues when an extractor raises an unexpected exception."""

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_board_api_exception_falls_through_to_json_ld(
        self, mock_board, mock_jsonld, mock_html
    ):
        """Unhandled exception in board_api → continue to json_ld."""
        mock_board.side_effect = RuntimeError("unexpected crash")
        mock_jsonld.return_value = _make_extraction_result(3, origen="json_ld")
        empresa = _make_empresa("greenhouse")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 3
        assert origen == "json_ld"
        assert error is None

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_json_ld_exception_falls_through_to_html_llm(
        self, mock_board, mock_jsonld, mock_html
    ):
        """Unhandled exception in json_ld → continue to html_llm."""
        mock_board.return_value = _make_extraction_result(0, origen="board_api")
        mock_jsonld.side_effect = ConnectionError("DNS failure")
        mock_html.return_value = _make_extraction_result(2, origen="html_llm")
        empresa = _make_empresa("lever")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 2
        assert origen == "html_llm"
        assert error is None

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_html_llm_exception_returns_error(self, mock_board, mock_jsonld, mock_html):
        """html_llm is final — exception returns error in tuple."""
        mock_board.return_value = _make_extraction_result(0, origen="board_api")
        mock_jsonld.return_value = _make_extraction_result(0, origen="json_ld")
        mock_html.side_effect = ValueError("Bedrock exploded")
        empresa = _make_empresa("greenhouse")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert vacancies == []
        assert origen == "html_llm"
        assert "ValueError" in error

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_all_extractors_exception_for_html_platform(
        self, mock_board, mock_jsonld, mock_html
    ):
        """html platform: both json_ld and html_llm raise → returns error."""
        mock_jsonld.side_effect = RuntimeError("crash")
        mock_html.side_effect = RuntimeError("crash too")
        empresa = _make_empresa("html")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert vacancies == []
        assert origen == "html_llm"
        assert "RuntimeError" in error


# =============================================================================
# Tests: Stop logic — only stops on N > 0 AND no error
# =============================================================================


class TestStopLogic:
    """Verify that cascade only stops at a method when it returns N>0 without error."""

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_board_api_with_error_and_vacancies_still_falls_through(
        self, mock_board, mock_jsonld, mock_html
    ):
        """board_api returns vacancies BUT with error → should fall through."""
        # This tests that error presence causes fallthrough even with vacancies
        mock_board.return_value = ExtractionResult(
            vacancies=[
                VacancyExtracted(
                    titulo="Job 1", url="https://x.com/1", modalidad="sin_dato", ubicacion=""
                )
            ],
            origen="board_api",
            error="partial_failure",
        )
        mock_jsonld.return_value = _make_extraction_result(2, origen="json_ld")
        empresa = _make_empresa("greenhouse")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        # The implementation stops only when error is None AND vacancies > 0.
        # With error present, it falls through to json_ld.
        assert len(vacancies) == 2
        assert origen == "json_ld"
        assert error is None

    @patch("backend.shared.cascada_descubrimiento.html_llm_extractor")
    @patch("backend.shared.cascada_descubrimiento.json_ld_extractor")
    @patch("backend.shared.cascada_descubrimiento.board_api_client")
    def test_json_ld_zero_vacancies_no_error_falls_through(
        self, mock_board, mock_jsonld, mock_html
    ):
        """json_ld returns 0 vacancies, no error → falls through to html_llm."""
        mock_jsonld.return_value = _make_extraction_result(0, origen="json_ld")
        mock_html.return_value = _make_extraction_result(10, origen="html_llm")
        empresa = _make_empresa("html")

        vacancies, origen, error = cascada_descubrimiento(empresa)

        assert len(vacancies) == 10
        assert origen == "html_llm"
