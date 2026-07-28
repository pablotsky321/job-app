"""
Unit tests for missCount increment and vacancy closure logic.

Tests: incrementing, reset, closing, reopening, manual protection,
new vacancy creation, and existing vacancy update behavior.

Requirements: 7.1-7.7
"""

from datetime import datetime, timedelta

import pytest

from backend.shared.extraction import VacancyExtracted, compute_vacancyId
from backend.shared.misscount_logic import apply_missCount_logic
from backend.shared.models import Empresa, PlatformaEnum, Vacante


# ============================================================================
# HELPERS
# ============================================================================


def make_empresa(**overrides) -> Empresa:
    defaults = {
        "companyId": "abc123",
        "nombre": "TestCorp",
        "careersUrl": "https://testcorp.com/careers",
        "plataforma": PlatformaEnum.GREENHOUSE,
        "lastVacancyCount": 5,
    }
    defaults.update(overrides)
    return Empresa(**defaults)


def make_vacante(url: str, **overrides) -> Vacante:
    vacancy_id = compute_vacancyId(url)
    defaults = {
        "vacanteSha256": vacancy_id,
        "companyId": "abc123",
        "titulo": "Software Engineer",
        "descripcion": "Build stuff",
        "url": url,
        "plataforma": PlatformaEnum.GREENHOUSE,
        "origen": "board_api",
        "crawledAt": datetime(2024, 1, 1),
        "verificadaAt": datetime(2024, 1, 1),
        "missCount": 0,
        "cerrada": False,
    }
    defaults.update(overrides)
    return Vacante(**defaults)


def make_extracted(url: str, titulo: str = "Software Engineer") -> VacancyExtracted:
    return VacancyExtracted(
        titulo=titulo,
        descripcion="Some description",
        url=url,
        modalidad="remote",
        ubicacion="Remote",
    )


# ============================================================================
# REQUIREMENT 7.1: INCREMENT missCount for missing abierta vacancies
# ============================================================================


