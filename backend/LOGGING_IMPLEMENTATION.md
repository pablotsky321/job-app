# Structured JSON Logging Implementation

## Overview

Task 1.3 implements structured JSON logging for the job-app backend as specified in Requirements 14.1-14.7.

## Files Created

### 1. `backend/shared/logging_config.py`
Main logging configuration module with the following components:

#### Classes
- **`JSONFormatter`**: Custom logging formatter that outputs JSON to stdout
  - Includes timestamp (ISO 8601 format with Z suffix)
  - Includes log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Includes requestId and userId from context (when available)
  - Includes optional context object with additional fields
  - Automatically converts timestamps to ISO 8601 format

- **`RequestContext`**: Context manager for injecting requestId and userId
  - Auto-generates requestId if not provided (UUID format)
  - Optionally accepts userId from JWT claims
  - Injects values into all log records within the context
  - Cleans up context variables on exit
  - Supports nested contexts

- **`LoggerWithContext`**: Extended logger supporting context parameter
  - All standard log methods accept optional `context` parameter
  - Automatically adds context dict to log records

#### Functions
- **`get_logger(name)`**: Factory function returning configured logger with JSON formatter
  - Returns standard `logging.Logger` instance
  - Single handler per logger (no duplication)
  - Suitable for most use cases

- **`get_contextual_logger(name)`**: Factory function returning `LoggerWithContext`
  - Returns logger that supports context parameter in all log methods
  - Suitable for logging with structured context data

- **`set_request_context(request_id, user_id)`**: Direct context setting
  - Alternative to RequestContext manager (for middleware/decorators)
  - Supports partial arguments

- **`get_request_id()` / `get_user_id()`**: Context retrieval functions
  - Returns current values from context variables

- **`clear_request_context()`**: Clear all context variables
  - Useful for cleanup between requests

### 2. `backend/tests/test_logging_config.py`
Comprehensive test suite with 32 test cases covering:

#### JSONFormatter Tests (11 tests)
- Valid JSON output
- Required fields (timestamp, level, message)
- Optional fields (requestId, userId)
- All log level support (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- ISO 8601 timestamp format validation

#### RequestContext Tests (7 tests)
- Setting requestId and userId
- Auto-generation of requestId
- Injection into log records
- Context cleanup after exit
- Optional userId handling
- Nested contexts

#### Logger Factory Tests (4 tests)
- Logger instance creation
- JSON formatter configuration
- Handler management (no duplication)
- Logger identity preservation

#### Contextual Logger Tests (2 tests)
- Context parameter support
- All log method variants support context

#### Context Management Tests (3 tests)
- Direct context setting
- Partial argument handling
- Complete context clearing

#### Security Tests (2 tests)
- Safe text logging
- Caller responsibility for PII (sanitization reminder)

#### Log Format Tests (3 tests)
- Multiple log records on separate lines
- String formatting support
- ISO 8601 with Z format validation

## Usage Examples

### Basic Logging
```python
from backend.shared.logging_config import get_logger

logger = get_logger(__name__)
logger.info("User profile saved")
logger.error("Failed to parse CV")
```

### Logging with Request Context
```python
from backend.shared.logging_config import get_logger, RequestContext

logger = get_logger(__name__)

with RequestContext(request_id="abc-123", user_id="user-456"):
    logger.info("Processing profile")  # Will include requestId and userId
```

### Logging with Context Data
```python
from backend.shared.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)
logger.info(
    "Bedrock invocation completed",
    context={
        "model": "claude-3-haiku",
        "attempt": 1,
        "status": "success",
        "tokens": 150
    }
)
```

### In FastAPI Middleware
```python
from backend.shared.logging_config import set_request_context, clear_request_context

@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id")
    set_request_context(request_id=request_id)
    try:
        response = await call_next(request)
        return response
    finally:
        clear_request_context()
```

## Log Output Format

All logs are emitted as JSON to stdout with the following structure:

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "requestId": "abc-123",
  "userId": "user-456",
  "message": "Profile saved successfully",
  "context": {
    "profileVersion": 2,
    "previousVersion": 1
  }
}
```

Fields:
- **timestamp**: ISO 8601 format with Z suffix (UTC)
- **level**: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **requestId**: Optional, from context (for tracing)
- **userId**: Optional, from context (for debugging)
- **message**: Log message
- **context**: Optional, additional structured data

## Requirements Compliance

### Requirement 14.1 - All Logging as JSON
✅ Implemented via `JSONFormatter` to stdout

### Requirement 14.2 - Required Fields
✅ Includes timestamp (ISO 8601), level, requestId (optional), userId (optional), message, context

### Requirement 14.3 - No Sensitive Data
✅ No logging of CV text, profile content, JWT tokens, or DB row content
   (Responsibility shared between logger and caller)

### Requirement 14.4 - Python logging Module
✅ Uses standard `logging` module with custom JSON formatter

### Requirement 14.7 - userId and requestId
✅ Both fields included in all internal logs when available

## Context Variables

Uses Python's `contextvars` module for thread-safe context management:
- `_request_id_context`: Stores request ID
- `_user_id_context`: Stores user ID

## Testing

All 32 tests pass successfully:
```
============================= test session starts =============================
...
============================== 32 passed in 0.11s ==============================
```

Run tests with:
```bash
pytest backend/tests/test_logging_config.py -v
```

## Security Considerations

1. **PII Protection**: The logger itself doesn't filter sensitive data. It's the caller's responsibility to avoid passing sensitive information (CV text, tokens, etc.) to log methods.

2. **Context Variables**: Using `contextvars` ensures thread-safe context management even in async environments.

3. **No Secrets**: Model IDs, table names, and other configuration are logged by their values (not sensitive), but actual secrets are never logged.

4. **CloudWatch Integration**: JSON format integrates seamlessly with CloudWatch Logs Insights for querying and analytics.

## Performance

- Minimal overhead: Simple JSON serialization
- No I/O blocking: Writes to stdout (handled by Lambda runtime)
- Memory efficient: No buffering, direct streaming

## Dependencies

- Python 3.12 standard library (`logging`, `json`, `contextvars`, `datetime`, `uuid`)
- No external dependencies required (python-json-logger not used; native JSON serialization)

## Integration Points

This module will be integrated with:

1. **FastAPI middleware** - for request/response tracing
2. **Bedrock client** (`backend/shared/bedrock.py`) - for AI invocation logging
3. **Database helpers** (`backend/shared/db.py`) - for DynamoDB operation logging
4. **Route handlers** (`backend/api/routes/*`) - for endpoint logging

## Future Enhancements

Potential future improvements (not in MVP scope):
- Log sampling for high-volume endpoints
- Structured error tracking with error codes
- Request/response payload sampling (with PII redaction)
- Custom context filters for specific domains
- OpenTelemetry integration
