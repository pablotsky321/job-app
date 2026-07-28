"""
Unit tests for Notificador qualification logic (pure functions, no AWS).

Validates: Requirement 7.3, 7.5
Property 3: Zero Vacancies → No Email
"""

from backend.workers.notificador.qualification import (
    determine_qualified_vacancies,
    should_send_email,
)


class TestDetermineQualifiedVacancies:
    """Tests for determine_qualified_vacancies."""

    def test_estado_nueva_included(self):
        """estado=nueva qualifies."""
        vacancies = [
            {
                "estado": "nueva",
                "companyId": "company-1",
                "vacancyId": "vac-1",
                "firstSeenAt": "2024-01-15T10:00:00Z",
            },
        ]
        result = determine_qualified_vacancies(
            usuario_vacantes=vacancies,
            empresas_completadas={"company-1"},
            started_at="2024-01-15T09:00:00Z",
        )
        assert len(result) == 1
        assert result[0]["vacancyId"] == "vac-1"

    def test_estado_filtered_out_excluded(self):
        """estado=filtered_out does NOT qualify."""
        vacancies = [
            {
                "estado": "filtered_out",
                "companyId": "company-1",
                "vacancyId": "vac-1",
                "firstSeenAt": "2024-01-15T10:00:00Z",
            },
        ]
        result = determine_qualified_vacancies(
            usuario_vacantes=vacancies,
            empresas_completadas={"company-1"},
            started_at="2024-01-15T09:00:00Z",
        )
        assert len(result) == 0

    def test_estado_vista_excluded(self):
        """estado=vista does NOT qualify."""
        vacancies = [
            {
                "estado": "vista",
                "companyId": "company-1",
                "vacancyId": "vac-1",
                "firstSeenAt": "2024-01-15T10:00:00Z",
            },
        ]
        result = determine_qualified_vacancies(
            usuario_vacantes=vacancies,
            empresas_completadas={"company-1"},
            started_at="2024-01-15T09:00:00Z",
        )
        assert len(result) == 0

    def test_estado_aplicada_excluded(self):
        """estado=aplicada does NOT qualify."""
        vacancies = [
            {
                "estado": "aplicada",
                "companyId": "company-1",
                "vacancyId": "vac-1",
                "firstSeenAt": "2024-01-15T10:00:00Z",
            },
        ]
        result = determine_qualified_vacancies(
            usuario_vacantes=vacancies,
            empresas_completadas={"company-1"},
            started_at="2024-01-15T09:00:00Z",
        )
        assert len(result) == 0

    def test_first_seen_at_equal_to_started_at_included(self):
        """firstSeenAt == startedAt qualifies (>= boundary)."""
        vacancies = [
            {
                "estado": "nueva",
                "companyId": "company-1",
                "vacancyId": "vac-1",
                "firstSeenAt": "2024-01-15T10:00:00Z",
            },
        ]
        result = determine_qualified_vacancies(
            usuario_vacantes=vacancies,
            empresas_completadas={"company-1"},
            started_at="2024-01-15T10:00:00Z",
        )
        assert len(result) == 1

    def test_first_seen_at_before_started_at_excluded(self):
        """firstSeenAt < startedAt does NOT qualify."""
        vacancies = [
            {
                "estado": "nueva",
                "companyId": "company-1",
                "vacancyId": "vac-1",
                "firstSeenAt": "2024-01-15T08:00:00Z",
            },
        ]
        result = determine_qualified_vacancies(
            usuario_vacantes=vacancies,
            empresas_completadas={"company-1"},
            started_at="2024-01-15T09:00:00Z",
        )
        assert len(result) == 0

    def test_company_not_in_empresas_completadas_excluded(self):
        """companyId not in empresasCompletadas does NOT qualify."""
        vacancies = [
            {
                "estado": "nueva",
                "companyId": "company-2",
                "vacancyId": "vac-1",
                "firstSeenAt": "2024-01-15T10:00:00Z",
            },
        ]
        result = determine_qualified_vacancies(
            usuario_vacantes=vacancies,
            empresas_completadas={"company-1"},
            started_at="2024-01-15T09:00:00Z",
        )
        assert len(result) == 0

    def test_multiple_vacancies_mixed_qualification(self):
        """Only vacancies meeting ALL criteria qualify."""
        vacancies = [
            {
                "estado": "nueva",
                "companyId": "company-1",
                "vacancyId": "vac-1",
                "firstSeenAt": "2024-01-15T10:00:00Z",
            },
            {
                "estado": "filtered_out",
                "companyId": "company-1",
                "vacancyId": "vac-2",
                "firstSeenAt": "2024-01-15T10:00:00Z",
            },
            {
                "estado": "nueva",
                "companyId": "company-1",
                "vacancyId": "vac-3",
                "firstSeenAt": "2024-01-14T08:00:00Z",  # Before startedAt
            },
            {
                "estado": "nueva",
                "companyId": "company-99",
                "vacancyId": "vac-4",
                "firstSeenAt": "2024-01-15T10:00:00Z",
            },
            {
                "estado": "nueva",
                "companyId": "company-1",
                "vacancyId": "vac-5",
                "firstSeenAt": "2024-01-15T11:00:00Z",
            },
        ]
        result = determine_qualified_vacancies(
            usuario_vacantes=vacancies,
            empresas_completadas={"company-1"},
            started_at="2024-01-15T09:00:00Z",
        )
        assert len(result) == 2
        qualified_ids = {v["vacancyId"] for v in result}
        assert qualified_ids == {"vac-1", "vac-5"}

    def test_empty_list_returns_empty(self):
        """Empty input returns empty result."""
        result = determine_qualified_vacancies(
            usuario_vacantes=[],
            empresas_completadas={"company-1"},
            started_at="2024-01-15T09:00:00Z",
        )
        assert result == []

    def test_missing_first_seen_at_excluded(self):
        """Missing firstSeenAt field excludes the vacancy."""
        vacancies = [
            {
                "estado": "nueva",
                "companyId": "company-1",
                "vacancyId": "vac-1",
            },
        ]
        result = determine_qualified_vacancies(
            usuario_vacantes=vacancies,
            empresas_completadas={"company-1"},
            started_at="2024-01-15T09:00:00Z",
        )
        assert len(result) == 0


class TestShouldSendEmail:
    """Tests for should_send_email (zero-vacancies guard)."""

    def test_empty_qualified_list_returns_false(self):
        """Empty qualified list → should_send_email returns False."""
        assert should_send_email([]) is False

    def test_non_empty_qualified_list_returns_true(self):
        """Non-empty list → returns True."""
        assert should_send_email([{"vacancyId": "vac-1"}]) is True

    def test_multiple_items_returns_true(self):
        """Multiple items → returns True."""
        vacancies = [
            {"vacancyId": "vac-1"},
            {"vacancyId": "vac-2"},
            {"vacancyId": "vac-3"},
        ]
        assert should_send_email(vacancies) is True
