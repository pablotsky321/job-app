"""
Tests for Scoring_Worker Lambda handler.

Covers:
- Idempotence: scoreProfileVersion check prevents redundant scoring
- Bedrock response validation: ScoringResult model enforcement
- Prefiltro routing: filtered_out vs scoring path

Requirements: 13.6, 16, 17
"""

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.shared.models import ScoringMessage, ScoringResult, UsuarioVacante


# ============================================================================
# ScoringResult VALIDATION TESTS (pure, no mocks needed)
# ============================================================================


class TestScoringResultValidation:
    """Test ScoringResult Pydantic model validation."""

    def test_valid_scoring_result(self):
        """Valid ScoringResult passes validation."""
        data = {
            "score": 75,
            "veredicto": "buen_encaje",
            "coincidencias": ["Python", "FastAPI"],
            "faltantes": ["Kubernetes"],
            "resumen": "Buen match general con gaps en infraestructura.",
        }
        result = ScoringResult(**data)
        assert result.score == 75
        assert result.veredicto == "buen_encaje"
        assert result.coincidencias == ["Python", "FastAPI"]
        assert result.faltantes == ["Kubernetes"]

    def test_score_below_zero_fails(self):
        """Score < 0 fails validation."""
        data = {
            "score": -1,
            "veredicto": "bajo",
            "coincidencias": [],
            "faltantes": [],
            "resumen": "No match.",
        }
        with pytest.raises(ValidationError):
            ScoringResult(**data)

    def test_score_above_100_fails(self):
        """Score > 100 fails validation."""
        data = {
            "score": 101,
            "veredicto": "excelente",
            "coincidencias": [],
            "faltantes": [],
            "resumen": "Match perfecto.",
        }
        with pytest.raises(ValidationError):

            ScoringResult(**data)

    def test_missing_veredicto_fails(self):
        """Missing veredicto fails validation."""
        data = {
            "score": 50,
            "coincidencias": [],
            "faltantes": [],
            "resumen": "Algo.",
        }
        with pytest.raises(ValidationError):
            ScoringResult(**data)

    def test_missing_resumen_fails(self):
        """Missing resumen fails validation."""
        data = {
            "score": 50,
            "veredicto": "parcial",
            "coincidencias": [],
            "faltantes": [],
        }
        with pytest.raises(ValidationError):
            ScoringResult(**data)

    def test_score_boundary_zero(self):
        """Score = 0 is valid."""
        data = {
            "score": 0,
            "veredicto": "bajo",
            "coincidencias": [],
            "faltantes": ["Todo"],
            "resumen": "No hay match.",
        }
        result = ScoringResult(**data)
        assert result.score == 0

    def test_score_boundary_100(self):
        """Score = 100 is valid."""
        data = {
            "score": 100,
            "veredicto": "excelente",
            "coincidencias": ["Todo"],
            "faltantes": [],
            "resumen": "Match perfecto.",
        }
        result = ScoringResult(**data)
        assert result.score == 100

    def test_extra_fields_ignored(self):
        """Extra fields are ignored (ConfigDict extra='ignore')."""
        data = {
            "score": 60,
            "veredicto": "parcial",
            "coincidencias": [],
            "faltantes": [],
            "resumen": "Parcial.",
            "extra_field": "should be ignored",
        }
        result = ScoringResult(**data)
        assert result.score == 60
        assert not hasattr(result, "extra_field")


# ============================================================================
# ScoringMessage VALIDATION TESTS
# ============================================================================


class TestScoringMessageValidation:
    """Test ScoringMessage model validation."""

    def test_valid_message(self):
        """Valid ScoringMessage passes."""
        msg = ScoringMessage(userId="user-123", vacancyId="abc" * 21 + "a")
        assert msg.userId == "user-123"

    def test_missing_userId_fails(self):
        """Missing userId fails."""
        with pytest.raises(ValidationError):
            ScoringMessage(vacancyId="abc123")

    def test_missing_vacancyId_fails(self):
        """Missing vacancyId fails."""
        with pytest.raises(ValidationError):
            ScoringMessage(userId="user-123")


# ============================================================================
# UsuarioVacante MODEL TESTS
# ============================================================================


