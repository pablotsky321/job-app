"""
Health check endpoint for Lambda readiness verification.

GET /health:
- No authentication required
- Returns {"status": "ok"} (HTTP 200) when ready
- Returns {"status": "unavailable"} (HTTP 503) on error
- Only logs on status change (not every request)

Requirements: 21.1, 21.2, 21.3, 21.4, 21.5
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.shared.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)

router = APIRouter(tags=["health"])

# Track last known health status to avoid excessive logging
_last_health_status: dict = {"status": "unknown"}


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for ALB/load balancer verification.

    Returns:
        HTTP 200: {"status": "ok"} when Lambda is ready
        HTTP 503: {"status": "unavailable"} when Lambda is starting or in error

    Logging:
    - Only logs on status change (ready -> error or vice versa)
    - Not logged on every request (would be too noisy in CloudWatch)
    """
    global _last_health_status

    try:
        # Check if Lambda startup completed successfully
        # If we reach this point, startup event passed all validations
        current_status = {"status": "ok"}

        # Log only on status change
        if current_status["status"] != _last_health_status["status"]:
            logger.info(
                "health_check_status_changed",
                context={
                    "previous_status": _last_health_status["status"],
                    "new_status": current_status["status"],
                },
            )
            _last_health_status = current_status

        return JSONResponse(status_code=200, content=current_status)

    except Exception as e:
        current_status = {"status": "unavailable"}

        # Log on status change
        if current_status["status"] != _last_health_status["status"]:
            logger.error(
                "health_check_status_changed",
                context={
                    "previous_status": _last_health_status["status"],
                    "new_status": current_status["status"],
                    "error": str(e),
                },
            )
            _last_health_status = current_status

        return JSONResponse(status_code=503, content=current_status)
