"""
Tests for backend/main.py — _handle_async_resumen_generation and handler() dispatch.

Validates:
- Success path: Bedrock returns valid ResumenParaMatchingOutput -> persists
  resumenParaMatching + resumenGenerationStatus='complete'
- Bedrock invocation failure -> resumenGenerationStatus='failed', without
  touching any previous resumenParaMatching
- Pydantic validation failure after retry -> resumenGenerationStatus='failed',
  without touching any previous resumenParaMatching
- handler() dispatches event.mode == 'async_resumen_generation' to
  _handle_async_resumen_generation

Requirements: 2.3, 2.4, 2.5
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch
from pydantic import ValidationError

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.shared.models import ResumenParaMatchingOutput


@pytest.fixture
def mock_user_id():
    """Fixed user ID for testing."""
    return "test-user-123"


@pytest.fixture
def sample_perfil_estructurado():
    """Minimal structured profile used as input to resumen generation."""
    return {
        "experiencia": [],
        "educacion": [],
        "proyectos": [],
        "certificaciones": [],
        "skills": ["Python", "AWS"],
        "lenguajes": [],
    }


# ============================================================================
# _handle_async_resumen_generation Tests
# ============================================================================


def test_async_resumen_generation_success(mock_user_id, sample_perfil_estructurado):
    """Bedrock returns a valid ResumenParaMatchingOutput -> persists
    resumenParaMatching + resumenGenerationStatus='complete'."""
    from backend.main import _handle_async_resumen_generation

    event = {"mode": "async_resumen_generation", "userId": mock_user_id}

    with patch("backend.shared.db.get_dynamodb_table") as mock_get_table, \
            patch("backend.shared.bedrock.get_bedrock_client") as mock_bedrock_fn:
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {
                "userId": mock_user_id,
                "perfilEstructurado": sample_perfil_estructurado,
            }
        }
        mock_get_table.return_value = mock_table

        mock_client = Mock()
        mock_client.model_small = "anthropic.claude-3-haiku-20250514"
        mock_client.invoke_with_retry.return_value = ResumenParaMatchingOutput(
            resumen="Experienced Python and AWS developer."
        )
        mock_bedrock_fn.return_value = mock_client

        result = _handle_async_resumen_generation(event, None)

        assert result == {"statusCode": 200, "body": {"status": "complete"}}

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["Key"] == {"userId": mock_user_id}
        assert "resumenParaMatching" in call_kwargs["UpdateExpression"]
        assert "resumenGenerationStatus" in call_kwargs["UpdateExpression"]
        assert (
            call_kwargs["ExpressionAttributeValues"][":resumen"]
            == "Experienced Python and AWS developer."
        )
        assert call_kwargs["ExpressionAttributeValues"][":status"] == "complete"


def test_async_resumen_generation_bedrock_invocation_failure(
    mock_user_id, sample_perfil_estructurado
):
    """Bedrock invocation fails (e.g. timeout) -> resumenGenerationStatus='failed',
    without modifying any previous resumenParaMatching."""
    from backend.main import _handle_async_resumen_generation

    event = {"mode": "async_resumen_generation", "userId": mock_user_id}

    with patch("backend.shared.db.get_dynamodb_table") as mock_get_table, \
            patch("backend.shared.bedrock.get_bedrock_client") as mock_bedrock_fn:
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {
                "userId": mock_user_id,
                "perfilEstructurado": sample_perfil_estructurado,
                "resumenParaMatching": "previous summary that must not change",
            }
        }
        mock_get_table.return_value = mock_table

        mock_client = Mock()
        mock_client.model_small = "anthropic.claude-3-haiku-20250514"
        mock_client.invoke_with_retry.side_effect = TimeoutError("Bedrock timeout")
        mock_bedrock_fn.return_value = mock_client

        result = _handle_async_resumen_generation(event, None)

        assert result == {"statusCode": 200, "body": {"status": "failed"}}

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["Key"] == {"userId": mock_user_id}
        # Only resumenGenerationStatus is touched, never resumenParaMatching
        assert "resumenGenerationStatus" in call_kwargs["UpdateExpression"]
        assert "resumenParaMatching" not in call_kwargs["UpdateExpression"]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == "failed"
        assert ":resumen" not in call_kwargs["ExpressionAttributeValues"]


def test_async_resumen_generation_validation_error_after_retry(
    mock_user_id, sample_perfil_estructurado
):
    """Pydantic validation fails after the standard retry -> resumenGenerationStatus='failed',
    without modifying any previous resumenParaMatching."""
    from backend.main import _handle_async_resumen_generation

    event = {"mode": "async_resumen_generation", "userId": mock_user_id}

    with patch("backend.shared.db.get_dynamodb_table") as mock_get_table, \
            patch("backend.shared.bedrock.get_bedrock_client") as mock_bedrock_fn:
        mock_table = Mock()
        mock_table.get_item.return_value = {
            "Item": {
                "userId": mock_user_id,
                "perfilEstructurado": sample_perfil_estructurado,
                "resumenParaMatching": "previous summary that must not change",
            }
        }
        mock_get_table.return_value = mock_table

        mock_client = Mock()
        mock_client.model_small = "anthropic.claude-3-haiku-20250514"
        mock_client.invoke_with_retry.side_effect = ValidationError.from_exception_data(
            "ResumenParaMatchingOutput",
            [{"type": "missing", "loc": ("resumen",)}],
        )
        mock_bedrock_fn.return_value = mock_client

        result = _handle_async_resumen_generation(event, None)

        assert result == {"statusCode": 200, "body": {"status": "failed"}}

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert "resumenGenerationStatus" in call_kwargs["UpdateExpression"]
        assert "resumenParaMatching" not in call_kwargs["UpdateExpression"]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == "failed"


def test_async_resumen_generation_missing_perfil_treated_as_failure(mock_user_id):
    """No perfilEstructurado available -> treated as failure, without ever
    invoking Bedrock, and resumenGenerationStatus='failed' is persisted."""
    from backend.main import _handle_async_resumen_generation

    event = {"mode": "async_resumen_generation", "userId": mock_user_id}

    with patch("backend.shared.db.get_dynamodb_table") as mock_get_table, \
            patch("backend.shared.bedrock.get_bedrock_client") as mock_bedrock_fn:
        mock_table = Mock()
        mock_table.get_item.return_value = {"Item": {"userId": mock_user_id}}
        mock_get_table.return_value = mock_table

        result = _handle_async_resumen_generation(event, None)

        assert result == {"statusCode": 200, "body": {"status": "failed"}}
        mock_bedrock_fn.assert_not_called()

        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == "failed"


# ============================================================================
# handler() dispatch Tests
# ============================================================================


def test_handler_dispatches_async_resumen_generation_mode(mock_user_id):
    """handler() routes event with mode == 'async_resumen_generation' to
    _handle_async_resumen_generation, without invoking Mangum/FastAPI."""
    from backend.main import handler

    event = {"mode": "async_resumen_generation", "userId": mock_user_id}
    context = Mock()

    with patch("backend.main._handle_async_resumen_generation") as mock_handle:
        mock_handle.return_value = {"statusCode": 200, "body": {"status": "complete"}}

        result = handler(event, context)

        mock_handle.assert_called_once_with(event, context)
        assert result == {"statusCode": 200, "body": {"status": "complete"}}


def test_handler_does_not_dispatch_other_events_to_resumen_handler():
    """handler() does not route ordinary API Gateway events (no 'mode' key) to
    _handle_async_resumen_generation."""
    from backend.main import handler

    event = {"httpMethod": "GET", "path": "/health"}
    context = Mock()

    with patch("backend.main._handle_async_resumen_generation") as mock_handle, \
            patch("backend.main._mangum_handler") as mock_mangum:
        mock_mangum.return_value = {"statusCode": 200}

        result = handler(event, context)

        mock_handle.assert_not_called()
        mock_mangum.assert_called_once_with(event, context)
        assert result == {"statusCode": 200}