class TestUsuarioVacanteModel:
    """Test UsuarioVacante model."""

    def test_nueva_state_with_score(self):
        """UsuarioVacante in 'nueva' state with score has all fields."""
        uv = UsuarioVacante(
            userId="user-1",
            companyId="company-1",
            vacancyId="vac-1",
            score=85,
            scoreDetalle={"veredicto": "excelente"},
            scoreProfileVersion=3,
            estado="nueva",
        )
        assert uv.score == 85
        assert uv.estado == "nueva"
        assert uv.scoreProfileVersion == 3
        assert uv.companyId == "company-1"

    def test_filtered_out_state(self):
        """UsuarioVacante in 'filtered_out' state has no score."""
        uv = UsuarioVacante(
            userId="user-1",
            companyId="company-1",
            vacancyId="vac-1",
            estado="filtered_out",
        )
        assert uv.score is None
        assert uv.scoreDetalle is None

    def test_score_out_of_range_fails(self):
        """Score outside 0-100 fails."""
        with pytest.raises(ValidationError):
            UsuarioVacante(
                userId="user-1",
                companyId="company-1",
                vacancyId="vac-1",
                score=150,
                estado="nueva",
            )


# ============================================================================
# SCORING WORKER INTEGRATION TESTS (with mocks)
# ============================================================================


class TestScoringWorkerIdempotence:
    """Test scoreProfileVersion idempotence check (Requirement 13.6)."""

    @patch("backend.workers.scoring_worker._get_perfil")
    @patch("backend.workers.scoring_worker._get_usuario_vacante")
    @patch("backend.workers.scoring_worker._get_vacante")
    @patch("backend.workers.scoring_worker._put_usuario_vacante")
    @patch("backend.workers.scoring_worker.get_bedrock_client")
    def test_skip_when_score_version_matches_profile(
        self,
        mock_bedrock,
        mock_put_uv,
        mock_get_vacante,
        mock_get_uv,
        mock_get_perfil,
    ):
        """When scoreProfileVersion == profileVersion, skip scoring entirely."""
        from backend.workers.scoring_worker import handler_scoring_worker

        mock_get_perfil.return_value = {
            "userId": "user-1",
            "profileVersion": 5,
            "cargosActivos": ["Desarrollador"],
            "resumenParaMatching": "Python dev con 5 años.",
        }
        mock_get_uv.return_value = {
            "userId": "user-1",
            "vacancyId": "vac-1",
            "scoreProfileVersion": 5,  # Same as profileVersion
            "score": 80,
            "estado": "scored",
        }

        event = _make_sqs_event("user-1", "vac-1")
        handler_scoring_worker(event, None)

        # Should NOT fetch vacante, NOT call Bedrock, NOT put new record
        mock_get_vacante.assert_not_called()
        mock_bedrock.assert_not_called()
        mock_put_uv.assert_not_called()

    @patch("backend.workers.scoring_worker._get_perfil")
    @patch("backend.workers.scoring_worker._get_usuario_vacante")
    @patch("backend.workers.scoring_worker._get_vacante")
    @patch("backend.workers.scoring_worker._put_usuario_vacante")
    @patch("backend.workers.scoring_worker.get_bedrock_client")
    def test_proceed_when_no_existing_record(
        self,
        mock_bedrock,
        mock_put_uv,
        mock_get_vacante,
        mock_get_uv,
        mock_get_perfil,
    ):
        """When no UsuarioVacante exists, proceed with scoring (Requirement 13.7)."""
        from backend.workers.scoring_worker import handler_scoring_worker

        mock_get_perfil.return_value = {
            "userId": "user-1",
            "profileVersion": 1,
            "cargosActivos": ["Desarrollador Python"],
            "resumenParaMatching": "Python dev con 5 años.",
        }
        mock_get_uv.return_value = None  # No existing record

        mock_get_vacante.return_value = {
            "vacanteSha256": "vac-1",
            "titulo": "Desarrollador Python Senior",
            "descripcion": "Buscamos dev Python.",
            "requisitos": ["Python", "FastAPI"],
        }

        # Mock Bedrock
        mock_client = MagicMock()
        mock_client.invoke_with_retry.return_value = ScoringResult(
            score=78,
            veredicto="buen_encaje",
            coincidencias=["Python"],
            faltantes=["Kubernetes"],
            resumen="Buen match.",
        )
        mock_bedrock.return_value = mock_client

        event = _make_sqs_event("user-1", "vac-1")
        handler_scoring_worker(event, None)

        # Should have persisted the result
        mock_put_uv.assert_called_once()
        put_call_item = mock_put_uv.call_args[0][0]
        assert put_call_item["score"] == 78
        assert put_call_item["estado"] == "scored"
        assert put_call_item["scoreProfileVersion"] == 1

    @patch("backend.workers.scoring_worker._get_perfil")
    @patch("backend.workers.scoring_worker._get_usuario_vacante")
    @patch("backend.workers.scoring_worker._get_vacante")
    @patch("backend.workers.scoring_worker._put_usuario_vacante")
    @patch("backend.workers.scoring_worker.get_bedrock_client")
    def test_rescore_when_profile_version_changed(
        self,
        mock_bedrock,
        mock_put_uv,
        mock_get_vacante,
        mock_get_uv,
        mock_get_perfil,
    ):
        """When scoreProfileVersion != profileVersion, rescore (Requirement 13.8 staleness)."""
        from backend.workers.scoring_worker import handler_scoring_worker

        mock_get_perfil.return_value = {
            "userId": "user-1",
            "profileVersion": 7,  # Changed from 5 to 7
            "cargosActivos": ["Ingeniero Backend"],
            "resumenParaMatching": "Backend engineer.",
        }
        mock_get_uv.return_value = {
            "userId": "user-1",
            "vacancyId": "vac-1",
            "scoreProfileVersion": 5,  # Old version
            "score": 60,
            "estado": "scored",
        }

        mock_get_vacante.return_value = {
            "vacanteSha256": "vac-1",
            "titulo": "Ingeniero Backend Senior",
            "descripcion": "Backend role.",
            "requisitos": ["Python", "AWS"],
        }

        mock_client = MagicMock()
        mock_client.invoke_with_retry.return_value = ScoringResult(
            score=85,
            veredicto="excelente",
            coincidencias=["Python", "AWS"],
            faltantes=[],
            resumen="Excelente match.",
        )
        mock_bedrock.return_value = mock_client

        event = _make_sqs_event("user-1", "vac-1")
        handler_scoring_worker(event, None)

        # Should rescore with new profile version
        mock_put_uv.assert_called_once()
        put_call_item = mock_put_uv.call_args[0][0]
        assert put_call_item["score"] == 85
        assert put_call_item["scoreProfileVersion"] == 7


