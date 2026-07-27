"""
JWT extraction and authorization utilities for FastAPI routes.

Provides:
- get_current_user_id() FastAPI dependency for extracting authenticated userId
  from Lambda/Mangum scope (event.requestContext.authorizer.claims.sub)
- Works as a FastAPI dependency using Depends() for routes requiring authentication

Usage:
    @router.get("/me/profile")
    async def get_profile(user_id: str = Depends(get_current_user_id)):
        # user_id is now safely extracted from JWT
        ...

Requirements: 13.1, 13.3
"""

from typing import Optional
from fastapi import Request, Depends
from backend.shared.auth import extract_user_id, InvalidAuthorizationContext
from backend.shared.errors import AppException
from backend.shared.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)


def get_current_user_id(request: Request) -> str:
    """
    FastAPI dependency that extracts userId from JWT authorizer claims.

    Reads from event.requestContext.authorizer.claims.sub (Cognito JWT token
    set by API Gateway Cognito Authorizer) via the Mangum ASGI adapter.

    This dependency:
    - Extracts userId from JWT claims.sub (never from body/query params)
    - Works as a FastAPI Depends() parameter for routes requiring authentication
    - Raises InvalidAuthorizationContext (HTTP 401) if claims are missing/invalid
    - Never logs JWT token values or sensitive claims

    Args:
        request: FastAPI Request object containing Lambda scope

    Returns:
        str: The authenticated userId from JWT claims.sub

    Raises:
        InvalidAuthorizationContext (HTTP 401): If JWT claims are missing or
            'sub' claim is absent. API Gateway typically prevents this by
            rejecting invalid JWTs before the Lambda is invoked, but we validate
            for robustness.

    Example:
        # In a route handler:
        @router.get("/me/profile")
        async def get_profile(user_id: str = Depends(get_current_user_id)):
            # user_id is safely extracted from JWT and ready to use
            # for DynamoDB queries, logging, etc.
            ...

    Requirements:
        - 13.1: userId extracted from JWT (event.requestContext.authorizer.claims.sub)
        - 13.3: Works as a FastAPI dependency for routes requiring authentication
    """
    try:
        # Access Lambda scope from Mangum via request.scope
        # Scope structure:
        # {
        #   "type": "http",
        #   "asgi": {...},
        #   ...
        #   "aws.event": {...},  # Raw Lambda event
        # }
        #
        # When using Mangum with API Gateway (Cognito Authorizer):
        # request.scope["aws.event"]["requestContext"]["authorizer"]["claims"]
        # = {"sub": "user-123", "email": "...", ...}

        # Get the raw Lambda event from scope
        aws_event: Optional[dict] = request.scope.get("aws.event")

        if not aws_event:
            # Fallback: try to get from request.scope directly (in case of different
            # Mangum/ASGI setup)
            claims = request.scope.get("authorizer", {}).get("claims", {})
        else:
            # Standard Lambda + Mangum + API Gateway Cognito Authorizer
            try:
                request_context = aws_event.get("requestContext", {})
                authorizer = request_context.get("authorizer", {})
                claims = authorizer.get("claims", {})
            except (AttributeError, TypeError):
                claims = {}

        # Extract userId from claims using shared auth module
        user_id = extract_user_id(claims)

        logger.debug(
            "jwt_extraction_success",
            context={"user_id_extracted": True},
        )

        return user_id

    except InvalidAuthorizationContext as e:
        # Log the failure (without exposing JWT/sensitive values)
        logger.warning(
            "jwt_extraction_failed",
            context={"error": e.error_code, "details": e.details},
        )
        # Re-raise to let FastAPI exception handler convert to HTTP 401
        raise AppException(
            error_code=e.error_code,
            message=e.message,
            http_status=e.http_status,
            details=e.details,
        ) from e

    except Exception as e:
        # Unexpected error (shouldn't happen with well-formed AWS event)
        logger.error(
            "jwt_extraction_unexpected_error",
            context={"error": str(e), "error_type": type(e).__name__},
        )
        raise InvalidAuthorizationContext(
            details=f"Unexpected error during JWT extraction: {type(e).__name__}"
        ) from e
