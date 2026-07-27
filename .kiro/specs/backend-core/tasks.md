# Implementation Plan: Backend Core

## Overview

Implementation plan for the monolithic FastAPI + Mangum Lambda backend (Python 3.12). Work proceeds bottom-up: `backend/shared/` modules (models, validators, normalization, db, auth, bedrock, logging, errors) are fully implemented and unit-tested first, since every route depends on them. Only after the shared layer is complete do we build the FastAPI app bootstrap and individual endpoint groups (health → auth extraction → profile parse → profile get/put → roles suggest/put → companies list/add → subscriptions get/put). The Lambda entry point comes after all routes are wired, and the OpenAPI export script is the final task since it depends on the fully assembled FastAPI app. No infrastructure/Terraform tasks are included — this plan covers only `backend/` application code. Test tasks are limited to the pure, dependency-free functions in `validators.py` and `normalization.py`; no boto3/moto/localstack mocking is used anywhere.

## Tasks

- [ ] 1. Shared module foundation
  - [ ] 1.1 Set up backend project structure and dependencies
    - Create `backend/requirements.txt` pinned to: `fastapi==0.104.1`, `mangum==0.26.0`, `pydantic==2.5.0`, `boto3==1.34.0`, `python-json-logger==2.0.7`, `beautifulsoup4==4.12.2`, `python-multipart==0.0.6`
    - Create `backend/pyproject.toml` with project metadata, Python 3.12 requirement, and pytest configuration
    - Create package skeleton: `backend/__init__.py`, `backend/api/__init__.py`, `backend/api/routes/__init__.py`, `backend/api/models/__init__.py`, `backend/shared/__init__.py`, `backend/tests/__init__.py`
    - _Requirements: 22.1, 22.3_

  - [ ] 1.2 Implement custom exception classes
    - Create `backend/shared/errors.py` with `ValidationError` (400), `ProfileNotFound` (404), `AIServiceUnavailable` (502), `PlatformDetectionFailed` (400), `ResumeNotReady` (424), `SubscriptionNotFound` (404), `CompanyAlreadyExists` (409), `CompanyNotFound` (400), `CVTooLarge` (413) — each exception carries an `error_code`, `message`, optional `details`, and HTTP status
    - _Requirements: 15.1, 15.2, 15.3_

  - [ ] 1.3 Implement structured JSON logging
    - Create `backend/shared/logging_config.py` with `get_logger(name)` returning a logger configured with a JSON formatter (via `python-json-logger`) writing to stdout
    - Implement a `RequestContext` context manager/helper that injects `requestId` and `userId` (when available) into every log record emitted within its scope
    - Ensure no helper accepts or logs CV text, profile content, JWT tokens, or raw DB row content
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.7_

  - [ ] 1.4 Implement domain models
    - Create `backend/shared/models.py` as the single source of truth for all Pydantic v2 domain models: `ExperienciaLaboral`, `Educacion`, `Proyecto`, `Certificacion`, `PerfilEstructurado`, `RolesSuggestions`, `Empresa`, `Suscripcion`, `ScanJob`, and the Perfiles table shape (including `resumenParaMatching`, `resumenGenerationStatus`, `cargosSugeridos`, `cargosActivos`, `profileVersion`, `updatedAt`)
    - Apply `ConfigDict(extra="ignore")` to every model for forward compatibility
    - _Requirements: 1.3, 2.2, 2.5, 3.1, 4.6, 5.1, 20.1, 20.3_

  - [ ] 1.5 Implement validators.py pure functions
    - Create `backend/shared/validators.py` with `normalize_url(url)`, `compute_company_id(url)` (SHA-256 hex digest), `detect_platform_hostname_only(url)` (pure hostname check, no network: returns `'greenhouse'` if hostname contains `greenhouse`, `'lever'` if hostname contains `lever`, else `'html'` — never returns `None`; raises on malformed URL — missing scheme or hostname — for the route to map to `platform_detection_failed`), `validate_cv_text(text)`, `validate_roles_list(roles)`, `validate_empresa_url(url)` — all pure, no network/AWS calls
    - _Requirements: 7.2, 7.3, 7.4, 1.1, 1.5, 5.1, 7.1_

  - [ ]* 1.6 Write unit tests for validators.py pure functions
    - Parametrized pytest cases for `normalize_url` (scheme/host lowercasing, fragment removal, trailing slash removal), `compute_company_id` (deterministic 64-char hex output), `detect_platform_hostname_only` (greenhouse match, lever match, fallback to `'html'`, and raises on malformed URL), `validate_cv_text` (empty string, >50KB, valid), `validate_roles_list` (empty list, >10 items, item >50 chars, valid), `validate_empresa_url` (missing scheme, non-http(s), valid)
    - _Requirements: 7.2, 7.3, 7.4, 1.1, 1.5, 5.1, 7.1_

  - [ ] 1.7 Implement normalization.py pure functions
    - Create `backend/shared/normalization.py` with `html_to_clean_text(html)` (BeautifulSoup `html.parser`, strips script/style, preserves block newlines), `normalize_whitespace(text)`, `extract_page_title(html)`, `extract_json_ld(html)` (parses `application/ld+json`, returns dict or `None`), `extract_careers_url_from_html(html, base_url)` (href matching `career`/`job`, resolved via `urljoin`) — no `lxml`, no network calls
    - _Requirements: 7.5_

  - [ ]* 1.8 Write unit tests for normalization.py pure functions
    - Fixture-based HTML strings covering: text extraction with script/style removal, whitespace collapsing, title extraction (present/absent), JSON-LD parsing (valid/missing/malformed), careers URL extraction (relative/absolute/absent)
    - _Requirements: 7.5_

  - [ ] 1.9 Implement DynamoDB access helpers
    - Create `backend/shared/db.py` reading `DYNAMODB_TABLE_EMPRESAS`, `DYNAMODB_TABLE_VACANTES`, `DYNAMODB_TABLE_USUARIO_VACANTE`, `DYNAMODB_TABLE_ENTRADAS`, `DYNAMODB_TABLE_PERFILES`, `DYNAMODB_TABLE_SUSCRIPCIONES`, `DYNAMODB_TABLE_SCAN_JOBS` from environment variables at import time, raising a clear startup error if any is missing
    - Implement `query_by_pk`, `put_item`, `update_item`, `delete_item` helpers as the single access point for all DynamoDB interaction; log operation type, table, key, and row count affected (never content) on every call
    - _Requirements: 16.1, 16.2, 16.3, 16.4_

  - [ ] 1.10 Implement JWT claim extraction helpers
    - Create `backend/shared/auth.py` with a pure function that extracts `userId` from an already-parsed `event.requestContext.authorizer.claims` mapping (`sub` claim), raising a clear error if the claim is absent
    - Ensure no function reads `userId` from body, query params, or headers, and no JWT token value is ever logged
    - _Requirements: 13.1, 13.2, 13.6_

  - [ ] 1.11 Implement Bedrock client module
    - Create `backend/shared/bedrock.py` reading `BEDROCK_REGION`, `BEDROCK_MODEL_SMALL`, `BEDROCK_MODEL_MID` from environment variables (never hardcoded, never read elsewhere)
    - Implement `BedrockClient` with `invoke_with_retry(prompt, response_model, retry_prompt_template)`: parses/validates every response against the given Pydantic model (never raw `json.loads()`), retries at most once on validation failure with the error injected into the prompt, and raises on a second failure
    - Configure boto3 client timeouts `connect_timeout=10`, `read_timeout=20`; on Bedrock-side timeout/error, log and raise without retrying
    - Implement `startup_validation()` sending a trivial "Respond with ok" prompt per configured model with a 2-second timeout, raising a descriptive error (model ID, region, underlying error) on failure
    - Log model ID and region on every invocation, and attempt count on retries
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 12.1, 12.2, 12.3, 12.4, 12.5, 19.1, 19.2, 19.3, 19.4_

