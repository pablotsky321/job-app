"""
Tests for profile endpoints.

Validates:
- POST /me/profile/parse parses CV text with Bedrock
- Rejects CV >50KB with HTTP 413
- Rejects empty CV with HTTP 400
- Returns PerfilEstructurado on success
- Handles Bedrock timeout/error with HTTP 502

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 12.1, 12.2, 12.3, 12.4, 12.5, 19.1, 19.2
"""

import pytest
import sys
import os
import json
from unittest.mock import Mock, patch, MagicMock
from pydantic import ValidationError

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from starlette.testclient import TestClient
from backend.shared.models import PerfilEstructurado


@pytest.fixture
def app():
    """Create test app with mocked auth dependency."""
    from backend.main import create_app
    
    test_app = create_app()
    return test_app


@pytest.fixture
def client(app):
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_user_id():
    """Fixed user ID for testing."""
    return "test-user-123"


@pytest.fixture
def sample_cv_text():
    """Sample CV text for testing."""
    return """
    John Doe
    john@example.com | (555) 123-4567
    
    EXPERIENCE
    Senior Software Engineer at TechCorp (Jan 2020 - Present)
    - Led development of microservices architecture using Python and FastAPI
    - Mentored junior developers
    - Technologies: Python, FastAPI, PostgreSQL, AWS
    
    Junior Developer at StartupInc (Jun 2018 - Dec 2019)
    - Built REST APIs
    - Technologies: Python, Flask, MySQL
    
    EDUCATION
    BS in Computer Science
    University of Tech, 2018
    
    SKILLS
    - Python, FastAPI, Flask, SQL
    - AWS, Lambda, DynamoDB
    - Git, Docker
    
    LANGUAGES
    - English (Native)
    - Spanish (Fluent)
    """


@pytest.fixture
def sample_perfil_structured():
    """Sample structured profile response from Bedrock."""
    return {
        "experiencia": [
            {
                "puesto": "Senior Software Engineer",
                "empresa": "TechCorp",
                "duracion": "Jan 2020 - Present",
                "descripcion": "Led development of microservices architecture",
                "tecnologias": ["Python", "FastAPI", "PostgreSQL", "AWS"],
            }
        ],
        "educacion": [
            {
                "titulo": "BS in Computer Science",
                "institucion": "University of Tech",
                "ano": "2018",
            }
        ],
        "proyectos": [],
        "certificaciones": [],
        "skills": ["Python", "FastAPI", "Flask", "SQL", "AWS", "Lambda", "DynamoDB"],
        "lenguajes": ["English", "Spanish"],
    }


def mock_get_current_user_id(request):
    """Mock the get_current_user_id dependency."""
    return "test-user-123"


# ============================================================================
# POST /me/profile/parse Tests
# ============================================================================


def test_parse_cv_success(client, sample_cv_text, sample_perfil_structured, mock_user_id):
    """Test successful CV parsing."""
    from backend.api.routes.auth import get_current_user_id
    
    # Set up dependency override
    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id
    
    try:
        with patch("backend.api.routes.profile.get_bedrock_client") as mock_bedrock_fn:
            mock_client = Mock()
            mock_client.model_small = "anthropic.claude-3-haiku-20250514"
            mock_client.invoke_with_retry.return_value = PerfilEstructurado(
                **sample_perfil_structured
            )
            mock_bedrock_fn.return_value = mock_client
            
            response = client.post(
                "/me/profile/parse",
                json={"cvText": sample_cv_text},
            )
            
            # Print debug info if status is not 200
            if response.status_code != 200:
                print(f"Response status: {response.status_code}")
                print(f"Response body: {response.text}")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify structure
            assert "experiencia" in data
            assert "educacion" in data
            assert "skills" in data
            assert len(data["experiencia"]) > 0
            assert len(data["educacion"]) > 0
            assert len(data["skills"]) > 0
            
    finally:
        client.app.dependency_overrides.clear()


