"""
Unit tests for prefiltro_cargos — pure token matching logic.

Tests cover:
- get_significant_tokens: lowercasing, diacritic removal, stopword filtering,
  punctuation splitting
- pasa_prefiltro_cargos: token overlap, empty cargosActivos bypass,
  no overlap rejection, threshold behavior

NO AWS mocks. Pure function tests only.

Requirements: 16.2-16.7
"""

import os
import pytest

from backend.shared.prefiltro_cargos import (
    get_significant_tokens,
    pasa_prefiltro_cargos,
    _get_threshold,
    STOPWORDS,
)


# ============================================================================
# get_significant_tokens tests
# ============================================================================


class TestGetSignificantTokens:
    """Tests for token extraction logic."""

    def test_basic_lowercasing(self):
        """Tokens are lowercased."""
        result = get_significant_tokens("Ingeniero Software")
        assert "ingeniero" in result
        assert "software" in result

    def test_diacritic_removal(self):
        """Accented characters are normalized to ASCII equivalents."""
        result = get_significant_tokens("Diseñador Gráfico")
        assert "disenador" in result
        assert "grafico" in result

    def test_accent_on_common_words(self):
        """Spanish accented words like más, también are normalized and removed as stopwords."""
        result = get_significant_tokens("más de lo esperado")
        # "mas" is a stopword, "de" and "lo" are stopwords
        assert "mas" not in result
        assert "de" not in result
        assert "lo" not in result
        assert "esperado" in result

    def test_stopword_removal(self):
        """Spanish stopwords are removed from token set."""
        result = get_significant_tokens("Director de Ventas para el Mercado")
        assert "de" not in result
        assert "para" not in result
        assert "el" not in result
        assert "director" in result
        assert "ventas" in result
        assert "mercado" in result

    def test_all_stopwords_filtered(self):
        """All defined stopwords are properly filtered."""
        for sw in STOPWORDS:
            result = get_significant_tokens(sw)
            assert sw not in result

    def test_split_on_hyphens(self):
        """Hyphenated terms are split into separate tokens."""
        result = get_significant_tokens("Full-Stack Developer")
        assert "full" in result
        assert "stack" in result
        assert "developer" in result

    def test_split_on_slashes(self):
        """Slashes split tokens."""
        result = get_significant_tokens("Frontend/Backend Engineer")
        assert "frontend" in result
        assert "backend" in result
        assert "engineer" in result

    def test_split_on_parentheses(self):
        """Parentheses and other punctuation split tokens."""
        result = get_significant_tokens("Analista (Junior)")
        assert "analista" in result
        assert "junior" in result

    def test_short_tokens_filtered(self):
        """Tokens shorter than 2 characters are removed."""
        result = get_significant_tokens("I am a QA lead")
        # "i", "a" are single chars → filtered; "am" stays (2 chars, not stopword)
        assert "am" in result  # 2 chars, not in STOPWORDS
        assert "qa" in result
        assert "lead" in result

    def test_empty_string(self):
        """Empty string returns empty set."""
        assert get_significant_tokens("") == set()

    def test_none_input(self):
        """None input returns empty set."""
        assert get_significant_tokens(None) == set()

    def test_only_stopwords(self):
        """Text with only stopwords returns empty set."""
        result = get_significant_tokens("de la en el por para")
        assert result == set()

    def test_numbers_preserved(self):
        """Numeric tokens are preserved if >= 2 chars."""
        result = get_significant_tokens("Python 3.12 Developer")
        assert "python" in result
        assert "12" in result
        assert "developer" in result

    def test_multiple_spaces_and_tabs(self):
        """Multiple spaces/tabs are handled correctly."""
        result = get_significant_tokens("  Ingeniero   Senior  ")
        assert "ingeniero" in result
        assert "senior" in result


# ============================================================================
# pasa_prefiltro_cargos tests
# ============================================================================


