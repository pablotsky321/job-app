"""
Unit tests for backend/shared/services/vacancy_service.py.

Tests cover:
- activas filter keeps only nueva/vista
- aplicadas filter keeps only aplicada
- score-descending sort with nulls last
- lastSeenAt tie-break for equal scores
- appliedAt descending sort
- staleness flag on version mismatch
- staleness flag on null version + nueva estado
- cvAtsTexto never present in output

Requirements: 1.1, 1.2, 1.6, 1.7, 1.8
"""

import pytest
from backend.shared.services.vacancy_service import build_vacancy_listing


# ============================================================================
# FIXTURES / HELPERS
# ============================================================================


def _make_uv(
    company_id: str = "comp1",
    vacancy_id: str = "vac1",
    estado: str = "nueva",
    score=80,
    score_profile_version=1,
    applied_at=None,
    cv_ats_texto=None,
):
    """Helper to build a UsuarioVacante dict."""
    record = {
        "userId": "user-123",
        "companyId": company_id,
        "vacancyId": vacancy_id,
        "estado": estado,
        "score": score,
        "scoreProfileVersion": score_profile_version,
        "appliedAt": applied_at,
        "createdAt": "2024-01-01T00:00:00Z",
    }
    if cv_ats_texto is not None:
        record["cvAtsTexto"] = cv_ats_texto
    return record


def _make_vacante_map(entries: list[tuple[str, str, dict]]) -> dict:
    """Build vacantes_by_id map from list of (companyId, vacancyId, extra_fields)."""
    result = {}
    for company_id, vacancy_id, fields in entries:
        key = f"{company_id}#{vacancy_id}"
        result[key] = {
            "titulo": fields.get("titulo", "Job Title"),
            "empresa_nombre": fields.get("empresa_nombre", "Company"),
            "empresa_plataforma": fields.get("empresa_plataforma", "greenhouse"),
            "lastSeenAt": fields.get("lastSeenAt", "2024-01-15T00:00:00Z"),
            **{k: v for k, v in fields.items() if k not in ("titulo", "empresa_nombre", "empresa_plataforma", "lastSeenAt")},
        }
    return result


# ============================================================================
# TEST: activas filter keeps only nueva/vista
# ============================================================================


class TestActivasFilter:
    def test_keeps_nueva_and_vista(self):
        """activas filter includes estado=nueva and estado=vista."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva"),
            _make_uv(vacancy_id="v2", estado="vista"),
            _make_uv(vacancy_id="v3", estado="aplicada"),
            _make_uv(vacancy_id="v4", estado="filtered_out"),
        ]
        vacantes = _make_vacante_map([
            ("comp1", "v1", {}),
            ("comp1", "v2", {}),
            ("comp1", "v3", {}),
            ("comp1", "v4", {}),
        ])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="activas")

        estados = [r["estado"] for r in result]
        assert set(estados) == {"nueva", "vista"}
        assert len(result) == 2

    def test_excludes_aplicada_and_filtered_out(self):
        """activas filter excludes aplicada and filtered_out."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="aplicada"),
            _make_uv(vacancy_id="v2", estado="filtered_out"),
        ]
        vacantes = _make_vacante_map([
            ("comp1", "v1", {}),
            ("comp1", "v2", {}),
        ])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="activas")
        assert result == []


# ============================================================================
# TEST: aplicadas filter keeps only aplicada
# ============================================================================


class TestAplicadasFilter:
    def test_keeps_only_aplicada(self):
        """aplicadas filter includes only estado=aplicada."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva"),
            _make_uv(vacancy_id="v2", estado="vista"),
            _make_uv(vacancy_id="v3", estado="aplicada", applied_at="2024-02-01T00:00:00Z"),
        ]
        vacantes = _make_vacante_map([
            ("comp1", "v1", {}),
            ("comp1", "v2", {}),
            ("comp1", "v3", {}),
        ])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="aplicadas")

        assert len(result) == 1
        assert result[0]["estado"] == "aplicada"

    def test_excludes_nueva_vista_filtered_out(self):
        """aplicadas filter excludes nueva, vista, filtered_out."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva"),
            _make_uv(vacancy_id="v2", estado="vista"),
            _make_uv(vacancy_id="v3", estado="filtered_out"),
        ]
        vacantes = _make_vacante_map([
            ("comp1", "v1", {}),
            ("comp1", "v2", {}),
            ("comp1", "v3", {}),
        ])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="aplicadas")
        assert result == []


