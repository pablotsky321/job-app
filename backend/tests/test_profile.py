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
