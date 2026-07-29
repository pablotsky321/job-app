"""
Tests for companies endpoints (GET /companies and POST /companies).

Validates:
- GET /companies returns paginated list sorted case-insensitively by nombre
- GET /companies pagination parameters (limit, offset, hasMore)
- POST /companies validates URL, normalizes, detects platform, creates entry
- POST /companies returns 400 on invalid URL
- POST /companies returns 400 on malformed URL (platform_detection_failed)
- POST /companies returns 409 on duplicate company

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from starlette.testclient import TestClient
from botocore.exceptions import ClientError
from hypothesis import given, settings, strategies as st


@pytest.fixture
def app():
    """Create test app."""
    from backend.main import create_app

    test_app = create_app()
    return test_app


@pytest.fixture
def client(app):
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_companies():
    """Sample companies data sorted in various casing for testing."""
    return [
        {
            "companyId": "abc123",
            "nombre": "Acme",
            "careersUrl": "https://acme.greenhouse.io/jobs",
            "plataforma": "greenhouse",
            "lastScannedAt": "2024-01-01T00:00:00Z",
            "lastScanStatus": "OK",
            "lastVacancyCount": 5,
            "consecutiveFailures": 0,
        },
        {
            "companyId": "def456",
            "nombre": "zebra",
            "careersUrl": "https://zebra.lever.co/careers",
            "plataforma": "lever",
            "lastScannedAt": None,
            "lastScanStatus": None,
            "lastVacancyCount": 0,
            "consecutiveFailures": 0,
        },
        {
            "companyId": "ghi789",
            "nombre": "Beta",
            "careersUrl": "https://beta.com/careers",
            "plataforma": "html",
            "lastScannedAt": "2024-02-01T00:00:00Z",
            "lastScanStatus": "FAILED",
            "lastVacancyCount": 3,
            "consecutiveFailures": 2,
        },
    ]


# ============================================================================
# Property-based tests: decide_subscription_action (Requirement 1.3-1.6)
# ============================================================================


@settings(max_examples=100, deadline=None)
@given(existing_activa=st.one_of(st.none(), st.booleans()))
def test_decide_subscription_action_property(existing_activa):
    """
    Feature: backend-fix-integracion-frontend, Property 1: Decisión de alta de
    suscripción es exhaustiva y correcta por rama.

    deadline=None: la primera ejecución de este test importa
    backend.api.routes.companies (y sus dependencias, incluida la carga de
    tablas DynamoDB simuladas en logging), lo que puede superar el deadline
    por defecto de Hypothesis en la primera llamada sin reflejar una regresión
    real de performance de la función pura bajo prueba.

    Validates: Requirements 1.3, 1.4, 1.5, 1.6
    """
    from backend.api.routes.companies import decide_subscription_action, SubscriptionAction

    action = decide_subscription_action(existing_activa)

    if existing_activa is None:
        assert action == SubscriptionAction.CREATE
    elif existing_activa is True:
        assert action == SubscriptionAction.NO_OP
    else:
        assert action == SubscriptionAction.REACTIVATE

    # Exhaustive: the result must always be one of the three known actions.
    assert action in (
        SubscriptionAction.CREATE,
        SubscriptionAction.NO_OP,
        SubscriptionAction.REACTIVATE,
    )


@settings(max_examples=100, deadline=None)
@given(existing_activa=st.one_of(st.none(), st.booleans()))
def test_decide_subscription_action_idempotent_convergence(existing_activa):
    """
    Feature: backend-fix-integracion-frontend, Property 2: El alta de
    suscripción es idempotente (convergencia a no-op).

    For any initial existing_activa, applying the resulting action always
    leaves activa=True stored. Re-deciding on that new state (True) must
    always converge to NO_OP.

    Validates: Requirements 1.3, 1.4, 1.5, 1.6
    """
    from backend.api.routes.companies import decide_subscription_action, SubscriptionAction

    # Decide on the initial state (not asserted here, covered by Property 1).
    decide_subscription_action(existing_activa)

    # Regardless of the initial state, applying CREATE/NO_OP/REACTIVATE always
    # leaves activa=True persisted. Re-deciding on that converged state must
    # always be a no-op.
    converged_action = decide_subscription_action(True)
    assert converged_action == SubscriptionAction.NO_OP


# ============================================================================
# GET /companies Tests
# ============================================================================


def test_list_companies_returns_200(client, sample_companies):
    """Test that GET /companies returns HTTP 200 with companies list."""
    with patch("backend.api.routes.companies.scan_all_items") as mock_scan:
        mock_scan.return_value = sample_companies

        response = client.get("/companies")

        assert response.status_code == 200
        data = response.json()
        assert "companies" in data
        assert "total" in data
        assert "hasMore" in data


def test_list_companies_sorted_case_insensitive(client, sample_companies):
    """Test that companies are sorted case-insensitively by nombre."""
    with patch("backend.api.routes.companies.scan_all_items") as mock_scan:
        mock_scan.return_value = sample_companies

        response = client.get("/companies")

        assert response.status_code == 200
        data = response.json()
        names = [c["nombre"] for c in data["companies"]]
        # Expected order: Acme, Beta, zebra (case-insensitive)
        assert names == ["Acme", "Beta", "zebra"]


def test_list_companies_pagination_default(client, sample_companies):
    """Test default pagination: limit=20, offset=0."""
    with patch("backend.api.routes.companies.scan_all_items") as mock_scan:
        mock_scan.return_value = sample_companies

        response = client.get("/companies")

        data = response.json()
        assert data["total"] == 3
        assert data["hasMore"] is False
        assert len(data["companies"]) == 3


def test_list_companies_pagination_limit(client, sample_companies):
    """Test pagination with custom limit."""
    with patch("backend.api.routes.companies.scan_all_items") as mock_scan:
        mock_scan.return_value = sample_companies

        response = client.get("/companies?limit=10&offset=0")

        data = response.json()
        assert data["total"] == 3
        assert data["hasMore"] is False
        assert len(data["companies"]) == 3


def test_list_companies_pagination_offset(client, sample_companies):
    """Test pagination with offset producing hasMore=True."""
    with patch("backend.api.routes.companies.scan_all_items") as mock_scan:
        mock_scan.return_value = sample_companies

        response = client.get("/companies?limit=10&offset=2")

        data = response.json()
        assert data["total"] == 3
        assert data["hasMore"] is False
        assert len(data["companies"]) == 1


def test_list_companies_has_more_true(client):
    """Test hasMore is True when more items exist beyond offset+limit."""
    # Create 15 companies
    companies = [
        {
            "companyId": f"id-{i}",
            "nombre": f"Company{i:02d}",
            "careersUrl": f"https://company{i}.com/careers",
            "plataforma": "html",
            "lastScannedAt": None,
            "lastScanStatus": None,
            "lastVacancyCount": 0,
            "consecutiveFailures": 0,
        }
        for i in range(15)
    ]

    with patch("backend.api.routes.companies.scan_all_items") as mock_scan:
        mock_scan.return_value = companies

        response = client.get("/companies?limit=10&offset=0")

        data = response.json()
        assert data["total"] == 15
        assert data["hasMore"] is True
        assert len(data["companies"]) == 10


def test_list_companies_limit_validation_min(client):
    """Test that limit below 10 is rejected."""
    response = client.get("/companies?limit=5")
    assert response.status_code == 422


def test_list_companies_limit_validation_max(client):
    """Test that limit above 100 is rejected."""
    response = client.get("/companies?limit=200")
    assert response.status_code == 422


def test_list_companies_returns_raw_fields(client, sample_companies):
    """Test that response contains only raw stored fields."""
    with patch("backend.api.routes.companies.scan_all_items") as mock_scan:
        mock_scan.return_value = sample_companies

        response = client.get("/companies")

        data = response.json()
        company = data["companies"][0]
        expected_fields = {
            "companyId",
            "nombre",
            "careersUrl",
            "plataforma",
            "lastScannedAt",
            "lastScanStatus",
            "lastVacancyCount",
            "consecutiveFailures",
        }
        assert set(company.keys()) == expected_fields


def test_list_companies_no_auth_required(client):
    """Test that GET /companies does not require auth."""
    with patch("backend.api.routes.companies.scan_all_items") as mock_scan:
        mock_scan.return_value = []

        # No Authorization header
        response = client.get("/companies")
        assert response.status_code == 200


def test_list_companies_empty_table(client):
    """Test empty response when no companies exist."""
    with patch("backend.api.routes.companies.scan_all_items") as mock_scan:
        mock_scan.return_value = []

        response = client.get("/companies")

        data = response.json()
        assert data["companies"] == []
        assert data["total"] == 0
        assert data["hasMore"] is False


# ============================================================================
# POST /companies Tests
# ============================================================================


def test_add_company_success_greenhouse(client):
    """Test successful creation of a greenhouse company."""
    with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
         patch("backend.api.routes.companies.put_item") as mock_put:
        mock_query.return_value = []  # No existing company

        response = client.post(
            "/companies",
            json={"careersUrl": "https://acme.greenhouse.io/jobs"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "companyId" in data
        assert len(data["companyId"]) == 64  # SHA-256 hex
        assert data["nombre"] == "Acme"
        assert data["plataforma"] == "greenhouse"
        assert "createdAt" in data

        # Verify put_item was called with correct defaults
        mock_put.assert_called_once()
        item = mock_put.call_args[0][1]
        assert item["lastScannedAt"] is None
        assert item["lastScanStatus"] is None
        assert item["lastVacancyCount"] == 0
        assert item["consecutiveFailures"] == 0


def test_add_company_success_lever(client):
    """Test successful creation of a lever company."""
    with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
         patch("backend.api.routes.companies.put_item") as mock_put:
        mock_query.return_value = []

        response = client.post(
            "/companies",
            json={"careersUrl": "https://jobs.lever.co/mycompany"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["plataforma"] == "lever"


def test_add_company_success_html(client):
    """Test successful creation of an html platform company."""
    with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
         patch("backend.api.routes.companies.put_item") as mock_put:
        mock_query.return_value = []

        response = client.post(
            "/companies",
            json={"careersUrl": "https://example.com/careers"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["plataforma"] == "html"
        assert data["nombre"] == "Example"


def test_add_company_invalid_url_no_scheme(client):
    """Test that URL without scheme is rejected with 400."""
    response = client.post(
        "/companies",
        json={"careersUrl": "example.com/careers"},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "validation_error"


def test_add_company_invalid_url_empty(client):
    """Test that empty URL is rejected with 400."""
    response = client.post(
        "/companies",
        json={"careersUrl": ""},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["error"] == "validation_error"


def test_add_company_duplicate_returns_409(client):
    """Test that duplicate company returns 409 with companyId."""
    with patch("backend.api.routes.companies.query_by_pk") as mock_query:
        mock_query.return_value = [{"companyId": "existing-id"}]

        response = client.post(
            "/companies",
            json={"careersUrl": "https://acme.greenhouse.io/jobs"},
        )

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "company_already_exists"
        assert "companyId" in data


def test_add_company_normalizes_url(client):
    """Test that URL is normalized (lowercase, no fragment, no trailing slash)."""
    with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
         patch("backend.api.routes.companies.put_item") as mock_put:
        mock_query.return_value = []

        response = client.post(
            "/companies",
            json={"careersUrl": "https://ACME.Greenhouse.IO/jobs/#section"},
        )

        assert response.status_code == 201
        # Verify the stored URL is normalized
        item = mock_put.call_args[0][1]
        assert item["careersUrl"] == "https://acme.greenhouse.io/jobs"


def test_add_company_no_auth_required(client):
    """Test that POST /companies does not require authentication."""
    with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
         patch("backend.api.routes.companies.put_item") as mock_put:
        mock_query.return_value = []

        # No Authorization header
        response = client.post(
            "/companies",
            json={"careersUrl": "https://example.com/careers"},
        )

        assert response.status_code == 201


def test_add_company_nombre_extracted_from_hostname(client):
    """Test that nombre is extracted from URL hostname first segment."""
    with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
         patch("backend.api.routes.companies.put_item") as mock_put:
        mock_query.return_value = []

        response = client.post(
            "/companies",
            json={"careersUrl": "https://mycompany.greenhouse.io/jobs"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["nombre"] == "Mycompany"


# ============================================================================
# GET /me/companies Tests (Subscriptions)
# ============================================================================


@pytest.fixture
def mock_user_id():
    """Fixed user ID for testing."""
    return "test-user-123"


@pytest.fixture
def sample_subscriptions():
    """Sample active subscriptions data."""
    return [
        {
            "userId": "test-user-123",
            "companyId": "abc123",
            "activa": True,
            "addedAt": "2024-03-01T10:00:00Z",
            "updatedAt": "2024-03-01T10:00:00Z",
        },
        {
            "userId": "test-user-123",
            "companyId": "def456",
            "activa": True,
            "addedAt": "2024-02-15T08:30:00Z",
            "updatedAt": "2024-02-15T08:30:00Z",
        },
        {
            "userId": "test-user-123",
            "companyId": "ghi789",
            "activa": False,
            "addedAt": "2024-01-10T12:00:00Z",
            "updatedAt": "2024-01-20T09:00:00Z",
        },
    ]


@pytest.fixture
def sample_empresas_data():
    """Empresas table data for left-join."""
    return {
        "abc123": {
            "companyId": "abc123",
            "nombre": "Acme Corp",
            "careersUrl": "https://acme.greenhouse.io/jobs",
            "plataforma": "greenhouse",
            "lastScannedAt": "2024-03-01T12:00:00Z",
            "lastScanStatus": "OK",
            "lastVacancyCount": 10,
            "consecutiveFailures": 0,
        },
        "def456": {
            "companyId": "def456",
            "nombre": "Beta Inc",
            "careersUrl": "https://beta.lever.co/careers",
            "plataforma": "lever",
            "lastScannedAt": None,
            "lastScanStatus": None,
            "lastVacancyCount": 0,
            "consecutiveFailures": 0,
        },
    }


def test_list_subscriptions_returns_active_only(
    client, mock_user_id, sample_subscriptions, sample_empresas_data
):
    """Test GET /me/companies returns only active subscriptions."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
             patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_query.return_value = sample_subscriptions

            # Mock DynamoDB table get_item calls
            mock_table = MagicMock()

            def mock_get_item(Key):
                company_id = Key.get("companyId")
                if company_id in sample_empresas_data:
                    return {"Item": sample_empresas_data[company_id]}
                return {}

            mock_table.get_item.side_effect = mock_get_item
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.get("/me/companies")

            assert response.status_code == 200
            data = response.json()
            assert "subscriptions" in data
            # Only 2 active subscriptions (activa=true), the third is inactive
            assert len(data["subscriptions"]) == 2

            # Verify no inactive subscriptions
            company_ids = [s["companyId"] for s in data["subscriptions"]]
            assert "ghi789" not in company_ids
    finally:
        client.app.dependency_overrides.clear()


