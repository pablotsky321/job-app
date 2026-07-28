"""
Tests for GET /scans/{jobId} endpoint.

Validates:
- Authorization: returns 404 for non-existent jobs and unauthorized users
- Zombie detection: RUNNING → PARCIAL after 600s
- Auto-DONE: RUNNING → DONE when completadas >= total
- Response fields: status, counts, startedAt, canStop, pendingCompanies
- canStop logic: true for DONE/PARCIAL/FAILED, false for RUNNING

Requirements: 14.1, 14.2, 14.3, 15.1-15.8
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import the module to ensure it's loaded before patching
import backend.api.routes.orquestador  # noqa: F401


def _make_scan_job(
    scan_job_id="job-123",
    user_id="user-123",
    status="RUNNING",
    empresas_total=5,
    empresas_completadas=None,
    empresas_omitidas=None,
    empresas_fallidas=None,
    started_at=None,
):
    """Build a mock ScanJob DynamoDB item."""
    if started_at is None:
        started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    elif isinstance(started_at, datetime):
        started_at = started_at.isoformat().replace("+00:00", "Z")

    item = {
        "scanJobId": scan_job_id,
        "status": status,
        "empresasTotal": empresas_total,
        "empresasCompletadas": empresas_completadas or [],
        "empresasOmitidas": empresas_omitidas or [],
        "empresasFallidas": empresas_fallidas or [],
        "startedAt": started_at,
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if user_id is not None:
        item["userId"] = user_id
    return item


def _create_test_client():
    """Create a test client with mocked auth."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from backend.api.routes.orquestador import scans_router
    from backend.api.routes.auth import get_current_user_id

    app = FastAPI()
    app.include_router(scans_router)
    app.dependency_overrides[get_current_user_id] = lambda: "user-123"

    return TestClient(app)


class TestGetScanJobNotFound:
    """Test 404 responses for missing and unauthorized jobs."""

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_returns_404_when_job_not_found(self, mock_dynamo):
        """Requirement 15.2: 404 if jobId does not exist."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No "Item" key
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/nonexistent-job")
        assert response.status_code == 404

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_returns_404_when_user_mismatch(self, mock_dynamo):
        """Requirement 15.3: 404 if userId set and differs from requesting user."""
        scan_job = _make_scan_job(user_id="other-user-xyz")
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        assert response.status_code == 404

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_allows_access_when_no_userid_set(self, mock_dynamo):
        """Requirement 15.4: If userId not set → any authenticated user can view."""
        scan_job = _make_scan_job(user_id=None, status="DONE")
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        assert response.status_code == 200


class TestGetScanJobZombieDetection:
    """Test zombie detection: RUNNING → PARCIAL after 600s."""

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_zombie_detection_triggers_at_601_seconds(self, mock_dynamo):
        """Requirement 14.1: RUNNING + elapsed > 600s → PARCIAL."""
        started_at = datetime.now(timezone.utc) - timedelta(seconds=601)
        scan_job = _make_scan_job(
            status="RUNNING",
            started_at=started_at,
            empresas_total=3,
            empresas_completadas=["c1"],
            empresas_fallidas=["c3"],
        )
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "PARCIAL"
        assert data["canStop"] is True
        # Verify update_item was called to persist PARCIAL
        mock_table.update_item.assert_called()

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_no_zombie_detection_at_599_seconds(self, mock_dynamo):
        """RUNNING + elapsed < 600s → remains RUNNING."""
        started_at = datetime.now(timezone.utc) - timedelta(seconds=599)
        scan_job = _make_scan_job(
            status="RUNNING",
            started_at=started_at,
            empresas_total=5,
            empresas_completadas=["c1", "c2"],
        )
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "RUNNING"
        assert data["canStop"] is False


class TestGetScanJobAutoDone:
    """Test auto-DONE: RUNNING + completadas >= total → DONE."""

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_auto_done_when_all_completed(self, mock_dynamo):
        """RUNNING + completadas == total → DONE."""
        started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        scan_job = _make_scan_job(
            status="RUNNING",
            started_at=started_at,
            empresas_total=3,
            empresas_completadas=["c1", "c2", "c3"],
        )
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "DONE"
        assert data["canStop"] is True
        # Verify update_item was called to persist DONE
        mock_table.update_item.assert_called()

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_no_auto_done_when_incomplete(self, mock_dynamo):
        """RUNNING + completadas < total → stays RUNNING."""
        started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        scan_job = _make_scan_job(
            status="RUNNING",
            started_at=started_at,
            empresas_total=5,
            empresas_completadas=["c1", "c2"],
        )
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "RUNNING"
        assert data["canStop"] is False


class TestGetScanJobResponseFields:
    """Test response structure and field values."""

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_response_fields_complete(self, mock_dynamo):
        """Requirement 15.5: Response includes all required fields."""
        started_at = "2024-01-15T10:30:00Z"
        scan_job = _make_scan_job(
            status="DONE",
            started_at=started_at,
            empresas_total=10,
            empresas_completadas=["c1", "c2", "c3", "c4", "c5"],
            empresas_omitidas=["c6", "c7"],
            empresas_fallidas=["c8"],
        )
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "DONE"
        assert data["empresasTotal"] == 10
        assert data["completados"] == 5
        assert data["omitidos"] == 2
        assert data["fallidos"] == 1
        assert data["startedAt"] == "2024-01-15T10:30:00Z"
        assert data["canStop"] is True
        assert data.get("pendingCompanies") is None

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_canstop_false_when_running(self, mock_dynamo):
        """Requirement 15.8: canStop=false when RUNNING."""
        started_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        scan_job = _make_scan_job(
            status="RUNNING",
            started_at=started_at,
            empresas_total=5,
            empresas_completadas=["c1"],
        )
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        data = response.json()
        assert data["canStop"] is False

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_canstop_true_for_failed(self, mock_dynamo):
        """Requirement 15.7: canStop=true when FAILED."""
        scan_job = _make_scan_job(status="FAILED")
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        data = response.json()
        assert data["status"] == "FAILED"
        assert data["canStop"] is True

    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    def test_parcial_includes_pending_companies(self, mock_dynamo):
        """Requirement 15.6: PARCIAL response includes pendingCompanies."""
        scan_job = _make_scan_job(
            status="PARCIAL",
            empresas_total=5,
            empresas_completadas=["c1", "c2"],
            empresas_omitidas=["c3"],
            empresas_fallidas=["c4"],
        )
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": scan_job}
        mock_dynamo.return_value.Table.return_value = mock_table

        client = _create_test_client()
        response = client.get("/scans/job-123")
        data = response.json()
        assert data["status"] == "PARCIAL"
        assert data["canStop"] is True
        assert "pendingCompanies" in data
        # c4 is in fallidas but not in completadas → pending
        assert "c4" in data["pendingCompanies"]