class TestScoringWorkerPrefiltro:
    """Test Prefiltro_Cargos routing (Requirement 16)."""

    @patch("backend.workers.scoring_worker._get_perfil")
    @patch("backend.workers.scoring_worker._get_usuario_vacante")
    @patch("backend.workers.scoring_worker._get_vacante")
    @patch("backend.workers.scoring_worker._put_usuario_vacante")
    @patch("backend.workers.scoring_worker.get_bedrock_client")
    def test_filtered_out_when_no_token_overlap(
        self,
        mock_bedrock,
        mock_put_uv,
        mock_get_vacante,
        mock_get_uv,
        mock_get_perfil,
    ):
        """When titulo has no overlap with cargosActivos, set estado='filtered_out'."""
        from backend.workers.scoring_worker import handler_scoring_worker

        mock_get_perfil.return_value = {
            "userId": "user-1",
            "profileVersion": 1,
            "cargosActivos": ["Chef Ejecutivo"],
            "resumenParaMatching": "Chef con 10 años.",
        }
        mock_get_uv.return_value = None

        mock_get_vacante.return_value = {
            "vacanteSha256": "vac-1",
            "titulo": "Ingeniero de Software Senior",
            "descripcion": "Programador en Python.",
            "requisitos": ["Python"],
        }

        event = _make_sqs_event("user-1", "vac-1")
        handler_scoring_worker(event, None)

        # Bedrock should NOT be called
        mock_bedrock.assert_not_called()

        # Should persist filtered_out
        mock_put_uv.assert_called_once()
        put_call_item = mock_put_uv.call_args[0][0]
        assert put_call_item["estado"] == "filtered_out"
        assert "score" not in put_call_item

    @patch("backend.workers.scoring_worker._get_perfil")
    @patch("backend.workers.scoring_worker._get_usuario_vacante")
    @patch("backend.workers.scoring_worker._get_vacante")
    @patch("backend.workers.scoring_worker._put_usuario_vacante")
    @patch("backend.workers.scoring_worker.get_bedrock_client")
    def test_bypass_prefiltro_when_cargos_empty(
        self,
        mock_bedrock,
        mock_put_uv,
        mock_get_vacante,
        mock_get_uv,
        mock_get_perfil,
    ):
        """When cargosActivos is empty, bypass prefiltro and invoke Bedrock (Req 16.5)."""
        from backend.workers.scoring_worker import handler_scoring_worker

        mock_get_perfil.return_value = {
            "userId": "user-1",
            "profileVersion": 1,
            "cargosActivos": [],  # Empty!
            "resumenParaMatching": "Generalist.",
        }
        mock_get_uv.return_value = None

        mock_get_vacante.return_value = {
            "vacanteSha256": "vac-1",
            "titulo": "Cualquier Cargo",
            "descripcion": "Algo.",
            "requisitos": [],
        }

        mock_client = MagicMock()
        mock_client.invoke_with_retry.return_value = ScoringResult(
            score=50,
            veredicto="parcial",
            coincidencias=[],
            faltantes=[],
            resumen="Parcial match.",
        )
        mock_bedrock.return_value = mock_client

        event = _make_sqs_event("user-1", "vac-1")
        handler_scoring_worker(event, None)

        # Bedrock SHOULD be called even though titulo doesn't matter
        mock_client.invoke_with_retry.assert_called_once()
        mock_put_uv.assert_called_once()
        put_call_item = mock_put_uv.call_args[0][0]
        assert put_call_item["estado"] == "scored"

    @patch("backend.workers.scoring_worker._get_perfil")
    @patch("backend.workers.scoring_worker._get_usuario_vacante")
    @patch("backend.workers.scoring_worker._get_vacante")
    @patch("backend.workers.scoring_worker._put_usuario_vacante")
    @patch("backend.workers.scoring_worker.get_bedrock_client")
    def test_passes_prefiltro_when_token_overlap_exists(
        self,
        mock_bedrock,
        mock_put_uv,
        mock_get_vacante,
        mock_get_uv,
        mock_get_perfil,
    ):
        """When titulo shares significant token with cargo, proceed to scoring."""
        from backend.workers.scoring_worker import handler_scoring_worker

        mock_get_perfil.return_value = {
            "userId": "user-1",
            "profileVersion": 2,
            "cargosActivos": ["Desarrollador Python"],
            "resumenParaMatching": "Dev Python.",
        }
        mock_get_uv.return_value = None

        mock_get_vacante.return_value = {
            "vacanteSha256": "vac-1",
            "titulo": "Desarrollador Python Senior",
            "descripcion": "Python backend dev.",
            "requisitos": ["Python"],
        }

        mock_client = MagicMock()
        mock_client.invoke_with_retry.return_value = ScoringResult(
            score=90,
            veredicto="excelente",
            coincidencias=["Python"],
            faltantes=[],
            resumen="Excelente match.",
        )
        mock_bedrock.return_value = mock_client

        event = _make_sqs_event("user-1", "vac-1")
        handler_scoring_worker(event, None)

        # Should call Bedrock and persist scored
        mock_client.invoke_with_retry.assert_called_once()
        mock_put_uv.assert_called_once()
        put_call_item = mock_put_uv.call_args[0][0]
        assert put_call_item["estado"] == "scored"
        assert put_call_item["score"] == 90