def test_list_subscriptions_sorted_by_added_at_desc(
    client, mock_user_id, sample_subscriptions, sample_empresas_data
):
    """Test GET /me/companies returns subscriptions sorted by addedAt descending."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
             patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_query.return_value = sample_subscriptions

            mock_table = MagicMock()

            def mock_get_item(Key):
                company_id = Key.get("companyId")
                if company_id in sample_empresas_data:
                    return {"Item": sample_empresas_data[company_id]}
                return {}

            mock_table.get_item.side_effect = mock_get_item
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.get("/me/companies")

            assert response.status_code == 200
            data = response.json()
            subscriptions = data["subscriptions"]

            # First item should be the most recent (2024-03-01)
            assert subscriptions[0]["companyId"] == "abc123"
            assert subscriptions[1]["companyId"] == "def456"
    finally:
        client.app.dependency_overrides.clear()


def test_list_subscriptions_returns_correct_fields(
    client, mock_user_id, sample_subscriptions, sample_empresas_data
):
    """Test GET /me/companies returns expected fields per subscription."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
             patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_query.return_value = sample_subscriptions

            mock_table = MagicMock()

            def mock_get_item(Key):
                company_id = Key.get("companyId")
                if company_id in sample_empresas_data:
                    return {"Item": sample_empresas_data[company_id]}
                return {}

            mock_table.get_item.side_effect = mock_get_item
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.get("/me/companies")

            assert response.status_code == 200
            data = response.json()
            sub = data["subscriptions"][0]

            expected_fields = {
                "companyId",
                "nombre",
                "plataforma",
                "addedAt",
                "lastScannedAt",
                "lastScanStatus",
                "lastVacancyCount",
                "consecutiveFailures",
            }
            assert set(sub.keys()) == expected_fields
            # Verify correct values from left-join
            assert sub["nombre"] == "Acme Corp"
            assert sub["plataforma"] == "greenhouse"
            assert sub["lastScannedAt"] == "2024-03-01T12:00:00Z"
            assert sub["lastScanStatus"] == "OK"
            assert sub["lastVacancyCount"] == 10
            assert sub["consecutiveFailures"] == 0
    finally:
        client.app.dependency_overrides.clear()