class TestMissCountIncrement:
    """Requirement 7.1: missCount += 1 when abierta vacancy NOT in scan result."""

    def test_increment_when_vacancy_missing_from_scan(self):
        empresa = make_empresa()
        existing = [make_vacante("https://testcorp.com/jobs/1", missCount=0)]
        scan_results = []  # Empty scan — vacancy not found

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 1

    def test_increment_multiple_missing_vacancies(self):
        empresa = make_empresa()
        existing = [
            make_vacante("https://testcorp.com/jobs/1", missCount=0),
            make_vacante("https://testcorp.com/jobs/2", missCount=1),
        ]
        scan_results = []  # None found

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 1
        assert result[1].missCount == 2

    def test_increment_only_missing_vacancy(self):
        """Only the vacancy NOT in scan gets incremented."""
        empresa = make_empresa()
        url_found = "https://testcorp.com/jobs/1"
        url_missing = "https://testcorp.com/jobs/2"
        existing = [
            make_vacante(url_found, missCount=0),
            make_vacante(url_missing, missCount=0),
        ]
        scan_results = [make_extracted(url_found)]

        result = apply_missCount_logic(empresa, scan_results, existing)

        found_vacancy = next(r for r in result if r.vacanteSha256 == compute_vacancyId(url_found))
        missing_vacancy = next(r for r in result if r.vacanteSha256 == compute_vacancyId(url_missing))
        assert found_vacancy.missCount == 0
        assert missing_vacancy.missCount == 1

    def test_no_increment_for_already_closed_vacancy(self):
        """Req 7.1: Only abierta vacancies get missCount incremented."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/closed-one"
        existing = [make_vacante(url, missCount=3, cerrada=True)]
        scan_results = []  # Not found

        result = apply_missCount_logic(empresa, scan_results, existing)

        # missCount stays at 3 because vacancy is already cerrada
        assert result[0].missCount == 3
        assert result[0].cerrada is True


# ============================================================================
# REQUIREMENT 7.2: RESET missCount when vacancy IS in scan result
# ============================================================================


class TestMissCountReset:
    """Requirement 7.2: missCount = 0 when vacancy IS in scan result."""

    def test_reset_misscount_when_found_in_scan(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        existing = [make_vacante(url, missCount=3)]
        scan_results = [make_extracted(url)]

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 0

    def test_reset_from_high_misscount(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        existing = [make_vacante(url, missCount=10)]
        scan_results = [make_extracted(url)]

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 0


# ============================================================================
# REQUIREMENT 7.3: REOPEN when cerrada vacancy reappears in scan
# ============================================================================


class TestReopen:
    """Requirement 7.3: cerrada → abierta when vacancy reappears."""

    def test_reopen_closed_vacancy_when_found(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        existing = [make_vacante(url, cerrada=True, missCount=5)]
        scan_results = [make_extracted(url)]

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].cerrada is False
        assert result[0].missCount == 0

    def test_open_vacancy_stays_open_when_found(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        existing = [make_vacante(url, cerrada=False, missCount=0)]
        scan_results = [make_extracted(url)]

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].cerrada is False


# ============================================================================
# REQUIREMENT 7.4: CLOSE when missCount >= 2 AND origen != 'manual'
# ============================================================================


class TestClose:
    """Requirement 7.4: cerrada = True when missCount >= 2 and not manual."""

    def test_close_at_misscount_2(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        existing = [make_vacante(url, missCount=1, origen="board_api")]
        scan_results = []  # Not found → missCount goes to 2

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 2
        assert result[0].cerrada is True

    def test_close_at_misscount_above_2(self):
        """Already-open vacancy with missCount=5 that misses again gets closed."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        # This vacancy has high missCount but was still abierta (weird but valid state)
        existing = [make_vacante(url, missCount=5, origen="board_api", cerrada=False)]
        scan_results = []  # Not found → missCount goes to 6

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 6
        assert result[0].cerrada is True

    def test_no_close_at_misscount_1(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        existing = [make_vacante(url, missCount=0, origen="board_api")]
        scan_results = []  # Not found → missCount goes to 1

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 1
        assert result[0].cerrada is False

    def test_close_with_json_ld_origen(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        existing = [make_vacante(url, missCount=1, origen="json_ld")]
        scan_results = []

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 2
        assert result[0].cerrada is True

    def test_close_with_html_llm_origen(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        existing = [make_vacante(url, missCount=1, origen="html_llm")]
        scan_results = []

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 2
        assert result[0].cerrada is True


# ============================================================================
# REQUIREMENT 7.5: MANUAL origen protection — never auto-closes
# ============================================================================


class TestManualProtection:
    """Requirement 7.5: origen='manual' never gets cerrada=True from missCount."""

    def test_manual_not_closed_even_with_high_misscount(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/manual-1"
        existing = [make_vacante(url, missCount=1, origen="manual")]
        scan_results = []  # Not found → missCount goes to 2

        result = apply_missCount_logic(empresa, scan_results, existing)

        # missCount still increments
        assert result[0].missCount == 2
        # But cerrada stays False
        assert result[0].cerrada is False

    def test_manual_not_closed_at_very_high_misscount(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/manual-2"
        existing = [make_vacante(url, missCount=99, origen="manual")]
        scan_results = []

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].missCount == 100
        assert result[0].cerrada is False

    def test_manual_misscount_increments_but_never_triggers_close(self):
        """Multiple scans without finding manual vacancy: increments but stays open."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/manual-3"
        existing = [make_vacante(url, missCount=0, origen="manual")]

        # Simulate 5 consecutive scans without finding it
        current = existing
        for i in range(5):
            current = apply_missCount_logic(empresa, [], current)
            assert current[0].cerrada is False
            assert current[0].missCount == i + 1


# ============================================================================
# REQUIREMENT 7.6: NEW vacancy creation
# ============================================================================


class TestNewVacancyCreation:
    """Requirement 7.6: New vacancies created with missCount=0, cerrada=False."""

    def test_new_vacancy_created_with_correct_defaults(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/new-1"
        scan_results = [make_extracted(url, titulo="Senior Dev")]
        existing = []

        result = apply_missCount_logic(empresa, scan_results, existing, origen="board_api")

        assert len(result) == 1
        new_v = result[0]
        assert new_v.vacanteSha256 == compute_vacancyId(url)
        assert new_v.missCount == 0
        assert new_v.cerrada is False
        assert new_v.companyId == empresa.companyId
        assert new_v.titulo == "Senior Dev"
        assert new_v.url == url
        assert new_v.origen == "board_api"

    def test_new_vacancy_uses_provided_origen(self):
        """The origen parameter determines the extraction source for new vacancies."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/new-origen"
        scan_results = [make_extracted(url)]
        existing = []

        result = apply_missCount_logic(empresa, scan_results, existing, origen="html_llm")

        assert result[0].origen == "html_llm"

    def test_new_vacancy_defaults_to_automated_origen(self):
        """When no origen specified, defaults to 'automated'."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/new-default"
        scan_results = [make_extracted(url)]
        existing = []

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].origen == "automated"

    def test_multiple_new_vacancies_created(self):
        empresa = make_empresa()
        urls = [
            "https://testcorp.com/jobs/new-1",
            "https://testcorp.com/jobs/new-2",
            "https://testcorp.com/jobs/new-3",
        ]
        scan_results = [make_extracted(u) for u in urls]
        existing = []

        result = apply_missCount_logic(empresa, scan_results, existing, origen="json_ld")

        assert len(result) == 3
        for v in result:
            assert v.missCount == 0
            assert v.cerrada is False
            assert v.origen == "json_ld"

    def test_new_vacancy_gets_empresa_plataforma(self):
        empresa = make_empresa(plataforma=PlatformaEnum.LEVER)
        url = "https://testcorp.com/jobs/lever-1"
        scan_results = [make_extracted(url)]
        existing = []

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].plataforma == PlatformaEnum.LEVER

    def test_new_vacancy_has_timestamps(self):
        """New vacancy gets crawledAt and verificadaAt set."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/timestamped"
        scan_results = [make_extracted(url)]
        existing = []

        before = datetime.utcnow()
        result = apply_missCount_logic(empresa, scan_results, existing)
        after = datetime.utcnow()

        assert before <= result[0].crawledAt <= after
        assert before <= result[0].verificadaAt <= after


# ============================================================================
# REQUIREMENT 7.7: Existing vacancy update — lastSeenAt updated, firstSeenAt unchanged
# ============================================================================


class TestExistingVacancyUpdate:
    """Requirement 7.7: verificadaAt updated when vacancy found in scan."""

    def test_verificada_at_updated_when_found(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        old_time = datetime(2024, 1, 1)
        existing = [make_vacante(url, verificadaAt=old_time)]
        scan_results = [make_extracted(url)]

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].verificadaAt > old_time

    def test_crawled_at_unchanged_when_found(self):
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        original_crawled = datetime(2023, 6, 15)
        existing = [make_vacante(url, crawledAt=original_crawled)]
        scan_results = [make_extracted(url)]

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].crawledAt == original_crawled

    def test_verificada_at_not_updated_when_not_found(self):
        """If vacancy not in scan, verificadaAt stays unchanged."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/1"
        old_time = datetime(2024, 1, 1)
        existing = [make_vacante(url, verificadaAt=old_time)]
        scan_results = []  # Not found

        result = apply_missCount_logic(empresa, scan_results, existing)

        assert result[0].verificadaAt == old_time


# ============================================================================
# COMBINED SCENARIOS
# ============================================================================


class TestCombinedScenarios:
    """Integration-like tests combining multiple requirements."""

    def test_mix_of_found_missing_new(self):
        """Scan has some found, some missing from existing, and some new."""
        empresa = make_empresa()
        url_found = "https://testcorp.com/jobs/found"
        url_missing = "https://testcorp.com/jobs/missing"
        url_new = "https://testcorp.com/jobs/brand-new"

        existing = [
            make_vacante(url_found, missCount=1),
            make_vacante(url_missing, missCount=0),
        ]
        scan_results = [
            make_extracted(url_found),
            make_extracted(url_new),
        ]

        result = apply_missCount_logic(empresa, scan_results, existing, origen="board_api")

        # 2 existing + 1 new = 3 total
        assert len(result) == 3

        found = next(r for r in result if r.vacanteSha256 == compute_vacancyId(url_found))
        missing = next(r for r in result if r.vacanteSha256 == compute_vacancyId(url_missing))
        new = next(r for r in result if r.vacanteSha256 == compute_vacancyId(url_new))

        assert found.missCount == 0  # reset
        assert missing.missCount == 1  # incremented
        assert new.missCount == 0  # new
        assert new.cerrada is False

    def test_sequence_of_scans_leading_to_closure(self):
        """Simulates two consecutive scans where vacancy disappears."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/disappearing"
        existing = [make_vacante(url, missCount=0, origen="board_api")]

        # Scan 1: vacancy not found
        result1 = apply_missCount_logic(empresa, [], existing)
        assert result1[0].missCount == 1
        assert result1[0].cerrada is False

        # Scan 2: vacancy still not found
        result2 = apply_missCount_logic(empresa, [], result1)
        assert result2[0].missCount == 2
        assert result2[0].cerrada is True

    def test_sequence_close_then_reopen(self):
        """Vacancy closes then reappears in next scan."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/flaky"
        existing = [make_vacante(url, missCount=1, origen="board_api")]

        # Scan 1: still missing → closes
        result1 = apply_missCount_logic(empresa, [], existing)
        assert result1[0].cerrada is True
        assert result1[0].missCount == 2

        # Scan 2: reappears → reopens
        result2 = apply_missCount_logic(empresa, [make_extracted(url)], result1)
        assert result2[0].cerrada is False
        assert result2[0].missCount == 0

    def test_closed_vacancy_stays_closed_when_still_missing(self):
        """Already closed vacancy remains closed on subsequent missing scans."""
        empresa = make_empresa()
        url = "https://testcorp.com/jobs/gone"
        existing = [make_vacante(url, missCount=2, cerrada=True, origen="board_api")]

        # Vacancy still not in scan — missCount does NOT increment (already cerrada)
        result = apply_missCount_logic(empresa, [], existing)
        assert result[0].missCount == 2  # stays at 2, not incremented
        assert result[0].cerrada is True

    def test_empty_existing_and_empty_scan(self):
        """No existing vacancies and empty scan → empty result."""
        empresa = make_empresa()
        result = apply_missCount_logic(empresa, [], [])
        assert result == []

    def test_all_existing_found_in_scan(self):
        """All existing vacancies are in the scan result — no increments."""
        empresa = make_empresa()
        urls = ["https://testcorp.com/jobs/1", "https://testcorp.com/jobs/2"]
        existing = [make_vacante(u, missCount=1) for u in urls]
        scan_results = [make_extracted(u) for u in urls]

        result = apply_missCount_logic(empresa, scan_results, existing)

        for v in result:
            assert v.missCount == 0

    def test_url_normalization_matches_correctly(self):
        """Vacancy matching uses normalized URL (case, fragment, trailing slash)."""
        empresa = make_empresa()
        # Existing uses one URL form
        url_existing = "https://testcorp.com/jobs/123"
        existing = [make_vacante(url_existing, missCount=1)]

        # Scan result uses variant of same URL (trailing slash)
        url_scan = "https://testcorp.com/jobs/123/"
        scan_results = [make_extracted(url_scan)]

        result = apply_missCount_logic(empresa, scan_results, existing)

        # Should match because compute_vacancyId normalizes URLs
        assert result[0].missCount == 0  # reset (matched)