class TestPasaPrefiltroCargos:
    """Tests for the prefiltro decision function."""

    def test_empty_cargos_activos_bypasses(self):
        """Empty cargosActivos list returns True (bypass). Requirement 16.5"""
        assert pasa_prefiltro_cargos("Senior Engineer", []) is True

    def test_single_token_overlap_passes(self):
        """One token in common is enough with default threshold=1."""
        result = pasa_prefiltro_cargos(
            "Ingeniero de Software Senior",
            ["Ingeniero Backend"],
        )
        assert result is True  # "ingeniero" overlaps

    def test_no_overlap_fails(self):
        """No tokens in common returns False."""
        result = pasa_prefiltro_cargos(
            "Chef de Cocina",
            ["Ingeniero de Software"],
        )
        assert result is False

    def test_overlap_with_accents(self):
        """Accented title still matches non-accented cargo."""
        result = pasa_prefiltro_cargos(
            "Diseñador Gráfico Senior",
            ["Disenador Grafico"],
        )
        assert result is True  # both normalize to "disenador", "grafico"

    def test_multiple_cargos_any_match(self):
        """If ANY cargo matches, returns True."""
        result = pasa_prefiltro_cargos(
            "Data Engineer",
            ["Frontend Developer", "Data Scientist", "Product Manager"],
        )
        assert result is True  # "data" overlaps with "Data Scientist"

    def test_threshold_2_requires_two_tokens(self):
        """With threshold=2, need at least 2 tokens in common."""
        # Only "ingeniero" overlaps
        result = pasa_prefiltro_cargos(
            "Ingeniero de Ventas",
            ["Ingeniero de Software"],
            threshold=2,
        )
        assert result is False  # only 1 token overlaps

        # "ingeniero" and "software" overlap
        result = pasa_prefiltro_cargos(
            "Ingeniero de Software Junior",
            ["Ingeniero de Software"],
            threshold=2,
        )
        assert result is True  # 2 tokens overlap

    def test_threshold_higher_than_possible(self):
        """Threshold higher than available tokens returns False."""
        result = pasa_prefiltro_cargos(
            "Developer",
            ["Developer"],
            threshold=5,
        )
        assert result is False  # only 1 token available

    def test_stopwords_dont_count_as_overlap(self):
        """Stopwords removed before comparison, so they don't contribute to overlap."""
        # "de" and "la" are stopwords, only overlap if significant tokens match
        result = pasa_prefiltro_cargos(
            "Jefe de la Cocina",
            ["Director de la Oficina"],
        )
        assert result is False  # no significant overlap

    def test_titulo_with_no_significant_tokens(self):
        """Titulo with all stopwords returns False."""
        result = pasa_prefiltro_cargos(
            "de la en el",
            ["Ingeniero Software"],
        )
        assert result is False

    def test_case_insensitive_matching(self):
        """Matching is case-insensitive."""
        result = pasa_prefiltro_cargos(
            "SENIOR DEVELOPER",
            ["senior developer"],
        )
        assert result is True


# ============================================================================
# _get_threshold tests
# ============================================================================


class TestGetThreshold:
    """Tests for threshold environment variable reading."""

    def test_default_when_unset(self, monkeypatch):
        """Returns 1 when PREFILTRO_THRESHOLD is not set."""
        monkeypatch.delenv("PREFILTRO_THRESHOLD", raising=False)
        assert _get_threshold() == 1

    def test_default_when_empty(self, monkeypatch):
        """Returns 1 when PREFILTRO_THRESHOLD is empty string."""
        monkeypatch.setenv("PREFILTRO_THRESHOLD", "")
        assert _get_threshold() == 1

    def test_valid_positive_integer(self, monkeypatch):
        """Returns the parsed integer when valid."""
        monkeypatch.setenv("PREFILTRO_THRESHOLD", "3")
        assert _get_threshold() == 3

    def test_invalid_non_numeric(self, monkeypatch):
        """Returns 1 when value is not numeric."""
        monkeypatch.setenv("PREFILTRO_THRESHOLD", "abc")
        assert _get_threshold() == 1

    def test_zero_returns_default(self, monkeypatch):
        """Returns 1 when value is 0 (not positive)."""
        monkeypatch.setenv("PREFILTRO_THRESHOLD", "0")
        assert _get_threshold() == 1

    def test_negative_returns_default(self, monkeypatch):
        """Returns 1 when value is negative."""
        monkeypatch.setenv("PREFILTRO_THRESHOLD", "-2")
        assert _get_threshold() == 1