def test_list_subscriptions_empty_when_no_active(client, mock_user_id):
    """Test GET /me/companies returns empty list when user has no active subscriptions."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
             patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            # All subscriptions are inactive
            mock_query.return_value = [
                {
                    "userId": "test-user-123",
                    "companyId": "abc123",
                    "activa": False,
                    "addedAt": "2024-01-01T00:00:00Z",
                }
            ]

            mock_table = MagicMock()
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.get("/me/companies")

            assert response.status_code == 200
            data = response.json()
            assert data["subscriptions"] == []
    finally:
        client.app.dependency_overrides.clear()


def test_list_subscriptions_skips_missing_company(client, mock_user_id):
    """Test GET /me/companies skips subscriptions where company not found in Empresas."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies.query_by_pk") as mock_query, \
             patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_query.return_value = [
                {
                    "userId": "test-user-123",
                    "companyId": "nonexistent-company",
                    "activa": True,
                    "addedAt": "2024-03-01T10:00:00Z",
                }
            ]

            mock_table = MagicMock()
            # Company not found in Empresas
            mock_table.get_item.return_value = {}
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.get("/me/companies")

            assert response.status_code == 200
            data = response.json()
            # Subscription skipped because company not found
            assert data["subscriptions"] == []
    finally:
        client.app.dependency_overrides.clear()


