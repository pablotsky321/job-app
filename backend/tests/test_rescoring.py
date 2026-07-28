"""
Tests for backend/shared/rescoring.py

Covers:
- is_score_stale: pure boolean logic for staleness detection
- enqueue_rescore: mocked SQS send_message
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.shared.models import Perfiles, UsuarioVacante
from backend.shared.rescoring import enqueue_rescore, is_score_stale


# ============================================================================
# is_score_stale — pure function tests (no I/O)
# ============================================================================


class TestIsScoreStale:
    """Tests for the pure staleness-detection function."""

    def _make_usuario_vacante(self, score_profile_version: int) -> UsuarioVacante:
        return UsuarioVacante(
            userId="user-1",
            vacancyId="vac-1",
            score=75,
            scoreProfileVersion=score_profile_version,
            estado="scored",
            updatedAt=datetime(2024, 1, 1),
        )

    def _make_perfil(self, profile_version: int) -> Perfiles:
        return Perfiles(
            userId="user-1",
            profileVersion=profile_version,
            updatedAt=datetime(2024, 1, 1),
        )

    def test_returns_false_when_versions_match(self):
        uv = self._make_usuario_vacante(score_profile_version=3)
        perfil = self._make_perfil(profile_version=3)
        assert is_score_stale(uv, perfil) is False

    def test_returns_true_when_versions_differ(self):
        uv = self._make_usuario_vacante(score_profile_version=2)
        perfil = self._make_perfil(profile_version=3)
        assert is_score_stale(uv, perfil) is True

    def test_returns_true_when_score_version_ahead(self):
        """Edge case: scoreProfileVersion > profileVersion (shouldn't happen, but still stale)."""
        uv = self._make_usuario_vacante(score_profile_version=5)
        perfil = self._make_perfil(profile_version=3)
        assert is_score_stale(uv, perfil) is True

    def test_returns_false_when_usuario_vacante_is_none(self):
        perfil = self._make_perfil(profile_version=3)
        assert is_score_stale(None, perfil) is False

    def test_returns_true_when_score_profile_version_is_none(self):
        """scoreProfileVersion=None means never scored → stale relative to any version."""
        uv = UsuarioVacante(
            userId="user-1",
            vacancyId="vac-1",
            score=None,
            scoreProfileVersion=None,
            estado="pending",
            updatedAt=datetime(2024, 1, 1),
        )
        perfil = self._make_perfil(profile_version=1)
        assert is_score_stale(uv, perfil) is True

    def test_returns_false_when_both_versions_zero(self):
        uv = self._make_usuario_vacante(score_profile_version=0)
        perfil = self._make_perfil(profile_version=0)
        assert is_score_stale(uv, perfil) is False


# ============================================================================
# enqueue_rescore — mocked SQS tests
# ============================================================================


class TestEnqueueRescore:
    """Tests for the SQS enqueue function with mocked boto3."""

    @patch("backend.shared.rescoring.boto3")
    def test_returns_true_on_successful_send(self, mock_boto3, monkeypatch):
        monkeypatch.setenv("SQS_SCORING_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/scoring")
        mock_sqs = MagicMock()
        mock_boto3.client.return_value = mock_sqs

        result = enqueue_rescore("user-1", "vacancy-abc123")

        assert result is True
        mock_boto3.client.assert_called_once_with("sqs")
        mock_sqs.send_message.assert_called_once()

        # Verify the message payload
        call_kwargs = mock_sqs.send_message.call_args[1]
        assert call_kwargs["QueueUrl"] == "https://sqs.us-east-1.amazonaws.com/123/scoring"
        body = json.loads(call_kwargs["MessageBody"])
        assert body["userId"] == "user-1"
        assert body["vacancyId"] == "vacancy-abc123"

    @patch("backend.shared.rescoring.boto3")
    def test_returns_false_on_sqs_error(self, mock_boto3, monkeypatch):
        monkeypatch.setenv("SQS_SCORING_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/scoring")
        mock_sqs = MagicMock()
        mock_sqs.send_message.side_effect = Exception("Connection timeout")
        mock_boto3.client.return_value = mock_sqs

        result = enqueue_rescore("user-1", "vacancy-abc123")

        assert result is False

    def test_returns_false_when_queue_url_not_set(self, monkeypatch):
        monkeypatch.delenv("SQS_SCORING_QUEUE_URL", raising=False)

        result = enqueue_rescore("user-1", "vacancy-abc123")

        assert result is False

    @patch("backend.shared.rescoring.boto3")
    def test_never_raises_on_error(self, mock_boto3, monkeypatch):
        """enqueue_rescore must never raise — always returns bool."""
        monkeypatch.setenv("SQS_SCORING_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/scoring")
        mock_sqs = MagicMock()
        mock_sqs.send_message.side_effect = RuntimeError("Unexpected error")
        mock_boto3.client.return_value = mock_sqs

        # Should not raise
        result = enqueue_rescore("user-1", "vacancy-abc123")
        assert result is False

    @patch("backend.shared.rescoring.boto3")
    def test_publishes_exactly_one_message(self, mock_boto3, monkeypatch):
        """Requirement 18.3: publishes exactly one ScoringMessage."""
        monkeypatch.setenv("SQS_SCORING_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/scoring")
        mock_sqs = MagicMock()
        mock_boto3.client.return_value = mock_sqs

        enqueue_rescore("user-1", "vacancy-xyz")

        assert mock_sqs.send_message.call_count == 1