- [ ] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Request schemas and API bootstrap
  - [ ] 3.1 Implement request body schemas
    - Create `backend/api/models/requests.py` with `ParseCVRequest` (`cvText: str`), `SaveProfileRequest` (`perfilEstructurado`), `SetRolesRequest` (`cargosActivos: List[str]`), `AddCompanyRequest` (`careersUrl: str`), `ToggleSubscriptionRequest` (`activa: bool`) — request-only schemas, separate from domain models in `shared/models.py`
    - _Requirements: 1.1, 3.1, 5.1, 7.1, 9.1_

  - [ ] 3.2 Implement FastAPI app bootstrap and health check endpoint
    - Create `backend/main.py`: FastAPI app factory, CORS middleware from `CORS_ALLOWED_ORIGINS` (comma-separated, default `http://localhost:3000` if unset), startup event validating all required environment variables (raising clearly if any is missing) and calling `bedrock.startup_validation()`, structured logging setup, and the Mangum ASGI handler; defer `boto3`/BeautifulSoup imports until first use
    - Create `backend/api/routes/health.py` with `GET /health` (no auth) returning `{"status": "ok"}` (200) when ready or `{"status": "unavailable"}` (503) otherwise; register the health router in `main.py`; only log on status change, not every request
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 23.1, 23.2, 23.3, 22.1, 22.2, 22.4, 16.2_

  - [ ] 3.3 Implement JWT extraction dependency for routes
    - Create `backend/api/routes/auth.py` with a FastAPI dependency `get_current_user_id(request)` that reads `event.requestContext.authorizer.claims.sub` from the Lambda/Mangum scope via `backend/shared/auth.py` and returns the `userId` for use in all `/me/...` routes
    - _Requirements: 13.1, 13.3_

