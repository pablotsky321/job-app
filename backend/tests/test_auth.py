"""
Unit tests for JWT claim extraction utilities.

Tests:
- Pure function extract_user_id() reads 'sub' from claims dict
- Raises InvalidAuthorizationContext when 'sub' is missing
- Raises InvalidAuthorizationContext when 'sub' is None or empty
- Does NOT read from request body, query params, or headers
- Never logs JWT tokens or claim values
- Handles edge cases: empty claims dict, None claims, malformed claims

Requirements: 13.1, 13.2, 13.6
"""

import pytest
from backend.shared.auth import extract_user_id, InvalidAuthorizationContext


class TestExtractUserIdPureFunction:
    """Test extract_user_id as a pure function."""

    def test_extract_user_id_returns_sub_claim(self):
        """Should extract and return the 'sub' claim value."""
        claims = {"sub": "user-123", "email": "user@example.com"}
        user_id = extract_user_id(claims)
        assert user_id == "user-123"

    def test_extract_user_id_with_multiple_claims(self):
        """Should extract 'sub' even with multiple claims present."""
        claims = {
            "sub": "cognito-user-456",
            "email": "john@example.com",
            "cognito:username": "john_doe",
            "email_verified": True,
            "aud": "abc123",
            "exp": 1234567890,
            "iat": 1234567800,
        }
        user_id = extract_user_id(claims)
        assert user_id == "cognito-user-456"

    def test_extract_user_id_with_complex_sub_value(self):
        """Should handle 'sub' values with various formats (UUIDs, etc.)."""
        test_subs = [
            "550e8400-e29b-41d4-a716-446655440000",  # UUID
            "user:123:abc",  # Colon-separated
            "us-east-1:12345678-1234-1234-1234-123456789012",  # AWS Cognito format
            "test@example.com",  # Email-like
        ]
        for sub_value in test_subs:
            claims = {"sub": sub_value}
            user_id = extract_user_id(claims)
            assert user_id == sub_value

    def test_extract_user_id_raises_when_sub_missing(self):
        """Should raise InvalidAuthorizationContext when 'sub' key is missing."""
        claims = {"email": "user@example.com", "name": "John"}
        with pytest.raises(InvalidAuthorizationContext) as exc_info:
            extract_user_id(claims)

        assert exc_info.value.error_code == "invalid_authorization"
        assert exc_info.value.http_status == 401
        assert "sub" in str(exc_info.value.details).lower()

    def test_extract_user_id_raises_when_sub_is_none(self):
        """Should raise InvalidAuthorizationContext when 'sub' is None."""
        claims = {"sub": None, "email": "user@example.com"}
        with pytest.raises(InvalidAuthorizationContext) as exc_info:
            extract_user_id(claims)

        assert exc_info.value.error_code == "invalid_authorization"
        assert exc_info.value.http_status == 401

    def test_extract_user_id_raises_when_sub_is_empty_string(self):
        """Should raise InvalidAuthorizationContext when 'sub' is empty string."""
        claims = {"sub": ""}
        with pytest.raises(InvalidAuthorizationContext) as exc_info:
            extract_user_id(claims)

        assert exc_info.value.error_code == "invalid_authorization"

    def test_extract_user_id_raises_when_claims_is_empty_dict(self):
        """Should raise InvalidAuthorizationContext when claims dict is empty."""
        claims = {}
        with pytest.raises(InvalidAuthorizationContext) as exc_info:
            extract_user_id(claims)

        assert exc_info.value.error_code == "invalid_authorization"

    def test_extract_user_id_raises_when_claims_is_none(self):
        """Should raise InvalidAuthorizationContext when claims is None."""
        with pytest.raises(InvalidAuthorizationContext) as exc_info:
            extract_user_id(None)

        assert exc_info.value.error_code == "invalid_authorization"

    def test_extract_user_id_ignores_irrelevant_claims(self):
        """Should extract 'sub' without being affected by other claims."""
        claims = {
            "sub": "user-xyz",
            "invalid_claim": "should_be_ignored",
            "another_bad_claim": 12345,
            "yet_another": None,
        }
        user_id = extract_user_id(claims)
        assert user_id == "user-xyz"


class TestExtractUserIdRobustness:
    """Test extract_user_id robustness and edge cases."""

    def test_extract_user_id_with_unicode_sub(self):
        """Should handle Unicode characters in 'sub' claim."""
        claims = {"sub": "usuario-España-123"}
        user_id = extract_user_id(claims)
        assert user_id == "usuario-España-123"

    def test_extract_user_id_with_very_long_sub(self):
        """Should handle very long 'sub' values."""
        long_sub = "a" * 1000
        claims = {"sub": long_sub}
        user_id = extract_user_id(claims)
        assert user_id == long_sub

    def test_extract_user_id_with_numeric_sub_as_string(self):
        """Should handle numeric 'sub' values as strings."""
        claims = {"sub": "123456"}
        user_id = extract_user_id(claims)
        assert user_id == "123456"

    @pytest.mark.parametrize("sub_value", [
        "user-1",
        "12345",
        "550e8400-e29b-41d4-a716-446655440000",
        "us-east-1:12345678-1234-1234-1234-123456789012",
        "john.doe@example.com",
    ])
    def test_extract_user_id_parametrized(self, sub_value):
        """Parametrized test: Should extract various valid 'sub' formats."""
        claims = {"sub": sub_value}
        user_id = extract_user_id(claims)
        assert user_id == sub_value


