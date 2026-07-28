"""
Unit tests for detect_language heuristic.

Requirements: 5.3
"""

import pytest

from backend.shared.normalization import detect_language


class TestDetectLanguage:
    """Tests for language detection heuristic in normalization module."""

    def test_clearly_spanish_text_returns_es(self):
        """Clearly Spanish vacancy text should return 'es'."""
        titulo = "Desarrollador Backend Senior"
        descripcion = (
            "Empresa líder en tecnología busca ingeniero con experiencia en Python. "
            "Requisitos: conocimientos en bases de datos, habilidades de trabajo en equipo. "
            "Modalidad remoto. Ubicación Colombia."
        )
        assert detect_language(titulo, descripcion) == "es"

    def test_clearly_english_text_returns_en(self):
        """Clearly English vacancy text should return 'en'."""
        titulo = "Senior Backend Developer"
        descripcion = (
            "We are looking for an engineer with experience in Python. "
            "Requirements: skills in databases, knowledge of cloud services. "
            "Location: remote. This is a great opportunity to work with our team."
        )
        assert detect_language(titulo, descripcion) == "en"

    def test_empty_text_returns_es(self):
        """Empty text should default to 'es'."""
        assert detect_language("", "") == "es"

    def test_none_like_empty_returns_es(self):
        """Whitespace-only text should default to 'es'."""
        assert detect_language("   ", "   ") == "es"

    def test_ambiguous_mixed_text_returns_es(self):
        """Mixed/ambiguous text should default to 'es' (tie defaults to Spanish)."""
        titulo = "Developer Desarrollador"
        descripcion = "Experience experiencia requirements requisitos"
        assert detect_language(titulo, descripcion) == "es"

    def test_spanish_title_only(self):
        """Spanish title with empty description should return 'es'."""
        assert detect_language("Ingeniero de Datos con experiencia", "") == "es"

    def test_english_title_only(self):
        """English title with enough indicators should return 'en'."""
        assert detect_language("Senior Engineer", "requirements experience skills team role") == "en"

    def test_tie_defaults_to_spanish(self):
        """Equal counts of Spanish and English indicators default to 'es'."""
        # One Spanish word, one English word
        titulo = "empresa company"
        descripcion = ""
        assert detect_language(titulo, descripcion) == "es"