- [ ] 4. Profile and roles endpoints
  - [ ] 4.1 Implement POST /me/profile/parse endpoint
    - Create `backend/api/routes/profile.py` with `POST /me/profile/parse`: validates `cvText` via `validate_cv_text` (413 if >50KB), invokes `BedrockClient.invoke_with_retry` against `PerfilEstructurado` using `BEDROCK_MODEL_SMALL`, returns 200 with the parsed profile (not persisted), 400 on validation failure after retry, 502 on Bedrock failure/timeout; register the profile router in `backend/main.py`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ] 4.2 Implement GET /me/profile and PUT /me/profile endpoints
    - Add `GET /me/profile` to `backend/api/routes/profile.py`: queries Perfiles by `userId` (from JWT dependency), returns 200 with `perfilEstructurado`, `resumenParaMatching`, `cargosSugeridos`, `cargosActivos`, `profileVersion`, `updatedAt`, and derived `resumenGenerating` (read-only from stored `resumenGenerationStatus`, written by a worker outside backend-core's scope); returns 404 with `profile_not_found` when absent
    - Add `PUT /me/profile`: validates body against `SaveProfileRequest`, persists ONLY `perfilEstructurado`/`profileVersion += 1`/`updatedAt` to the Perfiles table, and returns HTTP 200 with `{"profileVersion", "updatedAt"}` immediately once the write completes — no synchronous score recalculation, no Bedrock invocation, no `asyncio.create_task()` or other in-process background task, no SQS enqueue, and no modification of `resumenParaMatching` or `resumenGenerationStatus` (those fields are owned entirely by a worker outside backend-core's scope)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 10.1, 10.2, 10.3, 10.4, 10.5, 17.1, 17.2, 17.3_

  - [ ] 4.3 Implement POST /me/roles/suggest and PUT /me/roles endpoints
    - Add `POST /me/roles/suggest` to `backend/api/routes/profile.py`: returns 424 `resume_not_ready` when `resumenParaMatching` is null or generation is in progress (both read-only from the Perfiles table, never written by this endpoint), otherwise invokes `BedrockClient.invoke_with_retry` against `RolesSuggestions` using `BEDROCK_MODEL_SMALL`, returns 200 with `{"suggestions", "suggestedAt"}` (not persisted); returns 400 on validation failure after retry, 502 on Bedrock failure
    - Add `PUT /me/roles`: validates body via `validate_roles_list` (1–10 items, ≤50 chars each, empty list accepted), persists `cargosActivos`/`profileVersion += 1`/`updatedAt`, returns 200 with `{"profileVersion", "cargosActivos", "updatedAt"}` without synchronous rescoring
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Companies and subscriptions endpoints
  - [ ] 6.1 Implement GET /companies and POST /companies endpoints
    - Create `backend/api/routes/companies.py` with `GET /companies`: paginated (`limit` 10–100 default 20, `offset`) listing from Empresas, sorted case-insensitively by `nombre`, returning the raw stored fields only — `companyId`, `nombre`, `careersUrl`, `plataforma`, `lastScannedAt`, `lastScanStatus`, `lastVacancyCount`, `consecutiveFailures` — with no derived/computed warning flag, plus `{"companies", "total", "hasMore"}`
    - Add `POST /companies`: validates `careersUrl` via `validate_empresa_url`, normalizes via `normalize_url`/`compute_company_id`, detects platform using ONLY `detect_platform_hostname_only(url)` (pure hostname check, no HTTP fetch, no JSON-LD inspection — returns `'greenhouse'`/`'lever'`/`'html'`), maps a malformed-URL parse failure from that function to 400 `platform_detection_failed`, returns 409 `company_already_exists` if the hash exists, otherwise creates the Empresas entry with `lastScannedAt = null`, `lastScanStatus = null`, `lastVacancyCount = 0`, `consecutiveFailures = 0` and returns 201 with `{"companyId", "nombre", "plataforma", "createdAt"}`; register the companies router in `backend/main.py`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ] 6.2 Implement GET /me/companies and PUT /me/companies/{companyId} endpoints
    - Add `GET /me/companies` to `backend/api/routes/companies.py`: queries Suscripciones by `userId` where `activa = true`, left-joins Empresas details, sorted by `addedAt` descending, returns `{"subscriptions": [...]}` with only the raw stored fields (`companyId`, `nombre`, `plataforma`, `addedAt`, `lastScannedAt`, `lastScanStatus`, `lastVacancyCount`, `consecutiveFailures`) — no derived/computed warning flag; interpretation of `lastScanStatus`/`consecutiveFailures` is left to the client
    - Add `PUT /me/companies/{companyId}`: validates the subscription exists for `(userId, companyId)` (404 `subscription_not_found`), validates `companyId` exists in Empresas (400 `company_not_found`), sets `activa` and refreshes `addedAt` on reactivation, returns 200 with `{"companyId", "activa", "updatedAt"}`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Lambda entry point and OpenAPI export
  - [ ] 8.1 Implement Lambda entry point
    - Create `lambda_handler.py` at the repo root importing the Mangum `handler` from `backend/main.py`, exposing it as the Lambda function's configured handler target
    - _Requirements: 22.1, 22.2_

  - [ ] 8.2 Create OpenAPI export script
    - Create `scripts/export-openapi.py`: imports the fully assembled `app` from `backend/main.py`, calls `app.openapi()`, and writes the result to `frontend/openapi/openapi.json` (indented JSON)
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP; they cover only the pure functions in `validators.py` and `normalization.py` per project testing policy — no boto3/moto/localstack mocking is used anywhere in this plan.
- `backend/shared/` (tasks 1.1–1.11) is fully implemented and checkpointed before any API route task begins.
- Endpoint tasks are grouped exactly as: health, JWT extraction, profile parse, profile get/put, roles suggest/put, companies list/add, subscriptions get/put.
- No infrastructure/Terraform/CI tasks are included; `infra/` and `.github/workflows/` are out of scope for this spec.
- The OpenAPI export task (8.2) is intentionally last since it depends on the fully wired FastAPI app.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["1.5", "1.7", "1.9", "1.10", "1.11"] },
    { "id": 3, "tasks": ["1.6", "1.8"] },
    { "id": 4, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 5, "tasks": ["4.1"] },
    { "id": 6, "tasks": ["4.2", "6.1"] },
    { "id": 7, "tasks": ["4.3", "6.2"] },
    { "id": 8, "tasks": ["8.1"] },
    { "id": 9, "tasks": ["8.2"] }
  ]
}
```
