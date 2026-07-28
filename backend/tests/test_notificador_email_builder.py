"""
Unit tests for Notificador email builder (pure functions, no AWS).

Validates: Requirement 7.4
"""

from backend.workers.notificador.email_builder import build_notification_email


class TestBuildNotificationEmail:
    """Tests for build_notification_email."""

    def _make_vacancy(self, **overrides) -> dict:
        """Helper to create a test vacancy dict."""
        base = {
            "titulo": "Software Engineer",
            "empresa_nombre": "Acme Corp",
            "plataforma": "greenhouse",
            "ubicacion": "Remote",
            "modalidad": "remote",
            "url": "https://acme.com/jobs/123",
            "score": 85,
            "descripcion": "Great job opportunity for engineers.",
            "companyId": "comp-1",
            "vacancyId": "vac-1",
        }
        base.update(overrides)
        return base

    def test_subject_contains_count_and_date(self):
        """Subject follows format: '{count} nuevas vacante(s) de interés - {fecha_UTC}'."""
        vacancies = [self._make_vacancy()]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        subject, _ = build_notification_email(user_data, vacancies)

        assert subject.startswith("1 nuevas vacante(s) de interés - ")
        # Verify date format YYYY-MM-DD
        date_part = subject.split(" - ")[1]
        assert len(date_part) == 10
        assert date_part[4] == "-"
        assert date_part[7] == "-"

    def test_subject_count_multiple_vacancies(self):
        """Subject count reflects number of vacancies (up to 5)."""
        vacancies = [self._make_vacancy(vacancyId=f"vac-{i}") for i in range(3)]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        subject, _ = build_notification_email(user_data, vacancies)

        assert subject.startswith("3 nuevas vacante(s) de interés")

    def test_body_is_plain_text_no_html(self):
        """Body must be plain text with no HTML tags."""
        vacancies = [self._make_vacancy()]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        # No HTML tags present
        assert "<html" not in body.lower()
        assert "<body" not in body.lower()
        assert "<div" not in body.lower()
        assert "<p>" not in body.lower()
        assert "<br" not in body.lower()
        assert "<table" not in body.lower()
        assert "<a " not in body.lower()
        assert "<span" not in body.lower()

    def test_description_truncated_at_250_chars(self):
        """Descriptions longer than 250 chars are truncated with ellipsis."""
        long_description = "x" * 300
        vacancies = [self._make_vacancy(descripcion=long_description)]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        # The full 300-char string should not appear
        assert long_description not in body
        # The truncated version (250 chars + ...) should appear
        assert ("x" * 250 + "...") in body

    def test_description_not_truncated_when_short(self):
        """Descriptions of 250 chars or less are not truncated."""
        short_description = "y" * 250
        vacancies = [self._make_vacancy(descripcion=short_description)]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        assert short_description in body
        # No ellipsis after the text
        assert short_description + "..." not in body

    def test_cv_ats_texto_truncated_at_500_chars(self):
        """cvAtsTexto longer than 500 chars is truncated."""
        long_cv = "z" * 600
        vacancies = [self._make_vacancy(cvAtsTexto=long_cv)]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        # Full 600-char string should not appear
        assert long_cv not in body
        # Truncated version (500 + ...) should appear
        assert ("z" * 500 + "...") in body

    def test_cv_ats_texto_omitted_when_absent(self):
        """cvAtsTexto not included in email when None."""
        vacancies = [self._make_vacancy(cvAtsTexto=None)]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        assert "CV Personalizado" not in body

    def test_cv_ats_texto_omitted_when_empty_string(self):
        """cvAtsTexto not included in email when empty string."""
        vacancies = [self._make_vacancy(cvAtsTexto="")]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        assert "CV Personalizado" not in body

    def test_cv_ats_texto_included_when_present(self):
        """cvAtsTexto is included when it has content."""
        vacancies = [self._make_vacancy(cvAtsTexto="My ATS CV text")]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        assert "CV Personalizado" in body
        assert "My ATS CV text" in body

    def test_max_5_vacancies_per_call(self):
        """At most 5 vacancies are included per email call."""
        vacancies = [
            self._make_vacancy(titulo=f"Job {i}", vacancyId=f"vac-{i}")
            for i in range(8)
        ]
        user_data = {"nombre": "Juan", "email": "j@test.com"}

        subject, body = build_notification_email(user_data, vacancies)

        # Subject should say 5, not 8
        assert subject.startswith("5 nuevas vacante(s)")
        # Body includes VACANTE 1 through 5
        assert "VACANTE 1:" in body
        assert "VACANTE 5:" in body
        # VACANTE 6 should not be in body
        assert "VACANTE 6:" not in body

    def test_body_includes_user_greeting(self):
        """Body starts with greeting using user name."""
        vacancies = [self._make_vacancy()]
        user_data = {"nombre": "María", "email": "m@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        assert "Hola María," in body

    def test_body_includes_vacancy_fields(self):
        """Body includes all expected vacancy fields."""
        vacancies = [self._make_vacancy(
            titulo="Backend Dev",
            empresa_nombre="TechCorp",
            plataforma="lever",
            ubicacion="Bogotá",
            modalidad="hybrid",
            url="https://techcorp.com/jobs/42",
            score=92,
        )]
        user_data = {"nombre": "Carlos", "email": "c@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        assert "Backend Dev" in body
        assert "TechCorp" in body
        assert "lever" in body
        assert "Bogotá" in body
        assert "hybrid" in body
        assert "https://techcorp.com/jobs/42" in body
        assert "92" in body

    def test_score_pending_when_none(self):
        """Score shows 'pendiente' when None."""
        vacancies = [self._make_vacancy(score=None)]
        user_data = {"nombre": "Ana", "email": "a@test.com"}

        _, body = build_notification_email(user_data, vacancies)

        assert "Score: pendiente" in body