class TestScoringWorkerBedrockValidation:
    """Test Bedrock response validation behavior (Requirement 17)."""

    @patch("backend.workers.scoring_worker._get_perfil")
    @patch("backend.workers.scoring_worker._get_usuario_vacante")
    @patch("backend.workers.scoring_worker._get_vacante")
    @patch("backend.workers.scoring_worker._put_usuario_vacante")
    @patch("backend.workers.scoring_worker.get_bedrock_client")
    def test_validation_error_raises_for_sqs_retry(
        self,
        mock_bedrock,
        mock_put_uv,
        mock_get_vacante,
        mock_get_uv,
        mock_get_perfil,
    ):
        """When Bedrock validation fails after retry, raise for SQS redelivery."""
        from backend.workers.scoring_worker import handler_scoring_worker

        mock_get_perfil.return_value = {
            "userId": "user-1",
            "profileVersion": 1,
            "cargosActivos": ["Backend"],
            "resumenParaMatching": "Dev.",
        }
        mock_get_uv.return_value = None

        mock_get_vacante.return_value = {
            "vacanteSha256": "vac-1",
            "titulo": "Backend Developer",
            "descripcion": "Build APIs.",
            "requisitos": ["Python"],
        }

        # Bedrock client raises ValidationError (after its internal retry)
        mock_client = MagicMock()
        mock_client.invoke_with_retry.side_effect = ValidationError.from_exception_data(
            title="ScoringResult",
            line_errors=[
                {
                    "type": "missing",
                    "loc": ("score",),
                    "msg": "Field required",
                    "input": {},
                }
            ],
        )
        mock_bedrock.return_value = mock_client

        event = _make_sqs_event("user-1", "vac-1")

        with pytest.raises(ValidationError):
            handler_scoring_worker(event, None)

        # Should NOT persist anything on validation failure (Req 17.3)
        mock_put_uv.assert_not_called()

    @patch("backend.workers.scoring_worker._get_perfil")
    @patch("backend.workers.scoring_worker._get_usuario_vacante")
    @patch("backend.workers.scoring_worker._get_vacante")
    @patch("backend.workers.scoring_worker._put_usuario_vacante")
    @patch("backend.workers.scoring_worker.get_bedrock_client")
    def test_successful_scoring_persists_all_fields(
        self,
        mock_bedrock,
        mock_put_uv,
        mock_get_vacante,
        mock_get_uv,
        mock_get_perfil,
    ):
        """Successful scoring persists score, scoreDetalle, scoreProfileVersion, estado."""
        from backend.workers.scoring_worker import handler_scoring_worker

        mock_get_perfil.return_value = {
            "userId": "user-1",
            "profileVersion": 3,
            "cargosActivos": ["Data Engineer"],
            "resumenParaMatching": "Data eng 5 years.",
        }
        mock_get_uv.return_value = None

        mock_get_vacante.return_value = {
            "vacanteSha256": "vac-1",
            "titulo": "Senior Data Engineer",
            "descripcion": "ETL pipelines.",
            "requisitos": ["Spark", "Python", "AWS"],
        }

        scoring_result = ScoringResult(
            score=72,
            veredicto="buen_encaje",
            coincidencias=["Python", "AWS"],
            faltantes=["Spark"],
            resumen="Buen perfil pero falta Spark.",
        )
        mock_client = MagicMock()
        mock_client.invoke_with_retry.return_value = scoring_result
        mock_bedrock.return_value = mock_client

        event = _make_sqs_event("user-1", "vac-1")
        handler_scoring_worker(event, None)

        mock_put_uv.assert_called_once()
        item = mock_put_uv.call_args[0][0]
        assert item["userId"] == "user-1"
        assert item["vacancyId"] == "vac-1"
        assert item["score"] == 72
        assert item["scoreProfileVersion"] == 3
        assert item["estado"] == "scored"
        assert item["scoreDetalle"]["veredicto"] == "buen_encaje"
        assert item["scoreDetalle"]["coincidencias"] == ["Python", "AWS"]
        assert item["scoreDetalle"]["faltantes"] == ["Spark"]
        assert "updatedAt" in item


# ============================================================================
# HELPER
# ============================================================================


def _make_sqs_event(user_id: str, vacancy_id: str) -> dict:
    """Create a minimal SQS event with one record."""
    body = json.dumps({"userId": user_id, "vacancyId": vacancy_id})
    return {
        "Records": [
            {
                "messageId": "test-msg-001",
                "body": body,
            }
        ]
    }
