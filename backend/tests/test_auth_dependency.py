"""
Unit tests for the JWT extraction FastAPI dependency.

Tests the get_current_user_id() dependency function in isolation,
verifying it correctly extracts userId from Lambda/Mangum scope
and handles error cases appropriately.

Requirements: 13.1, 13.3
"""

import pytest
from unittest.mock import Mock, MagicMock
from fastapi import Request
from backend.api.routes.auth import get_current_user_id
from backend.shared.errors import AppException


class TestGetCurrentUserIdDependency:
    """Tests for the get_current_user_id FastAPI dependency."""

    def test_valid_jwt_extraction_from_aws_event(self):
        """
        Test: Valid JWT claims extraction from request.scope["aws.event"]
        
        When a request contains valid AWS Lambda event with Cognito authorizer claims,
        the dependency should extract and return the userId from claims.sub.
        """
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.scope = {
            "aws.event": {
                "requestContext": {
                    "authorizer": {
                        "claims": {
                            "sub": "user-12345",
                            "email": "user@example.com",
                            "cognito:username": "testuser"
                        }
                    }
                }
            }
        }

        # Act
        user_id = get_current_user_id(mock_request)

        # Assert
        assert user_id == "user-12345"

    def test_jwt_extraction_fallback_scope_structure(self):
        """
        Test: Fallback JWT extraction when aws_event is not in scope
        
        When request.scope doesn't have aws.event key, the dependency should
        attempt to read authorizer.claims directly from scope as a fallback.
        """
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.scope = {
            "authorizer": {
                "claims": {
                    "sub": "fallback-user-456"
                }
            }
        }

        # Act
        user_id = get_current_user_id(mock_request)

        # Assert
        assert user_id == "fallback-user-456"

    def test_missing_sub_claim_raises_error(self):
        """
        Test: Missing 'sub' claim raises AppException with HTTP 401
        
        When the JWT claims don't include the 'sub' claim (or it's None),
        the dependency should raise an AppException with error_code='invalid_authorization'
        and http_status=401.
        """
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.scope = {
            "aws.event": {
                "requestContext": {
                    "authorizer": {
                        "claims": {
                            "email": "user@example.com",
                            # 'sub' is missing
                        }
                    }
                }
            }
        }

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            get_current_user_id(mock_request)
        
        assert exc_info.value.error_code == "invalid_authorization"
        assert exc_info.value.http_status == 401

    def test_empty_claims_dict_raises_error(self):
        """
        Test: Empty claims dict raises AppException
        
        When the claims dict is empty (no 'sub' claim),
        the dependency should raise an AppException.
        """
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.scope = {
            "aws.event": {
                "requestContext": {
                    "authorizer": {
                        "claims": {}
                    }
                }
            }
        }

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            get_current_user_id(mock_request)
        
        assert exc_info.value.error_code == "invalid_authorization"
        assert exc_info.value.http_status == 401

    def test_missing_authorizer_context_raises_error(self):
        """
        Test: Missing authorizer context raises AppException
        
        When the requestContext doesn't have an authorizer key,
        the dependency should raise an AppException.
        """
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.scope = {
            "aws.event": {
                "requestContext": {
                    # Missing 'authorizer' key
                }
            }
        }

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            get_current_user_id(mock_request)
        
        assert exc_info.value.error_code == "invalid_authorization"
        assert exc_info.value.http_status == 401

    def test_malformed_aws_event_structure_handled_gracefully(self):
        """
        Test: Malformed AWS event structure is handled gracefully
        
        When the AWS event has an unexpected structure (e.g., requestContext
        is a list instead of dict), the dependency should raise an AppException
        without crashing on type errors.
        """
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.scope = {
            "aws.event": {
                "requestContext": []  # Malformed: list instead of dict
            }
        }

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            get_current_user_id(mock_request)
        
        assert exc_info.value.error_code == "invalid_authorization"
        assert exc_info.value.http_status == 401

    def test_no_aws_event_in_scope_tries_fallback(self):
        """
        Test: When aws.event is missing, dependency tries fallback path
        
        When request.scope doesn't have "aws.event" key, the dependency
        should fall back to looking for claims in scope["authorizer"]["claims"].
        """
        # Arrange
        mock_request = Mock(spec=Request)
        mock_request.scope = {
            # No aws.event key
            "type": "http",
            "method": "GET",
        }

        # Act & Assert
        with pytest.raises(AppException) as exc_info:
            get_current_user_id(mock_request)
        
        # Should fail because fallback also won't find claims
        assert exc_info.value.error_code == "invalid_authorization"

    def test_sub_claim_with_various_user_id_formats(self):
        """
        Test: Dependency correctly extracts various userId formats
        
        The 'sub' claim can have various formats (UUIDs, email-like strings, etc.).
        The dependency should return it as-is without modification.
        """
        test_cases = [
            "123e4567-e89b-12d3-a456-426614174000",  # UUID format
            "user@example.com",  # Email format
            "username123",  # Username format
            "a",  # Single character (valid but unusual)
        ]

        for test_user_id in test_cases:
            # Arrange
            mock_request = Mock(spec=Request)
            mock_request.scope = {
                "aws.event": {
                    "requestContext": {
                        "authorizer": {
                            "claims": {
                                "sub": test_user_id
                            }
                        }
                    }
                }
            }

            # Act
            user_id = get_current_user_id(mock_request)

            # Assert
            assert user_id == test_user_id


class TestGetCurrentUserIdIntegration:
    """Integration tests with real FastAPI Request-like objects."""

    def test_dependency_integration_example(self):
        """
        Test: Demonstrates how the dependency integrates with FastAPI routes
        
        This test shows the expected usage pattern:
            @router.get("/me/profile")
            async def get_profile(user_id: str = Depends(get_current_user_id)):
                # user_id is now safely extracted from JWT
                ...
        """
        # In real usage, FastAPI provides a Request object with the ASGI scope
        # already set up by Mangum. We mock this here for demonstration.
        
        mock_request = Mock(spec=Request)
        mock_request.scope = {
            "aws.event": {
                "requestContext": {
                    "authorizer": {
                        "claims": {
                            "sub": "authenticated-user-789"
                        }
                    }
                }
            }
        }

        # This simulates what happens when FastAPI injects the dependency
        user_id = get_current_user_id(mock_request)

        # The route handler now has the authenticated userId
        assert user_id == "authenticated-user-789"
        # This userId can be safely used for:
        # - DynamoDB queries (filter by userId)
        # - Logging (include userId in logs)
        # - Audit trails (record which user performed the action)

