"""
JWT claim extraction utilities.

Pure functions to extract authenticated user information from Cognito JWT claims.
Designed for use with Lambda + API Gateway Cognito Authorizer.

Requirements: 13.1, 13.2, 13.6
"""

from typing import Any, Dict, Optional
from backend.shared.errors import AppException


class InvalidAuthorizationContext(AppException):
    """
    HTTP 401: JWT validation failed or claims are missing/malformed.
    
    This exception is raised only if the Lambda receives invalid auth claims
    (which typically indicates API Gateway misconfiguration or missing authorizer).
    """
    
    def __init__(self, details: Optional[str] = None):
        super().__init__(
            error_code="invalid_authorization",
            message="Authorization context is invalid or missing required claims",
            http_status=401,
            details=details
        )


def extract_user_id(claims: Dict[str, Any]) -> str:
    """
    Extract userId from Cognito JWT claims.
    
    Reads the 'sub' (subject) claim from an already-parsed JWT claims mapping.
    This is a pure function that operates only on the parsed claims dict —
    it does NOT read from request body, query params, headers, or JWT tokens.
    
    Args:
        claims: Dict of JWT claims from event.requestContext.authorizer.claims.
                This is already parsed by API Gateway Cognito Authorizer.
    
    Returns:
        str: The userId (value of the 'sub' claim).
    
    Raises:
        InvalidAuthorizationContext: If the 'sub' claim is missing or None.
    
    Example:
        >>> claims = {"sub": "user-123", "email": "user@example.com", "cognito:username": "john"}
        >>> extract_user_id(claims)
        'user-123'
        
        >>> claims = {"email": "user@example.com"}  # 'sub' is missing
        >>> extract_user_id(claims)
        # Raises InvalidAuthorizationContext
    
    Requirements:
        - 13.1: userId is extracted from JWT (via claims.sub)
        - 13.2: userId is NEVER read from request body, query params, or headers
        - 13.6: JWT tokens/sensitive claims are never logged
    """
    if not claims:
        raise InvalidAuthorizationContext(
            details="Claims mapping is empty or None"
        )
    
    user_id = claims.get("sub")
    
    if not user_id:
        raise InvalidAuthorizationContext(
            details="Required 'sub' claim is missing from JWT"
        )
    
    return user_id