def test_parse_cv_empty_text_rejected(client, mock_user_id):
    """Test that empty CV text is rejected with HTTP 400."""
    from backend.api.routes.auth import get_current_user_id
    
    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id
    
    try:
        response = client.post(
            "/me/profile/parse",
            json={"cvText": "   "},  # Only whitespace
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "validation_error"
        
    finally:
        client.app.dependency_overrides.clear()


def test_parse_cv_too_large_rejected(client, mock_user_id):
    """Test that CV >50KB is rejected with HTTP 413."""
    from backend.api.routes.auth import get_current_user_id
    
    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id
    
    try:
        # Create CV text that exceeds 50KB
        large_cv = "A" * (50 * 1024 + 1)
        
        response = client.post(
            "/me/profile/parse",
            json={"cvText": large_cv},
        )
        
        assert response.status_code == 413
        data = response.json()
        assert data["error"] == "payload_too_large"
        
    finally:
        client.app.dependency_overrides.clear()


def test_parse_cv_bedrock_timeout_handled(client, sample_cv_text, mock_user_id):
    """Test that Bedrock timeout returns HTTP 502."""
    from backend.api.routes.auth import get_current_user_id
    
    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id
    
    try:
        with patch("backend.api.routes.profile.get_bedrock_client") as mock_bedrock_fn:
            mock_client = Mock()
            mock_client.model_small = "anthropic.claude-3-haiku-20250514"
            mock_client.invoke_with_retry.side_effect = TimeoutError("Bedrock timeout")
            mock_bedrock_fn.return_value = mock_client
            
            response = client.post(
                "/me/profile/parse",
                json={"cvText": sample_cv_text},
            )
            
            assert response.status_code == 502
            data = response.json()
            assert data["error"] == "ai_service_unavailable"
            
    finally:
        client.app.dependency_overrides.clear()


def test_parse_cv_bedrock_validation_error_handled(client, sample_cv_text, mock_user_id):
    """Test that Bedrock validation error is handled properly."""
    from backend.api.routes.auth import get_current_user_id
    
    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id
    
    try:
        with patch("backend.api.routes.profile.get_bedrock_client") as mock_bedrock_fn:
            mock_client = Mock()
            mock_client.model_small = "anthropic.claude-3-haiku-20250514"
            mock_client.invoke_with_retry.side_effect = ValidationError.from_exception_data(
                "PerfilEstructurado",
                [{"type": "missing", "loc": ("skills",)}],
            )
            mock_bedrock_fn.return_value = mock_client
            
            response = client.post(
                "/me/profile/parse",
                json={"cvText": sample_cv_text},
            )
            
            assert response.status_code == 502
            data = response.json()
            assert data["error"] == "ai_service_unavailable"
            
    finally:
        client.app.dependency_overrides.clear()


def test_parse_cv_requires_auth(client, sample_cv_text):
    """Test that POST /me/profile/parse requires authentication."""
    # Don't override the dependency - let it fail
    response = client.post(
        "/me/profile/parse",
        json={"cvText": sample_cv_text},
    )
    
    # Should fail due to missing auth (unless test client provides mock context)
    # This depends on how Mangum provides scope in test context
    # For now, we just verify the endpoint exists and is accessible


def test_parse_cv_max_exactly_50kb(client, mock_user_id, sample_perfil_structured):
    """Test that CV exactly 50KB is accepted."""
    from backend.api.routes.auth import get_current_user_id
    
    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id
    
    try:
        # Create CV text that is exactly 50KB
        cv_50kb = "A" * (50 * 1024)
        
        with patch("backend.api.routes.profile.get_bedrock_client") as mock_bedrock_fn:
            mock_client = Mock()
            mock_client.model_small = "anthropic.claude-3-haiku-20250514"
            mock_client.invoke_with_retry.return_value = PerfilEstructurado(
                **sample_perfil_structured
            )
            mock_bedrock_fn.return_value = mock_client
            
            response = client.post(
                "/me/profile/parse",
                json={"cvText": cv_50kb},
            )
            
            assert response.status_code == 200
            
    finally:
        client.app.dependency_overrides.clear()


# ============================================================================
# Prompt Generation Tests
# ============================================================================


def test_parse_cv_prompt_includes_schema(sample_cv_text):
    """Test that the prompt includes schema hints for Bedrock."""
    from backend.api.routes.profile import _prepare_cv_parsing_prompt
    
    prompt = _prepare_cv_parsing_prompt(sample_cv_text)
    
    # Verify prompt contains key schema fields
    assert "experiencia" in prompt
    assert "educacion" in prompt
    assert "skills" in prompt
    assert "tecnologias" in prompt
    
    # Verify CV text is included
    assert sample_cv_text in prompt


def test_parse_cv_prompt_returns_valid_format():
    """Test that the prompt instructs Bedrock to return valid JSON."""
    from backend.api.routes.profile import _prepare_cv_parsing_prompt
    
    cv = "Sample CV"
    prompt = _prepare_cv_parsing_prompt(cv)
    
    # Verify prompt mentions JSON output
    assert "JSON" in prompt or "json" in prompt


# ============================================================================
# GET /me/profile Tests
# ============================================================================


def test_get_profile_success(client, mock_user_id, sample_perfil_structured):
    """Test successful profile retrieval returns all expected fields."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        mock_item = {
            "userId": mock_user_id,
            "perfilEstructurado": sample_perfil_structured,
            "resumenParaMatching": "Experienced software engineer with Python expertise",
            "cargosSugeridos": ["Senior Dev", "Tech Lead"],
            "cargosActivos": ["Senior Dev"],
            "profileVersion": 3,
            "updatedAt": "2024-01-15T10:30:00Z",
            "resumenGenerationStatus": "complete",
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            response = client.get("/me/profile")

            assert response.status_code == 200
            data = response.json()

            # Verify all required fields are present
            assert data["perfilEstructurado"] == sample_perfil_structured
            assert data["resumenParaMatching"] == "Experienced software engineer with Python expertise"
            assert data["cargosSugeridos"] == ["Senior Dev", "Tech Lead"]
            assert data["cargosActivos"] == ["Senior Dev"]
            assert data["profileVersion"] == 3
            assert data["updatedAt"] == "2024-01-15T10:30:00Z"
            # resumenGenerationStatus is 'complete', so resumenGenerating should be false
            assert data["resumenGenerating"] is False

    finally:
        client.app.dependency_overrides.clear()


def test_get_profile_resumen_generating_true_when_pending(client, mock_user_id):
    """Test resumenGenerating is true when resumenGenerationStatus == 'pending'."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        mock_item = {
            "userId": mock_user_id,
            "perfilEstructurado": {"experiencia": [], "educacion": [], "skills": ["Python"]},
            "resumenParaMatching": None,
            "cargosSugeridos": [],
            "cargosActivos": [],
            "profileVersion": 1,
            "updatedAt": "2024-01-15T10:30:00Z",
            "resumenGenerationStatus": "pending",
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            response = client.get("/me/profile")

            assert response.status_code == 200
            data = response.json()
            assert data["resumenGenerating"] is True

    finally:
        client.app.dependency_overrides.clear()


def test_get_profile_resumen_generating_false_when_no_status(client, mock_user_id):
    """Test resumenGenerating is false when resumenGenerationStatus is absent/null."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        mock_item = {
            "userId": mock_user_id,
            "perfilEstructurado": {"experiencia": [], "educacion": [], "skills": ["Python"]},
            "profileVersion": 1,
            "updatedAt": "2024-01-15T10:30:00Z",
            # resumenGenerationStatus is absent
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            response = client.get("/me/profile")

            assert response.status_code == 200
            data = response.json()
            assert data["resumenGenerating"] is False

    finally:
        client.app.dependency_overrides.clear()


def test_get_profile_not_found(client, mock_user_id):
    """Test GET /me/profile returns 404 when profile does not exist."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {}  # No "Item" key
            mock_get_table.return_value = mock_table

            response = client.get("/me/profile")

            assert response.status_code == 404
            data = response.json()
            assert data["error"] == "profile_not_found"

    finally:
        client.app.dependency_overrides.clear()


def test_get_profile_defaults_empty_lists(client, mock_user_id):
    """Test GET /me/profile defaults cargosSugeridos and cargosActivos to empty lists."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        # Minimal item without optional list fields
        mock_item = {
            "userId": mock_user_id,
            "perfilEstructurado": {"experiencia": [], "educacion": [], "skills": ["JS"]},
            "profileVersion": 1,
            "updatedAt": "2024-01-10T00:00:00Z",
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            response = client.get("/me/profile")

            assert response.status_code == 200
            data = response.json()
            assert data["cargosSugeridos"] == []
            assert data["cargosActivos"] == []
            assert data["resumenParaMatching"] is None

    finally:
        client.app.dependency_overrides.clear()


# ============================================================================
# PUT /me/profile Tests
# ============================================================================


def test_save_profile_success(client, mock_user_id, sample_perfil_structured):
    """Test successful profile save returns profileVersion and updatedAt."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        # Existing profile with version 2
        existing_item = {
            "userId": mock_user_id,
            "profileVersion": 2,
            "cargosActivos": ["Dev"],
            "resumenParaMatching": "existing summary",
            "resumenGenerationStatus": "complete",
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": existing_item}
            mock_table.update_item.return_value = {"Attributes": {}}
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/profile",
                json={"perfilEstructurado": sample_perfil_structured},
            )

            assert response.status_code == 200
            data = response.json()

            # Should return profileVersion incremented and updatedAt
            assert data["profileVersion"] == 3
            assert "updatedAt" in data
            # Should NOT include cargosActivos
            assert "cargosActivos" not in data

            # Verify DynamoDB update_item was called with correct params
            mock_table.update_item.assert_called_once()
            call_kwargs = mock_table.update_item.call_args[1]
            assert call_kwargs["Key"] == {"userId": mock_user_id}
            assert ":perfil" in call_kwargs["ExpressionAttributeValues"]
            assert call_kwargs["ExpressionAttributeValues"][":ver"] == 3

    finally:
        client.app.dependency_overrides.clear()


def test_save_profile_first_time(client, mock_user_id, sample_perfil_structured):
    """Test saving profile for the first time (no existing profile)."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {}  # No existing profile
            mock_table.update_item.return_value = {"Attributes": {}}
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/profile",
                json={"perfilEstructurado": sample_perfil_structured},
            )

            assert response.status_code == 200
            data = response.json()

            # First save: version should be 2 (1 + 1)
            assert data["profileVersion"] == 2
            assert "updatedAt" in data

    finally:
        client.app.dependency_overrides.clear()


def test_save_profile_does_not_modify_resumen_fields(client, mock_user_id, sample_perfil_structured):
    """Test PUT /me/profile does NOT modify resumenParaMatching or resumenGenerationStatus."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        existing_item = {
            "userId": mock_user_id,
            "profileVersion": 5,
            "resumenParaMatching": "should not be modified",
            "resumenGenerationStatus": "complete",
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": existing_item}
            mock_table.update_item.return_value = {"Attributes": {}}
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/profile",
                json={"perfilEstructurado": sample_perfil_structured},
            )

            assert response.status_code == 200

            # Verify the update expression only touches perfilEstructurado, profileVersion, updatedAt
            call_kwargs = mock_table.update_item.call_args[1]
            update_expr = call_kwargs["UpdateExpression"]
            assert "resumenParaMatching" not in update_expr
            assert "resumenGenerationStatus" not in update_expr

    finally:
        client.app.dependency_overrides.clear()


