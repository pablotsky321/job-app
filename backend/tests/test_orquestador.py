"""
Tests for the Orquestador endpoint (POST /scans).

Covers:
- JWT extraction (userId from dependency)
- Suscripción query resolution and deduplication
- Ventana_Frescura logic (1h for board_api/json_ld, 12h for html_llm)
- ScanJob creation with correct status transitions
- SQS publish failures: ALL fail → FAILED, SOME fail → PARCIAL
- Zero companies and all-omitted edge cases

Requirements: 8, 9, 10, 11
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest

from backend.api.routes.orquestador import es_elegible_para_rescan


# ============================================================================
# Unit Tests: es_elegible_para_rescan (pure function)
# ============================================================================


class TestEsElegibleParaRescan:
    """Tests for Ventana_Frescura logic (Requirement 8)."""

    def test_no_last_scanned_always_eligible(self):
        """Requirement 8.3: No lastScannedAt → always eligible."""
        empresa = {"companyId": "abc", "lastScannedAt": None}
        now = datetime.now(timezone.utc)
        assert es_elegible_para_rescan(empresa, now) is True

    def test_no_last_scanned_missing_key_eligible(self):
        """Requirement 8.3: lastScannedAt key missing → always eligible."""
        empresa = {"companyId": "abc"}
        now = datetime.now(timezone.utc)
        assert es_elegible_para_rescan(empresa, now) is True

    def test_board_api_under_1h_not_eligible(self):
        """Requirement 8.1: board_api with elapsed < 3600s → not eligible."""
        now = datetime.now(timezone.utc)
        empresa = {
            "companyId": "abc",
            "lastScannedAt": (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            "ultimoOrigenExitoso": "board_api",
        }
        assert es_elegible_para_rescan(empresa, now) is False

    def test_board_api_over_1h_eligible(self):
        """Requirement 8.1: board_api with elapsed >= 3600s → eligible."""
        now = datetime.now(timezone.utc)
        empresa = {
            "companyId": "abc",
            "lastScannedAt": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "ultimoOrigenExitoso": "board_api",
        }
        assert es_elegible_para_rescan(empresa, now) is True

    def test_json_ld_under_1h_not_eligible(self):
        """Requirement 8.1: json_ld with elapsed < 3600s → not eligible."""
        now = datetime.now(timezone.utc)
        empresa = {
            "companyId": "abc",
            "lastScannedAt": (now - timedelta(minutes=50)).isoformat().replace("+00:00", "Z"),
            "ultimoOrigenExitoso": "json_ld",
        }
        assert es_elegible_para_rescan(empresa, now) is False

    def test_json_ld_over_1h_eligible(self):
        """Requirement 8.1: json_ld with elapsed >= 3600s → eligible."""
        now = datetime.now(timezone.utc)
        empresa = {
            "companyId": "abc",
            "lastScannedAt": (now - timedelta(hours=1, minutes=1)).isoformat().replace("+00:00", "Z"),
            "ultimoOrigenExitoso": "json_ld",
        }
        assert es_elegible_para_rescan(empresa, now) is True

    def test_html_llm_under_12h_not_eligible(self):
        """Requirement 8.2: html_llm with elapsed < 43200s → not eligible."""
        now = datetime.now(timezone.utc)
        empresa = {
            "companyId": "abc",
            "lastScannedAt": (now - timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
            "ultimoOrigenExitoso": "html_llm",
        }
        assert es_elegible_para_rescan(empresa, now) is False

    def test_html_llm_over_12h_eligible(self):
        """Requirement 8.2: html_llm with elapsed >= 43200s → eligible."""
        now = datetime.now(timezone.utc)
        empresa = {
            "companyId": "abc",
            "lastScannedAt": (now - timedelta(hours=13)).isoformat().replace("+00:00", "Z"),
            "ultimoOrigenExitoso": "html_llm",
        }
        assert es_elegible_para_rescan(empresa, now) is True

    def test_no_ultimo_origen_uses_12h_window(self):
        """Requirement 8.4: No ultimoOrigenExitoso → 43200s window."""
        now = datetime.now(timezone.utc)
        empresa = {
            "companyId": "abc",
            "lastScannedAt": (now - timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
            "ultimoOrigenExitoso": None,
        }
        assert es_elegible_para_rescan(empresa, now) is False

    def test_no_ultimo_origen_over_12h_eligible(self):
        """Requirement 8.4: No ultimoOrigenExitoso, elapsed >= 43200s → eligible."""
        now = datetime.now(timezone.utc)
        empresa = {
            "companyId": "abc",
            "lastScannedAt": (now - timedelta(hours=13)).isoformat().replace("+00:00", "Z"),
            "ultimoOrigenExitoso": None,
        }
        assert es_elegible_para_rescan(empresa, now) is True

    def test_exact_boundary_board_api(self):
        """Requirement 8.1: Exactly 3600s → eligible."""
        now = datetime.now(timezone.utc)
        empresa = {
            "companyId": "abc",
            "lastScannedAt": (now - timedelta(seconds=3600)).isoformat().replace("+00:00", "Z"),
            "ultimoOrigenExitoso": "board_api",
        }
        assert es_elegible_para_rescan(empresa, now) is True


# ============================================================================
# Integration Tests: POST /scans endpoint (with mocks)
# ============================================================================


class TestPostScansEndpoint:
    """Integration tests for POST /scans with mocked AWS dependencies."""

    @patch("backend.api.routes.orquestador.boto3.client")
    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    @patch("backend.api.routes.orquestador.query_by_pk")
    @patch("backend.api.routes.orquestador.put_item")
    def test_zero_subscriptions_returns_done(
        self, mock_put, mock_query, mock_dynamo, mock_sqs
    ):
        """Requirement 10.1: Zero companies → DONE immediately."""
        # No active subscriptions
        mock_query.return_value = []

        from fastapi.testclient import TestClient
        from backend.api.routes.orquestador import scans_router, PostScansResponse
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(scans_router)

        # Override auth dependency
        from backend.api.routes.auth import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "user-123"

        client = TestClient(app)
        response = client.post("/scans")

        assert response.status_code == 200
        data = response.json()
        assert "jobId" in data

        # Verify ScanJob was persisted with DONE status
        mock_put.assert_called_once()
        job_item = mock_put.call_args[0][1]
        assert job_item["status"] == "DONE"
        assert job_item["empresasTotal"] == 0
        assert job_item["userId"] == "user-123"

    @patch("backend.api.routes.orquestador.boto3.client")
    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    @patch("backend.api.routes.orquestador.query_by_pk")
    @patch("backend.api.routes.orquestador.put_item")
    def test_all_omitted_by_ventana_frescura_returns_done(
        self, mock_put, mock_query, mock_dynamo, mock_sqs
    ):
        """Requirement 10.2: All omitted by Ventana_Frescura → DONE."""
        now = datetime.now(timezone.utc)
        recent_scan_time = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")

        # Active subscription
        mock_query.return_value = [
            {"userId": "user-123", "companyId": "company-1", "activa": True}
        ]

        # Mock empresa: recently scanned with board_api → not eligible
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "companyId": "company-1",
                "lastScannedAt": recent_scan_time,
                "ultimoOrigenExitoso": "board_api",
            }
        }
        mock_dynamo.return_value.Table.return_value = mock_table

        from fastapi.testclient import TestClient
        from backend.api.routes.orquestador import scans_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(scans_router)

        from backend.api.routes.auth import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "user-123"

        client = TestClient(app)
        response = client.post("/scans")

        assert response.status_code == 200
        data = response.json()
        assert "jobId" in data

        # Verify ScanJob was persisted with DONE and empresasOmitidas
        mock_put.assert_called_once()
        job_item = mock_put.call_args[0][1]
        assert job_item["status"] == "DONE"
        assert "company-1" in job_item["empresasOmitidas"]

    @patch("backend.api.routes.orquestador.boto3.client")
    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    @patch("backend.api.routes.orquestador.query_by_pk")
    @patch("backend.api.routes.orquestador.put_item")
    def test_eligible_company_publishes_to_sqs(
        self, mock_put, mock_query, mock_dynamo, mock_sqs
    ):
        """Requirement 9.8: Publish one ScanMessage per eligible company."""
        # Active subscription
        mock_query.return_value = [
            {"userId": "user-123", "companyId": "company-1", "activa": True}
        ]

        # Mock empresa: never scanned → eligible
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "companyId": "company-1",
                "lastScannedAt": None,
                "ultimoOrigenExitoso": None,
            }
        }
        mock_table.update_item.return_value = {}
        mock_dynamo.return_value.Table.return_value = mock_table

        # Mock SQS client
        mock_sqs_client = MagicMock()
        mock_sqs.return_value = mock_sqs_client

        from fastapi.testclient import TestClient
        from backend.api.routes.orquestador import scans_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(scans_router)

        from backend.api.routes.auth import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "user-123"

        client = TestClient(app)
        response = client.post("/scans")

        assert response.status_code == 200

        # Verify SQS send_message was called once
        mock_sqs_client.send_message.assert_called_once()
        call_kwargs = mock_sqs_client.send_message.call_args[1]
        assert "company-1" in call_kwargs["MessageBody"]

    @patch("backend.api.routes.orquestador.boto3.client")
    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    @patch("backend.api.routes.orquestador.query_by_pk")
    @patch("backend.api.routes.orquestador.put_item")
    def test_all_sqs_publish_fail_status_failed(
        self, mock_put, mock_query, mock_dynamo, mock_sqs
    ):
        """Requirement 11.2: ALL SQS publishes fail → status=FAILED."""
        # Active subscriptions to 2 companies
        mock_query.return_value = [
            {"userId": "user-123", "companyId": "company-1", "activa": True},
            {"userId": "user-123", "companyId": "company-2", "activa": True},
        ]

        # Both empresas are eligible (never scanned)
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "companyId": "any",
                "lastScannedAt": None,
                "ultimoOrigenExitoso": None,
            }
        }
        mock_table.update_item.return_value = {}
        mock_dynamo.return_value.Table.return_value = mock_table

        # SQS always fails
        mock_sqs_client = MagicMock()
        mock_sqs_client.send_message.side_effect = Exception("SQS unavailable")
        mock_sqs.return_value = mock_sqs_client

        from fastapi.testclient import TestClient
        from backend.api.routes.orquestador import scans_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(scans_router)

        from backend.api.routes.auth import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "user-123"

        client = TestClient(app)
        response = client.post("/scans")

        assert response.status_code == 200
        data = response.json()
        assert "jobId" in data

        # ScanJob should be updated to FAILED via update_item
        mock_table.update_item.assert_called_once()
        update_call = mock_table.update_item.call_args[1]
        assert update_call["ExpressionAttributeValues"][":status"] == "FAILED"

    @patch("backend.api.routes.orquestador.boto3.client")
    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    @patch("backend.api.routes.orquestador.query_by_pk")
    @patch("backend.api.routes.orquestador.put_item")
    def test_partial_sqs_publish_fail_status_parcial(
        self, mock_put, mock_query, mock_dynamo, mock_sqs
    ):
        """Requirement 11.3: SOME SQS publishes fail → status=PARCIAL."""
        # Active subscriptions to 2 companies
        mock_query.return_value = [
            {"userId": "user-123", "companyId": "company-1", "activa": True},
            {"userId": "user-123", "companyId": "company-2", "activa": True},
        ]

        # Both empresas are eligible (never scanned)
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "companyId": "any",
                "lastScannedAt": None,
                "ultimoOrigenExitoso": None,
            }
        }
        mock_table.update_item.return_value = {}
        mock_dynamo.return_value.Table.return_value = mock_table

        # SQS: first call succeeds, second call fails
        mock_sqs_client = MagicMock()
        mock_sqs_client.send_message.side_effect = [
            {"MessageId": "msg-1"},  # Success
            Exception("SQS timeout"),  # Failure
        ]
        mock_sqs.return_value = mock_sqs_client

        from fastapi.testclient import TestClient
        from backend.api.routes.orquestador import scans_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(scans_router)

        from backend.api.routes.auth import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "user-123"

        client = TestClient(app)
        response = client.post("/scans")

        assert response.status_code == 200

        # ScanJob should be updated to PARCIAL
        mock_table.update_item.assert_called_once()
        update_call = mock_table.update_item.call_args[1]
        assert update_call["ExpressionAttributeValues"][":status"] == "PARCIAL"

    @patch("backend.api.routes.orquestador.boto3.client")
    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    @patch("backend.api.routes.orquestador.query_by_pk")
    @patch("backend.api.routes.orquestador.put_item")
    def test_deduplicates_company_ids(
        self, mock_put, mock_query, mock_dynamo, mock_sqs
    ):
        """Requirement 9.4: Deduplicate companyIds from multiple suscripciones."""
        # Two subscriptions to same company (e.g., from different flows)
        mock_query.return_value = [
            {"userId": "user-123", "companyId": "company-1", "activa": True},
            {"userId": "user-123", "companyId": "company-1", "activa": True},
        ]

        # Empresa never scanned → eligible
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "companyId": "company-1",
                "lastScannedAt": None,
                "ultimoOrigenExitoso": None,
            }
        }
        mock_table.update_item.return_value = {}
        mock_dynamo.return_value.Table.return_value = mock_table

        mock_sqs_client = MagicMock()
        mock_sqs.return_value = mock_sqs_client

        from fastapi.testclient import TestClient
        from backend.api.routes.orquestador import scans_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(scans_router)

        from backend.api.routes.auth import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "user-123"

        client = TestClient(app)
        response = client.post("/scans")

        assert response.status_code == 200

        # Only one SQS message should be sent (deduplicated)
        mock_sqs_client.send_message.assert_called_once()

    @patch("backend.api.routes.orquestador.boto3.client")
    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    @patch("backend.api.routes.orquestador.query_by_pk")
    @patch("backend.api.routes.orquestador.put_item")
    def test_inactive_subscriptions_excluded(
        self, mock_put, mock_query, mock_dynamo, mock_sqs
    ):
        """Requirement 9.2: Only active Suscripciones are resolved."""
        # One active, one inactive
        mock_query.return_value = [
            {"userId": "user-123", "companyId": "company-1", "activa": True},
            {"userId": "user-123", "companyId": "company-2", "activa": False},
        ]

        # Company-1 is eligible
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "companyId": "company-1",
                "lastScannedAt": None,
                "ultimoOrigenExitoso": None,
            }
        }
        mock_table.update_item.return_value = {}
        mock_dynamo.return_value.Table.return_value = mock_table

        mock_sqs_client = MagicMock()
        mock_sqs.return_value = mock_sqs_client

        from fastapi.testclient import TestClient
        from backend.api.routes.orquestador import scans_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(scans_router)

        from backend.api.routes.auth import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "user-123"

        client = TestClient(app)
        response = client.post("/scans")

        assert response.status_code == 200

        # Only company-1 should have SQS message published
        mock_sqs_client.send_message.assert_called_once()
        call_kwargs = mock_sqs_client.send_message.call_args[1]
        assert "company-1" in call_kwargs["MessageBody"]

    @patch("backend.api.routes.orquestador.boto3.client")
    @patch("backend.api.routes.orquestador._get_dynamodb_client")
    @patch("backend.api.routes.orquestador.query_by_pk")
    @patch("backend.api.routes.orquestador.put_item")
    def test_successful_scan_status_running(
        self, mock_put, mock_query, mock_dynamo, mock_sqs
    ):
        """Requirement 9.5: Successful publish → status remains RUNNING."""
        mock_query.return_value = [
            {"userId": "user-123", "companyId": "company-1", "activa": True}
        ]

        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {
                "companyId": "company-1",
                "lastScannedAt": None,
                "ultimoOrigenExitoso": None,
            }
        }
        mock_table.update_item.return_value = {}
        mock_dynamo.return_value.Table.return_value = mock_table

        mock_sqs_client = MagicMock()
        mock_sqs_client.send_message.return_value = {"MessageId": "msg-1"}
        mock_sqs.return_value = mock_sqs_client

        from fastapi.testclient import TestClient
        from backend.api.routes.orquestador import scans_router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(scans_router)

        from backend.api.routes.auth import get_current_user_id

        app.dependency_overrides[get_current_user_id] = lambda: "user-123"

        client = TestClient(app)
        response = client.post("/scans")

        assert response.status_code == 200

        # ScanJob was created with RUNNING status
        mock_put.assert_called_once()
        job_item = mock_put.call_args[0][1]
        assert job_item["status"] == "RUNNING"

        # update_item should NOT be called (no status change needed)
        mock_table.update_item.assert_not_called()