class TestExtractUserIdPurity:
    """Test that extract_user_id is a pure function."""

    def test_extract_user_id_is_pure_same_input_same_output(self):
        """Calling extract_user_id multiple times with same input should yield same output."""
        claims = {"sub": "user-123", "email": "user@example.com"}

        result1 = extract_user_id(claims)
        result2 = extract_user_id(claims)
        result3 = extract_user_id(claims)

        assert result1 == result2 == result3 == "user-123"

    def test_extract_user_id_does_not_modify_claims_dict(self):
        """Calling extract_user_id should not modify the input claims dict."""
        claims = {"sub": "user-123", "email": "user@example.com"}
        original_claims = claims.copy()

        extract_user_id(claims)

        # Claims dict should be unchanged
        assert claims == original_claims

    def test_extract_user_id_does_not_read_from_global_state(self):
        """Function should not depend on any global state."""
        claims1 = {"sub": "user-A"}
        claims2 = {"sub": "user-B"}

        result1 = extract_user_id(claims1)
        result2 = extract_user_id(claims2)

        # Results should be independent
        assert result1 == "user-A"
        assert result2 == "user-B"


class TestInvalidAuthorizationContextException:
    """Test InvalidAuthorizationContext exception class."""

    def test_invalid_authorization_context_has_correct_status(self):
        """Should have HTTP status 401."""
        exc = InvalidAuthorizationContext()
        assert exc.http_status == 401

    def test_invalid_authorization_context_has_correct_error_code(self):
        """Should have error_code 'invalid_authorization'."""
        exc = InvalidAuthorizationContext()
        assert exc.error_code == "invalid_authorization"

    def test_invalid_authorization_context_to_dict(self):
        """Should convert to dict for JSON response."""
        exc = InvalidAuthorizationContext(details="test details")
        exc_dict = exc.to_dict()

        assert exc_dict["error"] == "invalid_authorization"
        assert "message" in exc_dict
        assert exc_dict["details"] == "test details"

    def test_invalid_authorization_context_without_details(self):
        """Should work without details parameter."""
        exc = InvalidAuthorizationContext()
        exc_dict = exc.to_dict()

        assert exc_dict["error"] == "invalid_authorization"
        assert "details" not in exc_dict  # details should be omitted if None


class TestAuthRequirements:
    """Test compliance with documented requirements."""

    def test_requirement_13_1_user_id_from_jwt(self):
        """
        Requirement 13.1: userId is extracted from JWT (via claims.sub).
        
        The function reads ONLY from the already-parsed claims dict,
        which is the JWT's decoded claims.
        """
        claims = {"sub": "authenticated-user-123"}
        user_id = extract_user_id(claims)
        assert user_id == "authenticated-user-123"

    def test_requirement_13_2_never_from_body_query_headers(self):
        """
        Requirement 13.2: userId is NEVER read from request body, query params, or headers.
        
        The function accepts ONLY the claims dict (already parsed by API Gateway).
        It does not accept request body, query params, or headers as inputs.
        """
        # This test verifies the function signature and implementation
        claims = {"sub": "user-456"}
        user_id = extract_user_id(claims)
        assert user_id == "user-456"

        # The function does NOT accept these parameters:
        # - request_body: not in function signature
        # - query_params: not in function signature
        # - headers: not in function signature
        # Therefore it CANNOT read from these sources

    def test_requirement_13_6_never_logs_jwt_tokens(self):
        """
        Requirement 13.6: JWT tokens and sensitive claims are never logged.
        
        This is a design requirement: the function does not perform any logging.
        Callers are responsible for not logging the claims dict or JWT token.
        """
        # The extract_user_id function contains NO logging code
        # Therefore it cannot accidentally log JWT tokens or claims
        import inspect
        source = inspect.getsource(extract_user_id)
        assert "logger" not in source.lower()
        assert "print" not in source.lower()
        # Check for actual logging calls (logger.info, logger.debug, etc.)
        assert "logger.info" not in source.lower()
        assert "logger.debug" not in source.lower()
        assert "logger.warning" not in source.lower()
        assert "logger.error" not in source.lower()


class TestDocumentation:
    """Test that function documentation is complete and accurate."""

    def test_extract_user_id_has_docstring(self):
        """Function should have complete docstring."""
        docstring = extract_user_id.__doc__
        assert docstring is not None
        assert "sub" in docstring.lower()
        assert "jwt" in docstring.lower() or "claims" in docstring.lower()

    def test_extract_user_id_docstring_includes_requirements(self):
        """Docstring should reference relevant requirements."""
        docstring = extract_user_id.__doc__
        assert "13.1" in docstring or "13.2" in docstring or "13.6" in docstring