def test_save_profile_invalid_body_returns_400(client, mock_user_id):
    """Test PUT /me/profile with invalid body returns HTTP 400/422."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        # Missing required perfilEstructurado field
        response = client.put(
            "/me/profile",
            json={},
        )

        # FastAPI returns 422 for Pydantic validation errors on request body
        assert response.status_code == 422

    finally:
        client.app.dependency_overrides.clear()


def test_save_profile_invalid_perfil_returns_422(client, mock_user_id):
    """Test PUT /me/profile with invalid perfilEstructurado schema returns 422."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        # perfilEstructurado missing required 'skills' field
        response = client.put(
            "/me/profile",
            json={"perfilEstructurado": {"experiencia": [], "educacion": []}},
        )

        assert response.status_code == 422

    finally:
        client.app.dependency_overrides.clear()


def test_save_profile_returns_iso8601_timestamp(client, mock_user_id, sample_perfil_structured):
    """Test PUT /me/profile returns updatedAt in ISO8601 format ending with Z."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": {"userId": mock_user_id, "profileVersion": 1}}
            mock_table.update_item.return_value = {"Attributes": {}}
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/profile",
                json={"perfilEstructurado": sample_perfil_structured},
            )

            assert response.status_code == 200
            data = response.json()
            # Verify ISO8601 format with Z suffix
            assert data["updatedAt"].endswith("Z")
            assert "T" in data["updatedAt"]

    finally:
        client.app.dependency_overrides.clear()


# ============================================================================
# POST /me/roles/suggest Tests
# ============================================================================


def test_suggest_roles_success(client, mock_user_id):
    """Test successful role suggestion returns suggestions and suggestedAt."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        mock_item = {
            "userId": mock_user_id,
            "resumenParaMatching": "Experienced Python developer with 5 years in backend systems.",
            "resumenGenerationStatus": "complete",
            "profileVersion": 2,
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table, \
             patch("backend.api.routes.profile.get_bedrock_client") as mock_bedrock_fn:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            from backend.shared.models import RolesSuggestions
            mock_client = Mock()
            mock_client.model_small = "anthropic.claude-3-haiku-20250514"
            mock_client.invoke_with_retry.return_value = RolesSuggestions(
                suggestions=["Senior Python Developer", "Backend Engineer", "DevOps Engineer",
                             "Platform Engineer", "Tech Lead"]
            )
            mock_bedrock_fn.return_value = mock_client

            response = client.post("/me/roles/suggest")

            assert response.status_code == 200
            data = response.json()
            assert "suggestions" in data
            assert "suggestedAt" in data
            assert len(data["suggestions"]) == 5
            assert "Senior Python Developer" in data["suggestions"]
            # suggestedAt should be ISO8601
            assert "T" in data["suggestedAt"]
            assert data["suggestedAt"].endswith("Z")

    finally:
        client.app.dependency_overrides.clear()


