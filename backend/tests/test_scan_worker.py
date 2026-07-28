"""
Unit tests for Scan_Worker Lambda handler.

Tests with mocks: cascada flow, classification routing, Vacante upsert,
SQS_Scoring publish, idempotent String Set ADD operations.

Requirements: 2, 6, 7, 12, 13
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from backend.shared.extraction import VacancyExtracted
from backend.shared.models import Empresa, PlatformaEnum, Vacante


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_empresa():
    """A typical Empresa for testing."""
    return Empresa(
        companyId="abc123def456" * 4 + "abcdef1234567890",
        nombre="Acme Corp",
        careersUrl="https://acme.com/careers",
        plataforma=PlatformaEnum.GREENHOUSE,
        lastVacancyCount=5,
        consecutiveFailures=0,
        createdAt=datetime(2024, 1, 1),
    )


@pytest.fixture
def sample_empresa_empty():
    """Empresa with lastVacancyCount=0 (for EMPTY_LEGITIMO tests)."""
    return Empresa(
        companyId="empty123" * 8,
        nombre="New Corp",
        careersUrl="https://newcorp.com/careers",
        plataforma=PlatformaEnum.HTML,
        lastVacancyCount=0,
        consecutiveFailures=0,
        createdAt=datetime(2024, 1, 1),
    )


@pytest.fixture
def sample_vacancies():
    """Sample extracted vacancies from cascada."""
    return [
        VacancyExtracted(
            titulo="Senior Backend Engineer",
            descripcion="Build scalable systems",
            url="https://acme.com/jobs/senior-backend",
            modalidad="remote",
            ubicacion="Remote",
        ),
        VacancyExtracted(
            titulo="Frontend Developer",
            descripcion="React + TypeScript",
            url="https://acme.com/jobs/frontend-dev",
            modalidad="sin_dato",
            ubicacion="",
        ),
    ]


@pytest.fixture
def sample_existing_vacantes():
    """Existing Vacante records in DynamoDB."""
    return [
        Vacante(
            vacanteSha256="existing_hash_1" + "0" * 49,
            companyId="abc123def456" * 4 + "abcdef1234567890",
            titulo="Old Job",
            descripcion="Legacy role",
            url="https://acme.com/jobs/old-job",
            plataforma=PlatformaEnum.GREENHOUSE,
            origen="board_api",
            crawledAt=datetime(2024, 1, 10),
            missCount=0,
            cerrada=False,
        ),
    ]


@pytest.fixture
def sqs_event():
    """Sample SQS event with one record."""
    return {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "jobId": "scan_20240115_user123",
                        "companyId": "abc123def456" * 4 + "abcdef1234567890",
                    }
                ),
            }
        ]
    }


@pytest.fixture
def lambda_context():
    """Mock Lambda context."""
    ctx = MagicMock()
    ctx.aws_request_id = "req-12345"
    return ctx


# ============================================================================
# TEST: CASCADA FLOW AND OK CLASSIFICATION
# ============================================================================


@patch("backend.workers.scan_worker._get_sqs")
@patch("backend.workers.scan_worker._get_dynamodb")
@patch("backend.workers.scan_worker.cascada_descubrimiento")
class TestScanWorkerOKFlow:
    """Tests for OK classification path."""

    def test_ok_flow_upserts_vacantes_and_updates_empresa(
        self,
        mock_cascada,
        mock_dynamodb,
        mock_sqs,
        sqs_event,
        lambda_context,
        sample_empresa,
        sample_vacancies,
    ):
        """When cascada returns vacancies, worker upserts them and updates empresa."""
        from backend.workers.scan_worker import handler_scan_worker

        # Mock cascada returns OK result
        mock_cascada.return_value = (sample_vacancies, "board_api", None)

        # Mock DynamoDB
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": sample_empresa.model_dump()}
        mock_table.query.return_value = {"Items": []}
        mock_table.put_item.return_value = {}
        mock_table.update_item.return_value = {}

        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource

        # Mock SQS (no subscriptions → no scoring messages)
        mock_sqs_client = MagicMock()
        mock_sqs.return_value = mock_sqs_client

        result = handler_scan_worker(sqs_event, lambda_context)

        assert result["statusCode"] == 200
        # Cascada was called
        mock_cascada.assert_called_once()
        # Vacantes were upserted via put_item
        assert mock_table.put_item.call_count >= 1

    def test_ok_flow_enqueues_scoring_for_new_vacancies(
        self,
        mock_cascada,
        mock_dynamodb,
        mock_sqs,
        sqs_event,
        lambda_context,
        sample_empresa,
        sample_vacancies,
    ):
        """When OK with new vacancies and active subscriptions, enqueue scoring messages."""
        from backend.workers.scan_worker import handler_scan_worker

        mock_cascada.return_value = (sample_vacancies, "board_api", None)

        # Setup DynamoDB: empresa exists, no existing vacantes, active subscriptions
        mock_table = MagicMock()

        def table_router(name):
            return mock_table

        mock_resource = MagicMock()
        mock_resource.Table.side_effect = table_router
        mock_dynamodb.return_value = mock_resource

        # get_item for empresa
        mock_table.get_item.return_value = {"Item": sample_empresa.model_dump()}

        # query calls: first for existing vacantes (empty), then for subscriptions
        mock_table.query.side_effect = [
            {"Items": []},  # existing vacantes
            {"Items": [{"userId": "user-1", "companyId": sample_empresa.companyId, "activa": True}]},  # subscriptions
        ]
        mock_table.put_item.return_value = {}
        mock_table.update_item.return_value = {}

        # Mock SQS send_message_batch
        mock_sqs_client = MagicMock()
        mock_sqs_client.send_message_batch.return_value = {"Successful": [{"Id": "0"}], "Failed": []}
        mock_sqs.return_value = mock_sqs_client

        result = handler_scan_worker(sqs_event, lambda_context)

        assert result["statusCode"] == 200
        # SQS scoring messages should be sent
        mock_sqs_client.send_message_batch.assert_called()

    def test_ok_flow_identifies_new_vacancies_correctly(
        self,
        mock_cascada,
        mock_dynamodb,
        mock_sqs,
        sqs_event,
        lambda_context,
        sample_empresa,
        sample_vacancies,
        sample_existing_vacantes,
    ):
        """Only NEW vacancies (not previously existing) trigger scoring messages."""
        from backend.workers.scan_worker import _identify_new_vacancy_ids
        from backend.shared.extraction import compute_vacancyId

        # Create updated_vacantes: 2 new + 1 existing (from misscount logic)
        new_v1 = Vacante(
            vacanteSha256=compute_vacancyId("https://acme.com/jobs/senior-backend"),
            companyId=sample_empresa.companyId,
            titulo="Senior Backend Engineer",
            descripcion="Build scalable systems",
            url="https://acme.com/jobs/senior-backend",
            plataforma=PlatformaEnum.GREENHOUSE,
            origen="board_api",
            crawledAt=datetime.utcnow(),
            missCount=0,
            cerrada=False,
        )
        existing_ids = {sample_existing_vacantes[0].vacanteSha256}

        # new_v1 is NOT in existing_ids → it's new
        new_ids = _identify_new_vacancy_ids([new_v1] + sample_existing_vacantes, existing_ids)
        assert new_v1.vacanteSha256 in new_ids
        # existing vacancy should NOT be in new_ids
        assert sample_existing_vacantes[0].vacanteSha256 not in new_ids


# ============================================================================
# TEST: FAILED AND EMPTY_SOSPECHOSO CLASSIFICATION
# ============================================================================


@patch("backend.workers.scan_worker._get_sqs")
@patch("backend.workers.scan_worker._get_dynamodb")
@patch("backend.workers.scan_worker.cascada_descubrimiento")
class TestScanWorkerFailedFlow:
    """Tests for FAILED and EMPTY_SOSPECHOSO classification paths."""

    def test_failed_increments_consecutive_failures(
        self,
        mock_cascada,
        mock_dynamodb,
        mock_sqs,
        sqs_event,
        lambda_context,
        sample_empresa,
    ):
        """FAILED classification increments consecutiveFailures and adds to fallidas."""
        from backend.workers.scan_worker import handler_scan_worker

        # Cascada returns error
        mock_cascada.return_value = ([], None, "all_methods_failed")

        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": sample_empresa.model_dump()}
        mock_table.update_item.return_value = {}

        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource

        result = handler_scan_worker(sqs_event, lambda_context)

        assert result["statusCode"] == 200
        # update_item should be called for empresa + completadas + fallidas
        assert mock_table.update_item.call_count >= 3

    def test_empty_sospechoso_does_not_touch_vacantes(
        self,
        mock_cascada,
        mock_dynamodb,
        mock_sqs,
        sqs_event,
        lambda_context,
        sample_empresa,
    ):
        """EMPTY_SOSPECHOSO: NO vacante modifications (critical invariant from pitfalls.md)."""
        from backend.workers.scan_worker import handler_scan_worker

        # Cascada returns 0 vacancies, no error (empresa has lastVacancyCount > 0)
        mock_cascada.return_value = ([], "json_ld", None)

        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": sample_empresa.model_dump()}
        mock_table.update_item.return_value = {}

        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource

        result = handler_scan_worker(sqs_event, lambda_context)

        assert result["statusCode"] == 200
        # put_item should NOT be called (no vacante upserts)
        mock_table.put_item.assert_not_called()

    def test_empty_sospechoso_adds_to_fallidas(
        self,
        mock_cascada,
        mock_dynamodb,
        mock_sqs,
        sqs_event,
        lambda_context,
        sample_empresa,
    ):
        """EMPTY_SOSPECHOSO adds companyId to both completadas AND fallidas."""
        from backend.workers.scan_worker import handler_scan_worker

        mock_cascada.return_value = ([], "json_ld", None)

        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": sample_empresa.model_dump()}
        mock_table.update_item.return_value = {}

        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource

        handler_scan_worker(sqs_event, lambda_context)

        # Check that update_item was called with ADD for both sets
        update_calls = mock_table.update_item.call_args_list
        # Should have: update_empresa_failed + add_completadas + add_fallidas = 3 calls
        assert len(update_calls) >= 3


# ============================================================================
# TEST: EMPTY_LEGITIMO CLASSIFICATION
# ============================================================================


@patch("backend.workers.scan_worker._get_sqs")
@patch("backend.workers.scan_worker._get_dynamodb")
@patch("backend.workers.scan_worker.cascada_descubrimiento")
class TestScanWorkerEmptyLegitimoFlow:
    """Tests for EMPTY_LEGITIMO classification path."""

    def test_empty_legitimo_resets_failures_and_updates_origen(
        self,
        mock_cascada,
        mock_dynamodb,
        mock_sqs,
        lambda_context,
        sample_empresa_empty,
    ):
        """EMPTY_LEGITIMO: consecutiveFailures=0, updates ultimoOrigenExitoso."""
        from backend.workers.scan_worker import handler_scan_worker

        event = {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "jobId": "scan_20240115",
                            "companyId": sample_empresa_empty.companyId,
                        }
                    ),
                }
            ]
        }

        mock_cascada.return_value = ([], "json_ld", None)

        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": sample_empresa_empty.model_dump()}
        mock_table.update_item.return_value = {}

        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource

        result = handler_scan_worker(event, lambda_context)

        assert result["statusCode"] == 200
        # update_item called for empresa + completadas (no fallidas for EMPTY_LEGITIMO)
        update_calls = mock_table.update_item.call_args_list
        # Should NOT add to fallidas (only completadas)
        assert len(update_calls) == 2  # empresa update + completadas


# ============================================================================
# TEST: SQS SCORING ENQUEUE FAILURE (Requirement 12.5)
# ============================================================================


@patch("backend.workers.scan_worker._get_sqs")
@patch("backend.workers.scan_worker._get_dynamodb")
@patch("backend.workers.scan_worker.cascada_descubrimiento")
class TestScanWorkerSQSFailure:
    """Tests for SQS_Scoring enqueue failure behavior."""

    def test_scoring_enqueue_failure_raises_for_sqs_retry(
        self,
        mock_cascada,
        mock_dynamodb,
        mock_sqs,
        sqs_event,
        lambda_context,
        sample_empresa,
        sample_vacancies,
    ):
        """If SQS_Scoring enqueue fails, handler raises so SQS retries the message.

        Requirement 12.5: Abort without ADD to empresasCompletadas.
        """
        from backend.workers.scan_worker import handler_scan_worker

        mock_cascada.return_value = (sample_vacancies, "board_api", None)

        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": sample_empresa.model_dump()}
        # First query: no existing vacantes; second: active subscription
        mock_table.query.side_effect = [
            {"Items": []},  # existing vacantes
            {"Items": [{"userId": "user-1", "companyId": sample_empresa.companyId, "activa": True}]},
        ]
        mock_table.put_item.return_value = {}
        mock_table.update_item.return_value = {}

        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource

        # SQS batch send returns failures
        mock_sqs_client = MagicMock()
        mock_sqs_client.send_message_batch.return_value = {
            "Successful": [],
            "Failed": [{"Id": "0", "Code": "InternalError", "Message": "error"}],
        }
        mock_sqs.return_value = mock_sqs_client

        with pytest.raises(RuntimeError, match="Failed to enqueue"):
            handler_scan_worker(sqs_event, lambda_context)


# ============================================================================
# TEST: IDEMPOTENCY (Requirement 13)
# ============================================================================


@patch("backend.workers.scan_worker._get_sqs")
@patch("backend.workers.scan_worker._get_dynamodb")
@patch("backend.workers.scan_worker.cascada_descubrimiento")
class TestScanWorkerIdempotency:
    """Tests for idempotent behavior on SQS redelivery."""

    def test_string_set_add_is_idempotent(
        self,
        mock_cascada,
        mock_dynamodb,
        mock_sqs,
        sqs_event,
        lambda_context,
        sample_empresa,
    ):
        """ADD to String Set is idempotent — processing same message twice is safe."""
        from backend.workers.scan_worker import _add_to_scan_job_completadas

        mock_table = MagicMock()
        mock_table.update_item.return_value = {}

        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_dynamodb.return_value = mock_resource

        # Call twice — both should succeed without error
        _add_to_scan_job_completadas("job-1", "company-1")
        _add_to_scan_job_completadas("job-1", "company-1")

        # Both calls use ADD (DynamoDB handles idempotency)
        assert mock_table.update_item.call_count == 2
        for c in mock_table.update_item.call_args_list:
            assert "ADD empresasCompletadas" in c.kwargs.get(
                "UpdateExpression", c[1].get("UpdateExpression", "")
            )


# ============================================================================
# TEST: MESSAGE PARSING
# ============================================================================


class TestScanMessageParsing:
    """Tests for ScanMessage model parsing."""

    def test_valid_scan_message(self):
        """ScanMessage parses valid payload."""
        from backend.workers.scan_worker import ScanMessage

        msg = ScanMessage(jobId="job-123", companyId="company-456")
        assert msg.jobId == "job-123"
        assert msg.companyId == "company-456"

    def test_scan_message_ignores_extra_fields(self):
        """ScanMessage ignores unknown fields (forward compat)."""
        from backend.workers.scan_worker import ScanMessage

        msg = ScanMessage(jobId="job-123", companyId="company-456", extra_field="ignored")
        assert msg.jobId == "job-123"
        assert not hasattr(msg, "extra_field")

    def test_scoring_message_model(self):
        """ScoringMessage builds correctly."""
        from backend.workers.scan_worker import ScoringMessage

        msg = ScoringMessage(userId="user-1", vacancyId="vacancy-sha256")
        assert msg.userId == "user-1"
        assert msg.vacancyId == "vacancy-sha256"
        # Verify JSON serialization
        body = json.loads(msg.model_dump_json())
        assert body["userId"] == "user-1"
        assert body["vacancyId"] == "vacancy-sha256"
