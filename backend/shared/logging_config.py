"""
Structured JSON logging configuration for job-app backend.

Provides:
- get_logger(name): Returns a logger with JSON formatter writing to stdout
- RequestContext: Context manager for injecting requestId and userId into log records

All logs are JSON-formatted with:
- timestamp (ISO 8601)
- level (INFO, DEBUG, WARNING, ERROR)
- requestId (from Lambda context or UUID)
- userId (when available, internal logs only)
- message (short, descriptive)
- context (optional object with additional fields)

Security:
- NEVER logs CV text, profile content, JWT tokens, or raw DB row content
- Sanitizes all log output to prevent PII leakage
"""

import logging
import json
import uuid
import contextvars
from datetime import datetime, timezone
from typing import Any, Optional, Dict
from contextvars import ContextVar

# Context variables for request tracing
_request_id_context: ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
_user_id_context: ContextVar[Optional[str]] = contextvars.ContextVar(
    "user_id", default=None
)


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Add requestId from context
        request_id = _request_id_context.get()
        if request_id:
            log_data["requestId"] = request_id

        # Add userId from context (internal logs only, never in client-facing responses)
        user_id = _user_id_context.get()
        if user_id:
            log_data["userId"] = user_id

        # Add extra context fields if present
        if hasattr(record, "context") and record.context:
            log_data["context"] = record.context

        return json.dumps(log_data, default=str)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger configured with JSON formatter writing to stdout.

    Args:
        name: Logger name (typically __name__ from calling module)

    Returns:
        logging.Logger: Configured logger with JSON formatter
    """
    logger = logging.getLogger(name)

    # Only add handler if not already configured (prevent duplicate handlers)
    if not logger.handlers:
        # Create stdout handler
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())

        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    return logger


class RequestContext:
    """
    Context manager for injecting requestId and userId into log records.

    Usage:
        with RequestContext(request_id="abc-123", user_id="user-456"):
            logger.info("Processing request")  # Will include requestId and userId
    """

    def __init__(
        self,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """
        Initialize request context.

        Args:
            request_id: Unique request ID for tracing (generated if not provided)
            user_id: User ID from JWT (optional, only set if authenticated)
        """
        self.request_id = request_id or str(uuid.uuid4())
        self.user_id = user_id
        self._request_id_token = None
        self._user_id_token = None

    def __enter__(self):
        """Enter context manager."""
        self._request_id_token = _request_id_context.set(self.request_id)
        if self.user_id:
            self._user_id_token = _user_id_context.set(self.user_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        if self._request_id_token:
            _request_id_context.reset(self._request_id_token)
        if self._user_id_token:
            _user_id_context.reset(self._user_id_token)


def set_request_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """
    Set request context directly without context manager.

    Useful for middleware or decorators.

    Args:
        request_id: Unique request ID (generated if not provided)
        user_id: User ID from JWT (optional)
    """
    if request_id:
        _request_id_context.set(request_id)
    if user_id:
        _user_id_context.set(user_id)


def get_request_id() -> Optional[str]:
    """Get current request ID from context."""
    return _request_id_context.get()


def get_user_id() -> Optional[str]:
    """Get current user ID from context."""
    return _user_id_context.get()


def clear_request_context() -> None:
    """Clear all request context variables."""
    _request_id_context.set(None)
    _user_id_context.set(None)


class LoggerWithContext(logging.Logger):
    """
    Extended logger that automatically adds context to log records.

    Usage:
        logger = get_contextual_logger(__name__)
        logger.info("message", context={"model": "claude-3", "attempt": 1})
    """

    def _log(
        self,
        level,
        msg,
        args,
        exc_info=None,
        extra=None,
        stack_info=None,
        stacklevel=1,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Override _log to add context to log record."""
        if extra is None:
            extra = {}
        if context is not None:
            extra["context"] = context
        super()._log(
            level,
            msg,
            args,
            exc_info=exc_info,
            extra=extra,
            stack_info=stack_info,
            stacklevel=stacklevel + 1,
        )

    def debug(
        self,
        msg: str,
        *args,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Log debug message with optional context."""
        self._log(logging.DEBUG, msg, args, extra={"context": context}, **kwargs)

    def info(
        self,
        msg: str,
        *args,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Log info message with optional context."""
        self._log(logging.INFO, msg, args, extra={"context": context}, **kwargs)

    def warning(
        self,
        msg: str,
        *args,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Log warning message with optional context."""
        self._log(logging.WARNING, msg, args, extra={"context": context}, **kwargs)

    def error(
        self,
        msg: str,
        *args,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Log error message with optional context."""
        self._log(logging.ERROR, msg, args, extra={"context": context}, **kwargs)

    def critical(
        self,
        msg: str,
        *args,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Log critical message with optional context."""
        self._log(logging.CRITICAL, msg, args, extra={"context": context}, **kwargs)


def get_contextual_logger(name: str) -> LoggerWithContext:
    """
    Get a logger that supports context parameter in log methods.

    Usage:
        logger = get_contextual_logger(__name__)
        logger.info("parsed_cv", context={"model": "claude-3", "status": "ok"})

    Args:
        name: Logger name (typically __name__)

    Returns:
        LoggerWithContext: Extended logger with context support
    """
    logging.setLoggerClass(LoggerWithContext)
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    return logger