# ============================================================================
# TEST: score-descending sort with nulls last
# ============================================================================


class TestScoreSort:
    def test_score_descending_order(self):
        """activas are sorted by score descending."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva", score=50),
            _make_uv(vacancy_id="v2", estado="nueva", score=90),
            _make_uv(vacancy_id="v3", estado="nueva", score=70),
        ]
        vacantes = _make_vacante_map([
            ("comp1", "v1", {}),
            ("comp1", "v2", {}),
            ("comp1", "v3", {}),
        ])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="activas")

        scores = [r["score"] for r in result]
        assert scores == [90, 70, 50]

    def test_null_scores_last(self):
        """Records with null score appear after all scored records."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva", score=None),
            _make_uv(vacancy_id="v2", estado="nueva", score=60),
            _make_uv(vacancy_id="v3", estado="nueva", score=None),
            _make_uv(vacancy_id="v4", estado="nueva", score=80),
        ]
        vacantes = _make_vacante_map([
            ("comp1", "v1", {}),
            ("comp1", "v2", {}),
            ("comp1", "v3", {}),
            ("comp1", "v4", {}),
        ])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="activas")

        scores = [r["score"] for r in result]
        # Non-null scores first (descending), then nulls
        assert scores == [80, 60, None, None]


# ============================================================================
# TEST: lastSeenAt tie-break for equal scores
# ============================================================================


class TestLastSeenAtTieBreak:
    def test_same_score_sorted_by_last_seen_at_descending(self):
        """When scores are equal, sort by Vacante.lastSeenAt descending."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva", score=75),
            _make_uv(vacancy_id="v2", estado="nueva", score=75),
            _make_uv(vacancy_id="v3", estado="nueva", score=75),
        ]
        vacantes = _make_vacante_map([
            ("comp1", "v1", {"lastSeenAt": "2024-01-10T00:00:00Z"}),
            ("comp1", "v2", {"lastSeenAt": "2024-01-20T00:00:00Z"}),
            ("comp1", "v3", {"lastSeenAt": "2024-01-15T00:00:00Z"}),
        ])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="activas")

        vacancy_ids = [r["vacancyId"] for r in result]
        # Most recent lastSeenAt first
        assert vacancy_ids == ["v2", "v3", "v1"]


# ============================================================================
# TEST: appliedAt descending sort
# ============================================================================


class TestAppliedAtSort:
    def test_aplicadas_sorted_by_applied_at_descending(self):
        """aplicadas are sorted by appliedAt descending."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="aplicada", applied_at="2024-01-05T00:00:00Z"),
            _make_uv(vacancy_id="v2", estado="aplicada", applied_at="2024-01-20T00:00:00Z"),
            _make_uv(vacancy_id="v3", estado="aplicada", applied_at="2024-01-10T00:00:00Z"),
        ]
        vacantes = _make_vacante_map([
            ("comp1", "v1", {}),
            ("comp1", "v2", {}),
            ("comp1", "v3", {}),
        ])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="aplicadas")

        vacancy_ids = [r["vacancyId"] for r in result]
        assert vacancy_ids == ["v2", "v3", "v1"]


# ============================================================================
# TEST: staleness flag on version mismatch
# ============================================================================


