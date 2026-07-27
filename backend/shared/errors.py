"""
Custom exception classes with HTTP status code mapping.

Each exception carries:
- error_code (str): machine-readable error identifier
- message (str): human-readable message
- details (Optional[str]): optional extra information
- http_status (int): HTTP status code for mapping to responses

Requirements: 15.1, 15.2, 15.3
"""

from typing import Optional


class AppException(Exception):
    """
    Base exception class for all application-level errors.
    
    Attributes:
        error_code: Machine-readable error identifier (e.g., 'validation_error')
        message: Human-readable error message
        details: Optional extra information for debugging/client context
        http_status: HTTP status code for this error
    """
    
    def __init__(
        self,
        error_code: str,
        message: str,
        http_status: int,
        details: Optional[str] = None
    ):
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        self.details = details
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        """
        Convert exception to dict for JSON response.
        
        Returns:
            Dict with error_code, message, and optional details
        """
        response = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            response["details"] = self.details
        return response


class ValidationError(AppException):
    """
    HTTP 400: Input validation failed (schema mismatch, invalid format).
    
    Args:
        message: Human-readable validation error
        details: Optional specific field/constraint info
    """
    
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(
            error_code="validation_error",
            message=message,
            http_status=400,
            details=details
        )


class ProfileNotFound(AppException):
    """
    HTTP 404: User's profile does not exist.
    
    Args:
        details: Optional additional context
    """
    
    def __init__(self, details: Optional[str] = None):
        super().__init__(
            error_code="profile_not_found",
            message="User profile not found",
            http_status=404,
            details=details
        )


class AIServiceUnavailable(AppException):
    """
    HTTP 502: Bedrock invocation failed, network error, or timeout.
    
    Args:
        message: Human-readable error (e.g., 'Bedrock request timed out')
        details: Optional technical details (model ID, region, underlying error)
    """
    
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(
            error_code="ai_service_unavailable",
            message=message,
            http_status=502,
            details=details
        )


class PlatformDetectionFailed(AppException):
    """
    HTTP 400: URL parsing failed (malformed URL, missing scheme/hostname).
    
    Args:
        details: Optional details about the malformed URL
    """
    
    def __init__(self, details: Optional[str] = None):
        super().__init__(
            error_code="platform_detection_failed",
            message="Platform detection failed due to malformed URL",
            http_status=400,
            details=details
        )


class ResumeNotReady(AppException):
    """
    HTTP 424: Dependency failed - resumen generation in progress or not exists.
    
    Args:
        details: Optional context (e.g., 'Resumen generation in progress')
    """
    
    def __init__(self, details: Optional[str] = None):
        super().__init__(
            error_code="resume_not_ready",
            message="Resume not ready for suggestions",
            http_status=424,
            details=details
        )


class SubscriptionNotFound(AppException):
    """
    HTTP 404: User's subscription for a company does not exist.
    
    Args:
        details: Optional additional context
    """
    
    def __init__(self, details: Optional[str] = None):
        super().__init__(
            error_code="subscription_not_found",
            message="Subscription not found",
            http_status=404,
            details=details
        )


class CompanyAlreadyExists(AppException):
    """
    HTTP 409: Company URL already exists in the catalog (duplicate).
    
    Args:
        company_id: The SHA-256 hash (companyId) that already exists
        details: Optional additional context
    """
    
    def __init__(self, company_id: str, details: Optional[str] = None):
        if not details:
            details = f"Company with ID {company_id} already exists"
        super().__init__(
            error_code="company_already_exists",
            message="Company already exists in catalog",
            http_status=409,
            details=details
        )
        self.company_id = company_id


class CompanyNotFound(AppException):
    """
    HTTP 400: Company ID does not exist in the Empresas table.
    
    Args:
        company_id: The companyId that was not found
        details: Optional additional context
    """
    
    def __init__(self, company_id: str, details: Optional[str] = None):
        if not details:
            details = f"Company with ID {company_id} not found"
        super().__init__(
            error_code="company_not_found",
            message="Company not found",
            http_status=400,
            details=details
        )
        self.company_id = company_id


class CVTooLarge(AppException):
    """
    HTTP 413: CV text exceeds size limit (>50KB).
    
    Args:
        max_size_kb: Maximum allowed size in KB
        actual_size_kb: Actual size in KB
    """
    
    def __init__(self, max_size_kb: int = 50, actual_size_kb: Optional[int] = None):
        details = f"CV exceeds {max_size_kb}KB limit"
        if actual_size_kb is not None:
            details += f" (actual: {actual_size_kb}KB)"
        super().__init__(
            error_code="payload_too_large",
            message="CV text too large",
            http_status=413,
            details=details
        )