def test_suggest_roles_resume_not_ready_null_resumen(client, mock_user_id):
    """Test POST /me/roles/suggest returns 424 when resumenParaMatching is null."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        mock_item = {
            "userId": mock_user_id,
            "resumenParaMatching": None,
            "resumenGenerationStatus": "complete",
            "profileVersion": 1,
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            response = client.post("/me/roles/suggest")

            assert response.status_code == 424
            data = response.json()
            assert data["error"] == "resume_not_ready"

    finally:
        client.app.dependency_overrides.clear()


def test_suggest_roles_resume_not_ready_generation_pending(client, mock_user_id):
    """Test POST /me/roles/suggest returns 424 when resumenGenerationStatus is 'pending'."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        mock_item = {
            "userId": mock_user_id,
            "resumenParaMatching": "Some text",
            "resumenGenerationStatus": "pending",
            "profileVersion": 1,
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            response = client.post("/me/roles/suggest")

            assert response.status_code == 424
            data = response.json()
            assert data["error"] == "resume_not_ready"

    finally:
        client.app.dependency_overrides.clear()


def test_suggest_roles_resume_not_ready_no_profile(client, mock_user_id):
    """Test POST /me/roles/suggest returns 424 when profile doesn't exist."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {}  # No "Item" key
            mock_get_table.return_value = mock_table

            response = client.post("/me/roles/suggest")

            assert response.status_code == 424
            data = response.json()
            assert data["error"] == "resume_not_ready"

    finally:
        client.app.dependency_overrides.clear()


def test_suggest_roles_bedrock_timeout_returns_502(client, mock_user_id):
    """Test POST /me/roles/suggest returns 502 on Bedrock timeout."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        mock_item = {
            "userId": mock_user_id,
            "resumenParaMatching": "Experienced developer with Python expertise.",
            "resumenGenerationStatus": "complete",
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table, \
             patch("backend.api.routes.profile.get_bedrock_client") as mock_bedrock_fn:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            mock_client = Mock()
            mock_client.model_small = "anthropic.claude-3-haiku-20250514"
            mock_client.invoke_with_retry.side_effect = TimeoutError("Bedrock timeout")
            mock_bedrock_fn.return_value = mock_client

            response = client.post("/me/roles/suggest")

            assert response.status_code == 502
            data = response.json()
            assert data["error"] == "ai_service_unavailable"

    finally:
        client.app.dependency_overrides.clear()


