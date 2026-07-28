"""
Unit tests for scan result classification — exhaustive decision table.

Tests all four classifications (OK, FAILED, EMPTY_SOSPECHOSO, EMPTY_LEGITIMO)
plus edge cases around None vacancies list and empty error string vs None.

Requirements: 6.1-6.6
"""

from datetime import datetime

import pytest

from backend.shared.models import Empresa, PlatformaEnum
from backend.shared.scan_classification import classify_scan_result


def _make_empresa(last_vacancy_count: int = 0) -> Empresa:
    """Helper to build a minimal Empresa for classification tests."""
    return Empresa(
        companyId="a" * 64,
        nombre="Test Company",
        careersUrl="https://example.com/careers",
        plataforma=PlatformaEnum.GREENHOUSE,
        lastVacancyCount=last_vacancy_count,
        createdAt=datetime(2024, 1, 1),
    )


class TestClassifyScanResult:
    """Exhaustive decision table for classify_scan_result (Requirement 6.6)."""

    # --- CASE 1: FAILED (Requirement 6.3) ---

    def test_error_present_returns_failed(self) -> None:
        """Error in extraction result → FAILED regardless of vacancies."""
        empresa = _make_empresa(last_vacancy_count=0)
        result = classify_scan_result(empresa, ([], "board_api", "timeout"))
        assert result == "FAILED"

    def test_error_present_with_vacancies_still_returns_failed(self) -> None:
        """Even with vacancies, if error is set → FAILED (error takes priority)."""
        empresa = _make_empresa(last_vacancy_count=5)
        vacancies = [{"titulo": "Dev", "url": "https://x.com/1"}]
        result = classify_scan_result(empresa, (vacancies, "json_ld", "partial_error"))
        assert result == "FAILED"

    def test_error_empty_string_returns_failed(self) -> None:
        """Empty string error is still 'not None' → FAILED."""
        empresa = _make_empresa(last_vacancy_count=0)
        result = classify_scan_result(empresa, ([], "html_llm", ""))
        assert result == "FAILED"

    def test_error_with_high_last_vacancy_count_returns_failed(self) -> None:
        """Error + high lastVacancyCount → FAILED (error takes priority over EMPTY_SOSPECHOSO)."""
        empresa = _make_empresa(last_vacancy_count=50)
        result = classify_scan_result(empresa, ([], "board_api", "HTTP 500"))
        assert result == "FAILED"

    # --- CASE 2: OK (Requirement 6.2) ---

    def test_valid_response_with_vacancies_returns_ok(self) -> None:
        """No error + N > 0 vacancies → OK."""
        empresa = _make_empresa(last_vacancy_count=0)
        vacancies = [{"titulo": "Engineer", "url": "https://x.com/1"}]
        result = classify_scan_result(empresa, (vacancies, "board_api", None))
        assert result == "OK"

    def test_valid_response_with_multiple_vacancies_returns_ok(self) -> None:
        """No error + many vacancies → OK."""
        empresa = _make_empresa(last_vacancy_count=10)
        vacancies = [{"titulo": f"Job {i}", "url": f"https://x.com/{i}"} for i in range(5)]
        result = classify_scan_result(empresa, (vacancies, "json_ld", None))
        assert result == "OK"

    def test_ok_regardless_of_last_vacancy_count(self) -> None:
        """Having vacancies → OK even when lastVacancyCount was 0."""
        empresa = _make_empresa(last_vacancy_count=0)
        vacancies = [{"titulo": "Dev", "url": "https://x.com/1"}]
        result = classify_scan_result(empresa, (vacancies, "html_llm", None))
        assert result == "OK"

    # --- CASE 3: EMPTY_SOSPECHOSO (Requirement 6.4) ---

    def test_zero_vacancies_with_previous_count_returns_empty_sospechoso(self) -> None:
        """No error + 0 vacancies + lastVacancyCount > 0 → EMPTY_SOSPECHOSO."""
        empresa = _make_empresa(last_vacancy_count=5)
        result = classify_scan_result(empresa, ([], "json_ld", None))
        assert result == "EMPTY_SOSPECHOSO"

    def test_empty_sospechoso_with_last_vacancy_count_one(self) -> None:
        """Boundary: lastVacancyCount == 1 (> 0) → EMPTY_SOSPECHOSO."""
        empresa = _make_empresa(last_vacancy_count=1)
        result = classify_scan_result(empresa, ([], "board_api", None))
        assert result == "EMPTY_SOSPECHOSO"

    def test_none_vacancies_list_with_previous_count_returns_empty_sospechoso(self) -> None:
        """None vacancies list (not []) + lastVacancyCount > 0 → EMPTY_SOSPECHOSO."""
        empresa = _make_empresa(last_vacancy_count=3)
        result = classify_scan_result(empresa, (None, "html_llm", None))
        assert result == "EMPTY_SOSPECHOSO"

    # --- CASE 4: EMPTY_LEGITIMO (Requirement 6.5) ---

    def test_zero_vacancies_with_zero_last_count_returns_empty_legitimo(self) -> None:
        """No error + 0 vacancies + lastVacancyCount == 0 → EMPTY_LEGITIMO."""
        empresa = _make_empresa(last_vacancy_count=0)
        result = classify_scan_result(empresa, ([], "json_ld", None))
        assert result == "EMPTY_LEGITIMO"

    def test_none_vacancies_list_with_zero_last_count_returns_empty_legitimo(self) -> None:
        """None vacancies list + lastVacancyCount == 0 → EMPTY_LEGITIMO."""
        empresa = _make_empresa(last_vacancy_count=0)
        result = classify_scan_result(empresa, (None, "board_api", None))
        assert result == "EMPTY_LEGITIMO"

    def test_manual_platform_scenario_returns_empty_legitimo(self) -> None:
        """Manual platform: cascada returns ([], None, None), lastVacancyCount=0 → EMPTY_LEGITIMO."""
        empresa = Empresa(
            companyId="b" * 64,
            nombre="Manual Co",
            careersUrl="https://manual.com/careers",
            plataforma=PlatformaEnum.MANUAL,
            lastVacancyCount=0,
            createdAt=datetime(2024, 1, 1),
        )
        result = classify_scan_result(empresa, ([], None, None))
        assert result == "EMPTY_LEGITIMO"

    def test_empty_list_none_origen_none_error_zero_count_returns_empty_legitimo(self) -> None:
        """Edge case: all None/empty with zero count → EMPTY_LEGITIMO."""
        empresa = _make_empresa(last_vacancy_count=0)
        result = classify_scan_result(empresa, ([], None, None))
        assert result == "EMPTY_LEGITIMO"

    # --- Exhaustive decision table (Requirement 6.1-6.6) ---

    @pytest.mark.parametrize(
        "error, vacancies, last_vacancy_count, expected",
        [
            # FAILED: error is not None (Requirement 6.3)
            ("timeout", [], 0, "FAILED"),
            ("timeout", [], 5, "FAILED"),
            ("timeout", [{"titulo": "x", "url": "https://x.com"}], 0, "FAILED"),
            ("timeout", [{"titulo": "x", "url": "https://x.com"}], 5, "FAILED"),
            ("HTTP 500", [], 0, "FAILED"),
            ("HTTP 500", [], 1, "FAILED"),
            ("", [], 0, "FAILED"),  # empty string is still not None
            ("invalid_json", None, 10, "FAILED"),
            ("connection_error", [], 100, "FAILED"),
            # OK: error is None AND vacancies > 0 (Requirement 6.2)
            (None, [{"titulo": "x", "url": "https://x.com"}], 0, "OK"),
            (None, [{"titulo": "x", "url": "https://x.com"}], 5, "OK"),
            (None, [{"titulo": "x", "url": "https://x.com"}], 100, "OK"),
            (None, [{"titulo": "a", "url": "https://a.com"}, {"titulo": "b", "url": "https://b.com"}], 0, "OK"),
            (None, [{"titulo": "a", "url": "https://a.com"}, {"titulo": "b", "url": "https://b.com"}], 10, "OK"),
            # EMPTY_SOSPECHOSO: error None, vacancies == 0, lastVacancyCount > 0 (Req 6.4)
            (None, [], 1, "EMPTY_SOSPECHOSO"),
            (None, [], 5, "EMPTY_SOSPECHOSO"),
            (None, [], 100, "EMPTY_SOSPECHOSO"),
            (None, None, 1, "EMPTY_SOSPECHOSO"),
            (None, None, 50, "EMPTY_SOSPECHOSO"),
            # EMPTY_LEGITIMO: error None, vacancies == 0, lastVacancyCount == 0 (Req 6.5)
            (None, [], 0, "EMPTY_LEGITIMO"),
            (None, None, 0, "EMPTY_LEGITIMO"),
        ],
        ids=[
            "FAILED-error_timeout-empty-lvc0",
            "FAILED-error_timeout-empty-lvc5",
            "FAILED-error_timeout-with_vacancies-lvc0",
            "FAILED-error_timeout-with_vacancies-lvc5",
            "FAILED-error_http500-empty-lvc0",
            "FAILED-error_http500-empty-lvc1",
            "FAILED-error_empty_string-empty-lvc0",
            "FAILED-error_invalid_json-none-lvc10",
            "FAILED-error_connection-empty-lvc100",
            "OK-no_error-one_vacancy-lvc0",
            "OK-no_error-one_vacancy-lvc5",
            "OK-no_error-one_vacancy-lvc100",
            "OK-no_error-two_vacancies-lvc0",
            "OK-no_error-two_vacancies-lvc10",
            "EMPTY_SOSPECHOSO-no_error-empty-lvc1",
            "EMPTY_SOSPECHOSO-no_error-empty-lvc5",
            "EMPTY_SOSPECHOSO-no_error-empty-lvc100",
            "EMPTY_SOSPECHOSO-no_error-none-lvc1",
            "EMPTY_SOSPECHOSO-no_error-none-lvc50",
            "EMPTY_LEGITIMO-no_error-empty-lvc0",
            "EMPTY_LEGITIMO-no_error-none-lvc0",
        ],
    )
    def test_exhaustive_decision_table(
        self, error: str | None, vacancies: list | None, last_vacancy_count: int, expected: str
    ) -> None:
        """Parametrized exhaustive decision table covering all (error, vacancies, lastVacancyCount) combos."""
        empresa = _make_empresa(last_vacancy_count=last_vacancy_count)
        result = classify_scan_result(empresa, (vacancies, "board_api", error))
        assert result == expected

    # --- Uniqueness guarantee (Requirement 6.6) ---

    def test_classification_is_always_exactly_one_value(self) -> None:
        """Every input produces exactly one of the four valid classifications."""
        valid_classifications = {"OK", "FAILED", "EMPTY_SOSPECHOSO", "EMPTY_LEGITIMO"}

        test_cases = [
            # (lastVacancyCount, vacancies, origen, error)
            (0, [], "board_api", "timeout"),
            (5, [], "json_ld", "HTTP 500"),
            (0, [{"titulo": "x", "url": "https://x.com"}], "board_api", None),
            (10, [{"titulo": "x", "url": "https://x.com"}], "json_ld", None),
            (5, [], "html_llm", None),
            (1, [], "board_api", None),
            (0, [], "json_ld", None),
            (0, None, "board_api", None),
            (0, [], None, None),
        ]

        for last_count, vacancies, origen, error in test_cases:
            empresa = _make_empresa(last_vacancy_count=last_count)
            result = classify_scan_result(empresa, (vacancies, origen, error))
            assert result in valid_classifications, (
                f"Got '{result}' for input: lastVacancyCount={last_count}, "
                f"vacancies={vacancies}, origen={origen}, error={error}"
            )

    def test_no_two_classifications_for_same_input(self) -> None:
        """Calling classify_scan_result multiple times with same input yields same result."""
        empresa = _make_empresa(last_vacancy_count=3)
        extraction = ([{"titulo": "Dev", "url": "https://x.com/1"}], "json_ld", None)

        results = {classify_scan_result(empresa, extraction) for _ in range(10)}
        assert len(results) == 1, f"Non-deterministic: got multiple classifications {results}"

    def test_classifications_are_mutually_exclusive_across_conditions(self) -> None:
        """For every combination of conditions, exactly one classification is produced (no overlap)."""
        valid_classifications = {"OK", "FAILED", "EMPTY_SOSPECHOSO", "EMPTY_LEGITIMO"}
        errors = [None, "some_error"]
        vacancy_lists: list = [[], [{"titulo": "x", "url": "https://x.com"}]]
        last_counts = [0, 1, 5]

        for error in errors:
            for vacancies in vacancy_lists:
                for lvc in last_counts:
                    empresa = _make_empresa(last_vacancy_count=lvc)
                    result = classify_scan_result(empresa, (vacancies, "board_api", error))
                    assert result in valid_classifications, (
                        f"Invalid classification '{result}' for "
                        f"error={error}, vacancies={len(vacancies)}, lvc={lvc}"
                    )