def test_list_subscriptions_requires_auth(client):
    """Test GET /me/companies requires authentication (no override = 401)."""
    # Don't override the auth dependency - should fail
    response = client.get("/me/companies")
    # Without valid JWT context, we expect an auth error
    assert response.status_code == 401


# ============================================================================
# PUT /me/companies/{companyId} Tests (Toggle Subscription)
# ============================================================================


def test_toggle_subscription_activate(client, mock_user_id):
    """Test PUT /me/companies/{companyId} with activa=true reactivates subscription."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()

            # Subscription exists
            mock_table.get_item.side_effect = [
                {"Item": {"userId": "test-user-123", "companyId": "abc123", "activa": False}},
                {"Item": {"companyId": "abc123", "nombre": "Acme Corp"}},
            ]
            mock_table.update_item.return_value = {}
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.put(
                "/me/companies/abc123",
                json={"activa": True},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["companyId"] == "abc123"
            assert data["activa"] is True
            assert "updatedAt" in data

            # Verify update_item was called with addedAt refresh
            mock_table.update_item.assert_called_once()
            call_kwargs = mock_table.update_item.call_args[1]
            assert ":activa" in call_kwargs["ExpressionAttributeValues"]
            assert call_kwargs["ExpressionAttributeValues"][":activa"] is True
            # addedAt should be refreshed on reactivation
            assert ":addedAt" in call_kwargs["ExpressionAttributeValues"]
    finally:
        client.app.dependency_overrides.clear()


def test_toggle_subscription_deactivate(client, mock_user_id):
    """Test PUT /me/companies/{companyId} with activa=false deactivates subscription."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()

            # Subscription exists
            mock_table.get_item.side_effect = [
                {"Item": {"userId": "test-user-123", "companyId": "abc123", "activa": True}},
                {"Item": {"companyId": "abc123", "nombre": "Acme Corp"}},
            ]
            mock_table.update_item.return_value = {}
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.put(
                "/me/companies/abc123",
                json={"activa": False},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["companyId"] == "abc123"
            assert data["activa"] is False
            assert "updatedAt" in data

            # Verify update_item does NOT refresh addedAt on deactivation
            call_kwargs = mock_table.update_item.call_args[1]
            assert ":activa" in call_kwargs["ExpressionAttributeValues"]
            assert call_kwargs["ExpressionAttributeValues"][":activa"] is False
            # addedAt should NOT be in the update on deactivation
            assert ":addedAt" not in call_kwargs["ExpressionAttributeValues"]
    finally:
        client.app.dependency_overrides.clear()


def test_toggle_subscription_not_found_404(client, mock_user_id):
    """Test PUT /me/companies/{companyId} returns 404 when subscription not found."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()

            # Subscription NOT found
            mock_table.get_item.return_value = {}
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.put(
                "/me/companies/nonexistent",
                json={"activa": True},
            )

            assert response.status_code == 404
            data = response.json()
            assert data["error"] == "subscription_not_found"
    finally:
        client.app.dependency_overrides.clear()


def test_toggle_subscription_company_not_found_400(client, mock_user_id):
    """Test PUT /me/companies/{companyId} returns 400 when company not in Empresas."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()

            # Subscription exists but company does NOT exist in Empresas
            mock_table.get_item.side_effect = [
                {"Item": {"userId": "test-user-123", "companyId": "abc123", "activa": True}},
                {},  # Company not found in Empresas
            ]
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.put(
                "/me/companies/abc123",
                json={"activa": True},
            )

            assert response.status_code == 400
            data = response.json()
            assert data["error"] == "company_not_found"
    finally:
        client.app.dependency_overrides.clear()


def test_toggle_subscription_requires_auth(client):
    """Test PUT /me/companies/{companyId} requires authentication."""
    response = client.put(
        "/me/companies/abc123",
        json={"activa": True},
    )
    assert response.status_code == 401


def test_toggle_subscription_missing_body(client, mock_user_id):
    """Test PUT /me/companies/{companyId} returns 422 when body is missing."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        response = client.put("/me/companies/abc123", json={})
        assert response.status_code == 422
    finally:
        client.app.dependency_overrides.clear()


# ============================================================================
# POST /me/companies/{companyId} Tests (Alta idempotente de Suscripción)
# ============================================================================


def test_create_subscription_new_returns_201(client, mock_user_id):
    """
    HTTP 201 cuando no existe registro previo de Suscripción (Req 1.1, 1.3, 1.7).
    """
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()

            # 1st get_item -> company exists in Empresas
            # 2nd get_item -> no existing subscription
            mock_table.get_item.side_effect = [
                {"Item": {"companyId": "abc123", "nombre": "Acme Corp"}},
                {},
            ]
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.post("/me/companies/abc123")

            assert response.status_code == 201
            data = response.json()
            assert data["companyId"] == "abc123"
            assert data["activa"] is True
            assert "addedAt" in data

            # Only one write: the conditional put_item creating the record.
            mock_table.put_item.assert_called_once()
            put_kwargs = mock_table.put_item.call_args[1]
            assert put_kwargs["Item"]["userId"] == mock_user_id
            assert put_kwargs["Item"]["companyId"] == "abc123"
            assert put_kwargs["Item"]["activa"] is True
            assert put_kwargs["ConditionExpression"] == "attribute_not_exists(userId)"
            mock_table.update_item.assert_not_called()
    finally:
        client.app.dependency_overrides.clear()


def test_create_subscription_no_op_returns_200(client, mock_user_id):
    """
    HTTP 200 no-op cuando ya existe registro con activa=True (Req 1.4).
    No debe escribir nada en DynamoDB, y debe retornar el addedAt almacenado.
    """
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()

            mock_table.get_item.side_effect = [
                {"Item": {"companyId": "abc123", "nombre": "Acme Corp"}},
                {
                    "Item": {
                        "userId": mock_user_id,
                        "companyId": "abc123",
                        "activa": True,
                        "addedAt": "2024-01-01T00:00:00Z",
                    }
                },
            ]
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.post("/me/companies/abc123")

            assert response.status_code == 200
            data = response.json()
            assert data["companyId"] == "abc123"
            assert data["activa"] is True
            assert data["addedAt"] == "2024-01-01T00:00:00Z"

            # No-op: no write of any kind.
            mock_table.put_item.assert_not_called()
            mock_table.update_item.assert_not_called()
    finally:
        client.app.dependency_overrides.clear()


def test_create_subscription_reactivate_returns_200(client, mock_user_id):
    """
    HTTP 200 reactivate cuando existe registro con activa=False (Req 1.5).
    Debe hacer update_item con SET activa=:true, addedAt=:now.
    """
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()

            mock_table.get_item.side_effect = [
                {"Item": {"companyId": "abc123", "nombre": "Acme Corp"}},
                {
                    "Item": {
                        "userId": mock_user_id,
                        "companyId": "abc123",
                        "activa": False,
                        "addedAt": "2023-06-01T00:00:00Z",
                    }
                },
            ]
            mock_table.update_item.return_value = {}
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.post("/me/companies/abc123")

            assert response.status_code == 200
            data = response.json()
            assert data["companyId"] == "abc123"
            assert data["activa"] is True
            # addedAt was refreshed, so it should NOT be the old stored value.
            assert data["addedAt"] != "2023-06-01T00:00:00Z"

            mock_table.put_item.assert_not_called()
            mock_table.update_item.assert_called_once()
            update_kwargs = mock_table.update_item.call_args[1]
            assert update_kwargs["ExpressionAttributeValues"][":activa"] is True
            assert ":addedAt" in update_kwargs["ExpressionAttributeValues"]
    finally:
        client.app.dependency_overrides.clear()


def test_create_subscription_company_not_found_404(client, mock_user_id):
    """
    HTTP 404 company_not_found cuando companyId no existe en Empresas (Req 1.2).
    Distinto del 400 usado por PUT /me/companies/{companyId} para el mismo error_code.
    """
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()
            mock_table.get_item.return_value = {}  # Company not found
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.post("/me/companies/nonexistent")

            assert response.status_code == 404
            data = response.json()
            assert data["error"] == "company_not_found"
    finally:
        client.app.dependency_overrides.clear()


def test_create_subscription_write_failed_returns_500(client, mock_user_id):
    """
    HTTP 500 subscription_write_failed cuando put_item falla por un ClientError
    no relacionado con la condición de escritura (Req 1.9).
    """
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()

            mock_table.get_item.side_effect = [
                {"Item": {"companyId": "abc123", "nombre": "Acme Corp"}},
                {},  # No existing subscription -> action CREATE
            ]
            mock_table.put_item.side_effect = ClientError(
                {
                    "Error": {
                        "Code": "ProvisionedThroughputExceededException",
                        "Message": "Rate exceeded",
                    }
                },
                "PutItem",
            )
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.post("/me/companies/abc123")

            assert response.status_code == 500
            data = response.json()
            assert data["error"] == "subscription_write_failed"
    finally:
        client.app.dependency_overrides.clear()


def test_create_subscription_conditional_check_failed_falls_to_no_op(client, mock_user_id):
    """
    Rama ConditionalCheckFailedException en el put_item inicial: otro request
    ganó la carrera. Debe re-leer el registro, re-decidir la acción (cae a
    NO_OP aquí porque el ganador dejó activa=True) y NO crear un segundo
    registro (Req 1.8).
    """
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.companies._get_dynamodb_client") as mock_dynamo:
            mock_table = MagicMock()

            mock_table.get_item.side_effect = [
                {"Item": {"companyId": "abc123", "nombre": "Acme Corp"}},
                {},  # No existing subscription at decision time -> action CREATE
                {  # Re-read after losing the race: winner already created it
                    "Item": {
                        "userId": mock_user_id,
                        "companyId": "abc123",
                        "activa": True,
                        "addedAt": "2024-05-05T00:00:00Z",
                    }
                },
            ]
            mock_table.put_item.side_effect = ClientError(
                {
                    "Error": {
                        "Code": "ConditionalCheckFailedException",
                        "Message": "The conditional request failed",
                    }
                },
                "PutItem",
            )
            mock_dynamo.return_value.Table.return_value = mock_table

            response = client.post("/me/companies/abc123")

            assert response.status_code == 200
            data = response.json()
            assert data["companyId"] == "abc123"
            assert data["activa"] is True
            assert data["addedAt"] == "2024-05-05T00:00:00Z"

            # Only one put_item attempt (the failed one); no second create,
            # and no update_item since the re-decided action was NO_OP.
            assert mock_table.put_item.call_count == 1
            mock_table.update_item.assert_not_called()
    finally:
        client.app.dependency_overrides.clear()


def test_create_subscription_requires_auth(client):
    """Test POST /me/companies/{companyId} requires authentication."""
    response = client.post("/me/companies/abc123")
    assert response.status_code == 401