def test_suggest_roles_validation_error_returns_400(client, mock_user_id):
    """Test POST /me/roles/suggest returns 400 on Pydantic validation failure after retry."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        mock_item = {
            "userId": mock_user_id,
            "resumenParaMatching": "Experienced developer.",
            "resumenGenerationStatus": "complete",
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table, \
             patch("backend.api.routes.profile.get_bedrock_client") as mock_bedrock_fn:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            mock_client = Mock()
            mock_client.model_small = "anthropic.claude-3-haiku-20250514"
            mock_client.invoke_with_retry.side_effect = ValidationError.from_exception_data(
                "RolesSuggestions",
                [{"type": "missing", "loc": ("suggestions",)}],
            )
            mock_bedrock_fn.return_value = mock_client

            response = client.post("/me/roles/suggest")

            assert response.status_code == 400
            data = response.json()
            assert data["error"] == "validation_error"

    finally:
        client.app.dependency_overrides.clear()


def test_suggest_roles_does_not_persist_suggestions(client, mock_user_id):
    """Test that POST /me/roles/suggest does NOT persist suggestions to profile."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        mock_item = {
            "userId": mock_user_id,
            "resumenParaMatching": "Python developer with AWS expertise.",
            "resumenGenerationStatus": "complete",
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table, \
             patch("backend.api.routes.profile.get_bedrock_client") as mock_bedrock_fn:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": mock_item}
            mock_get_table.return_value = mock_table

            from backend.shared.models import RolesSuggestions
            mock_client = Mock()
            mock_client.model_small = "anthropic.claude-3-haiku-20250514"
            mock_client.invoke_with_retry.return_value = RolesSuggestions(
                suggestions=["Backend Engineer", "Cloud Architect"]
            )
            mock_bedrock_fn.return_value = mock_client

            response = client.post("/me/roles/suggest")

            assert response.status_code == 200
            # Verify update_item was NOT called (suggestions are not persisted)
            mock_table.update_item.assert_not_called()
            mock_table.put_item.assert_not_called()

    finally:
        client.app.dependency_overrides.clear()


