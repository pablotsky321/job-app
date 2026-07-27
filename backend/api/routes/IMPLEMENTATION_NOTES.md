# JWT Extraction Dependency Implementation Notes

## Overview

Task 3.3 implementation: JWT extraction dependency for FastAPI routes.

**File:** `backend/api/routes/auth.py`  
**Requirements:** 13.1, 13.3  
**Dependencies:** 
- `backend/shared/auth.py` - Pure extraction function `extract_user_id(claims)`
- `backend/shared/errors.py` - Custom exceptions
- `backend/shared/logging_config.py` - Structured logging

## Implementation Details

### Function: `get_current_user_id(request: Request) -> str`

**Purpose:** FastAPI dependency that extracts authenticated userId from JWT claims

**How it works:**

1. **Receives:** FastAPI `Request` object containing Lambda/Mangum ASGI scope
2. **Reads:** JWT claims from `event.requestContext.authorizer.claims.sub`
3. **Returns:** userId string for use in route handlers
4. **Errors:** Raises `AppException` (HTTP 401) if claims are missing/invalid

### Integration with FastAPI Routes

**Usage Pattern:**

```python
from fastapi import APIRouter, Depends
from backend.api.routes.auth import get_current_user_id

router = APIRouter()

@router.get("/me/profile")
async def get_profile(user_id: str = Depends(get_current_user_id)):
    # user_id is now safely extracted from JWT
    # e.g., "user-123"
    
    # Can use for DynamoDB queries:
    profile = db.query_profile(user_id)
    
    # Can use for logging:
    logger.info("profile_retrieved", context={"user_id": user_id})
    
    return profile
```

### Technical Details

**Request Scope Structure (Mangum + API Gateway):**

```
request.scope = {
    "type": "http",
    "asgi": {...},
    "method": "GET",
    "path": "/me/profile",
    ...
    "aws.event": {                    # Raw Lambda event
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "user-123",          # JWT subject (userId)
                    "email": "user@example.com",
                    "cognito:username": "john",
                    ...
                }
            }
        }
    }
}
```

**Claim Extraction:**

1. Accesses `request.scope["aws.event"]["requestContext"]["authorizer"]["claims"]`
2. Passes claims dict to `backend.shared.auth.extract_user_id(claims)`
3. `extract_user_id()` returns claims.sub or raises `InvalidAuthorizationContext` (HTTP 401)
4. Converts `InvalidAuthorizationContext` to `AppException` for FastAPI handler

**Fallback Handling:**

If `aws.event` is not present in scope (unlikely in production but possible in different ASGI configurations):
- Tries to read from `request.scope["authorizer"]["claims"]` directly
- Falls back gracefully to avoid crashes

**Error Cases:**

1. **Missing aws.event:** Falls back to alternative scope structure
2. **Missing authorizer/claims:** Raises `InvalidAuthorizationContext` → HTTP 401
3. **Missing sub claim:** Raises `InvalidAuthorizationContext` → HTTP 401
4. **Empty claims dict:** Raises `InvalidAuthorizationContext` → HTTP 401
5. **Malformed structure:** Catches AttributeError/TypeError → HTTP 401
6. **Unexpected errors:** Logs and raises `InvalidAuthorizationContext` → HTTP 401

### Security Properties

✓ userId is ALWAYS read from JWT claims (never from body/query params)  
✓ JWT tokens are NEVER logged (only error codes and details)  
✓ JWT claims are never exposed in responses sent to client  
✓ Invalid/missing authorization results in HTTP 401 (not 400)  
✓ All extraction errors are properly logged for debugging  

### Logging

**Success Case:**
```json
{
  "level": "DEBUG",
  "message": "jwt_extraction_success",
  "context": {"user_id_extracted": true}
}
```

**Failure Case (missing sub):**
```json
{
  "level": "WARNING",
  "message": "jwt_extraction_failed",
  "context": {
    "error": "invalid_authorization",
    "details": "Required 'sub' claim is missing from JWT"
  }
}
```

**Unexpected Error:**
```json
{
  "level": "ERROR",
  "message": "jwt_extraction_unexpected_error",
  "context": {
    "error": "...",
    "error_type": "..."
  }
}
```

## Requirements Coverage

| Requirement | Coverage |
|---|---|
| 13.1 | ✓ Extract userId from event.requestContext.authorizer.claims.sub |
| 13.2 | ✓ Never read userId from body/query params/headers |
| 13.3 | ✓ Works as FastAPI dependency for /me/... routes |
| 13.6 | ✓ Never log JWT tokens or sensitive claims |

## Testing

**Tests File:** `backend/tests/test_auth_dependency.py`

**Test Coverage:**
- Valid JWT extraction from aws.event
- Fallback extraction from scope
- Missing sub claim error handling
- Empty claims error handling
- Missing authorizer context
- Malformed structure handling
- Various userId formats (UUIDs, email, etc.)
- Integration example

**Run Tests:**
```bash
pytest backend/tests/test_auth_dependency.py -v
```

**Result:** 9/9 tests passing ✓

## Next Steps

This dependency is ready to be used in route handlers:

1. **Profile routes** (`backend/api/routes/profile.py`):
   - `GET /me/profile` - requires authenticated user
   - `PUT /me/profile` - requires authenticated user
   - `POST /me/profile/parse` - requires authenticated user
   - etc.

2. **Companies routes** (`backend/api/routes/companies.py`):
   - `GET /me/companies` - requires authenticated user
   - `PUT /me/companies/{companyId}` - requires authenticated user

3. **All endpoints** that access user-specific data should use:
   ```python
   user_id: str = Depends(get_current_user_id)
   ```

## Example Usage in a Route Handler

```python
from fastapi import APIRouter, Depends
from backend.api.routes.auth import get_current_user_id
from backend.shared.db import query_profile
from backend.shared.models import PerfilEstructurado

router = APIRouter()

@router.get("/me/profile", response_model=PerfilEstructurado)
async def get_profile(user_id: str = Depends(get_current_user_id)):
    """
    Get user's profile.
    
    JWT extraction is automatic via the get_current_user_id dependency.
    """
    profile = query_profile(user_id)
    if not profile:
        raise ProfileNotFound()
    return profile
```

## Implementation Status

✅ **Complete and tested**

- [x] Created `backend/api/routes/auth.py`
- [x] Implemented `get_current_user_id()` dependency
- [x] Handles all error cases gracefully
- [x] Integrated with shared auth module
- [x] Proper logging and error handling
- [x] Comprehensive unit tests (9/9 passing)
- [x] Ready for use in route handlers