class TestStalenessFlag:
    def test_stale_when_version_mismatch(self):
        """staleFlag=True when scoreProfileVersion != profile_version."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva", score=80, score_profile_version=1),
            _make_uv(vacancy_id="v2", estado="nueva", score=70, score_profile_version=2),
        ]
        vacantes = _make_vacante_map([
            ("comp1", "v1", {}),
            ("comp1", "v2", {}),
        ])

        # Current profile version is 2
        result = build_vacancy_listing(uvs, vacantes, profile_version=2, estado_filter="activas")

        # v1 has scoreProfileVersion=1 but profile is 2 → stale
        # v2 has scoreProfileVersion=2 matching profile → not stale
        result_by_id = {r["vacancyId"]: r for r in result}
        assert result_by_id["v1"]["staleFlag"] is True
        assert result_by_id["v2"]["staleFlag"] is False

    def test_stale_when_null_version_and_nueva(self):
        """staleFlag=True when scoreProfileVersion is None and estado=nueva."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva", score=None, score_profile_version=None),
        ]
        vacantes = _make_vacante_map([("comp1", "v1", {})])

        result = build_vacancy_listing(uvs, vacantes, profile_version=2, estado_filter="activas")

        assert result[0]["staleFlag"] is True

    def test_not_stale_when_null_version_and_vista(self):
        """staleFlag=False when scoreProfileVersion is None but estado=vista (not nueva)."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="vista", score=60, score_profile_version=None),
        ]
        vacantes = _make_vacante_map([("comp1", "v1", {})])

        result = build_vacancy_listing(uvs, vacantes, profile_version=2, estado_filter="activas")

        # scoreProfileVersion is None but estado is vista, not nueva → not stale
        # Wait — requirement says staleFlag when scoreProfileVersion != profile_version
        # OR when scoreProfileVersion is None AND estado == nueva.
        # If scoreProfileVersion is None: check if estado==nueva → True
        # If scoreProfileVersion is None but estado != nueva → the first condition
        # (scoreProfileVersion != profile_version) applies: None != 2 → ...
        # Actually re-reading the requirement: the two conditions are:
        # 1. scoreProfileVersion != profile_version
        # 2. scoreProfileVersion is null AND estado == nueva
        # These are OR conditions. But condition 1 with None:
        # If scoreProfileVersion is None, it's "not equal" to profile_version (which is 2).
        # Hmm, need to re-read the task definition more carefully.
        # Task says: "staleFlag=True when scoreProfileVersion != profile_version,
        # or when scoreProfileVersion is null AND estado == nueva"
        # This implies condition 1 only applies when scoreProfileVersion is NOT null.
        # Otherwise condition 2 handles the null case (only for nueva).
        # So for vista with null scoreProfileVersion → staleFlag=False.
        assert result[0]["staleFlag"] is False

    def test_not_stale_when_version_matches(self):
        """staleFlag=False when scoreProfileVersion equals profile_version."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva", score=80, score_profile_version=3),
        ]
        vacantes = _make_vacante_map([("comp1", "v1", {})])

        result = build_vacancy_listing(uvs, vacantes, profile_version=3, estado_filter="activas")

        assert result[0]["staleFlag"] is False


# ============================================================================
# TEST: cvAtsTexto never present in output
# ============================================================================


class TestCvAtsTextoExcluded:
    def test_cv_ats_texto_excluded_from_activas(self):
        """cvAtsTexto is never included in output records for activas."""
        uvs = [
            _make_uv(vacancy_id="v1", estado="nueva", cv_ats_texto="My optimized CV text..."),
        ]
        vacantes = _make_vacante_map([("comp1", "v1", {})])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="activas")

        assert "cvAtsTexto" not in result[0]

    def test_cv_ats_texto_excluded_from_aplicadas(self):
        """cvAtsTexto is never included in output records for aplicadas."""
        uvs = [
            _make_uv(
                vacancy_id="v1",
                estado="aplicada",
                applied_at="2024-01-10T00:00:00Z",
                cv_ats_texto="Some CV text here",
            ),
        ]
        vacantes = _make_vacante_map([("comp1", "v1", {})])

        result = build_vacancy_listing(uvs, vacantes, profile_version=1, estado_filter="aplicadas")

        assert "cvAtsTexto" not in result[0]