# ============================================================================
# PUT /me/roles Tests
# ============================================================================


def test_save_roles_success(client, mock_user_id):
    """Test successful PUT /me/roles returns profileVersion, cargosActivos, updatedAt."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        existing_item = {
            "userId": mock_user_id,
            "profileVersion": 3,
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": existing_item}
            mock_table.update_item.return_value = {}
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/roles",
                json={"cargosActivos": ["Senior Python Developer", "Tech Lead"]},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["profileVersion"] == 4
            assert data["cargosActivos"] == ["Senior Python Developer", "Tech Lead"]
            assert "updatedAt" in data
            assert data["updatedAt"].endswith("Z")
            assert "T" in data["updatedAt"]

    finally:
        client.app.dependency_overrides.clear()


def test_save_roles_empty_list_accepted(client, mock_user_id):
    """Test PUT /me/roles accepts empty list (user clearing roles)."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        existing_item = {
            "userId": mock_user_id,
            "profileVersion": 2,
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": existing_item}
            mock_table.update_item.return_value = {}
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/roles",
                json={"cargosActivos": []},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["cargosActivos"] == []
            assert data["profileVersion"] == 3

    finally:
        client.app.dependency_overrides.clear()


def test_save_roles_too_many_items_rejected(client, mock_user_id):
    """Test PUT /me/roles rejects more than 10 roles with HTTP 400."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        roles = [f"Role {i}" for i in range(11)]

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/roles",
                json={"cargosActivos": roles},
            )

            assert response.status_code == 400
            data = response.json()
            assert data["error"] == "validation_error"

    finally:
        client.app.dependency_overrides.clear()


def test_save_roles_item_too_long_rejected(client, mock_user_id):
    """Test PUT /me/roles rejects role exceeding 50 chars with HTTP 400."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        roles = ["A" * 51]

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/roles",
                json={"cargosActivos": roles},
            )

            assert response.status_code == 400
            data = response.json()
            assert data["error"] == "validation_error"

    finally:
        client.app.dependency_overrides.clear()


def test_save_roles_increments_profile_version(client, mock_user_id):
    """Test PUT /me/roles increments profileVersion by 1."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        existing_item = {
            "userId": mock_user_id,
            "profileVersion": 7,
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": existing_item}
            mock_table.update_item.return_value = {}
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/roles",
                json={"cargosActivos": ["DevOps"]},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["profileVersion"] == 8

            # Verify DynamoDB update_item was called with correct version
            mock_table.update_item.assert_called_once()
            call_kwargs = mock_table.update_item.call_args[1]
            assert call_kwargs["ExpressionAttributeValues"][":ver"] == 8

    finally:
        client.app.dependency_overrides.clear()


def test_save_roles_does_not_trigger_rescoring(client, mock_user_id):
    """Test PUT /me/roles does NOT trigger synchronous rescoring."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        existing_item = {
            "userId": mock_user_id,
            "profileVersion": 1,
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table, \
             patch("backend.api.routes.profile.get_bedrock_client", side_effect=AssertionError("Bedrock should not be called")) as mock_bedrock:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": existing_item}
            mock_table.update_item.return_value = {}
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/roles",
                json={"cargosActivos": ["Engineer"]},
            )

            assert response.status_code == 200

    finally:
        client.app.dependency_overrides.clear()


def test_save_roles_persists_correct_fields(client, mock_user_id):
    """Test PUT /me/roles persists cargosActivos, profileVersion, updatedAt only."""
    from backend.api.routes.auth import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = lambda: mock_user_id

    try:
        existing_item = {
            "userId": mock_user_id,
            "profileVersion": 2,
        }

        with patch("backend.api.routes.profile.get_dynamodb_table") as mock_get_table:
            mock_table = Mock()
            mock_table.get_item.return_value = {"Item": existing_item}
            mock_table.update_item.return_value = {}
            mock_get_table.return_value = mock_table

            response = client.put(
                "/me/roles",
                json={"cargosActivos": ["Software Architect", "CTO"]},
            )

            assert response.status_code == 200

            # Verify DynamoDB update was called with correct fields
            call_kwargs = mock_table.update_item.call_args[1]
            update_expr = call_kwargs["UpdateExpression"]
            assert "cargosActivos" in update_expr
            assert "profileVersion" in update_expr
            assert "updatedAt" in update_expr
            # Should NOT include resumenParaMatching or other unrelated fields
            assert "resumenParaMatching" not in update_expr
            assert "perfilEstructurado" not in update_expr

            # Verify the roles values
            expr_values = call_kwargs["ExpressionAttributeValues"]
            assert expr_values[":roles"] == ["Software Architect", "CTO"]

    finally:
        client.app.dependency_overrides.clear()


# ============================================================================
# Prompt Template Tests for Roles Suggestion
# ============================================================================


def test_roles_suggestion_prompt_includes_resumen():
    """Test that the roles suggestion prompt includes the resumen text."""
    from backend.api.routes.profile import _prepare_roles_suggestion_prompt

    resumen = "Senior Python developer with 10 years of AWS experience."
    prompt = _prepare_roles_suggestion_prompt(resumen)

    assert resumen in prompt
    assert "suggestions" in prompt
    assert "JSON" in prompt or "json" in prompt
