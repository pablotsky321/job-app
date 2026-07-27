# Requirements Document

## Introduction

Backend de plataforma de job search para usuarios que buscan empleo. Proporciona APIs REST síncronas para gestión de perfiles (parseo de CV con IA, sugerencia de cargos), catálogo compartido de empresas, suscripciones, y seguimiento de escaneos asíncronos. Integración con Amazon Bedrock para tareas de NLP (parseo, sugerencias, scoring). Arquitectura serverless: Lambda monolítica (FastAPI + Mangum), workers asíncronos en SQS, DynamoDB separadas por dominio.

## Glossary

- **System**: Backend API (Lambda FastAPI monolítica)
- **CV Original**: texto plano del currículum pegado por el usuario
- **Perfil Estructurado**: modelo Pydantic con experiencia laboral, formación académica, proyectos, certificaciones
- **Resumen para Matching**: extracto ≤500 palabras del perfil, generado por IA, para evitar pasar el perfil completo en scoring
- **Cargos Activos**: lista de puestos objetivo elegidos por el usuario, contra los que se filtran/puntúan vacantes
- **Vacante**: oferta laboral individual, con URL única como clave de deduplicación
- **Plataforma**: origen de descarga de vacantes (greenhouse, lever, jsonld, html, manual)
- **Escaneo**: proceso de descubrimiento en cascada (API → JSON-LD → HTML+LLM) para una empresa
- **ScanJob**: seguimiento asíncrono de un escaneo completo (múltiples empresas)
- **Suscripción**: relación usuario↔empresa que permite escaneo y seguimiento
- **Bedrock Model**: servicio de IA (región us-east-1), accedido vía IDs de modelo desde variables de entorno
- **JWT Authorizer**: validador Cognito que extrae userId del token
- **profileVersion**: número de versión del perfil; incrementa al guardar perfil o cargos, usado para rescoring híbrido
- **scoreProfileVersion**: versión del perfil con la que se calculó el último score de una vacante
- **Scoring de Match**: puntuación (0–100) y análisis de coincidencias/faltantes entre perfil y vacante


## Requirements

### Requirement 1: Parse CV into Structured Profile

**User Story:** As a job seeker, I want to upload or paste my CV and get a structured profile (without saving), so that I can review how the system understands my experience.

#### Acceptance Criteria

1. POST /me/profile/parse receives JSON with `cvText` (string, ≤50KB)
2. WHEN a valid CV text is provided, THE System SHALL invoke Bedrock (model from BEDROCK_MODEL_SMALL env var) with prompt requesting output in JSON matching `PerfilEstructurado` schema
3. THE System SHALL validate the response against `PerfilEstructurado` Pydantic model; IF validation fails on first attempt, THE System SHALL retry with validation error injected into the prompt; IF retry fails, THE System SHALL return HTTP 400 with structured error
4. THE System SHALL return HTTP 200 with `PerfilEstructurado` object; profile is NOT persisted
5. WHEN CV text exceeds 50KB, THE System SHALL return HTTP 413
6. WHEN Bedrock invocation times out or fails, THE System SHALL return HTTP 502 with `{"error": "ai_service_unavailable"}`
7. ALL Bedrock model IDs and failure conditions SHALL be logged as structured JSON (no PII: no CV text, no personal details); logging SHALL include request ID, model used, attempt number, response status


### Requirement 2: Get User Profile

**User Story:** As a user, I want to retrieve my saved profile, so that I can see my current structured experience.

#### Acceptance Criteria

1. GET /me/profile uses `userId` extracted from JWT authorizer (event.requestContext.authorizer.claims.sub)
2. WHEN profile exists, THE System SHALL query Perfiles table by userId and return HTTP 200 with object containing: `perfilEstructurado`, `resumenParaMatching`, `cargosSugeridos`, `cargosActivos`, `profileVersion`, `updatedAt`, and `resumenGenerating` (derived from `resumenGenerationStatus` field, as currently stored in the Perfiles table)
3. WHEN profile does not exist, THE System SHALL return HTTP 404 with `{"error": "profile_not_found"}`
4. IF `resumenGenerationStatus` equals `'pending'`, THE System SHALL set `resumenGenerating = true` in response; otherwise `resumenGenerating = false`
5. THE response schema SHALL ALWAYS include `resumenGenerating` boolean field, derived from the Perfiles table's `resumenGenerationStatus` field (values: 'pending' | 'complete' | 'failed' | null); THE System SHALL treat this field as data written by whichever process last updated it, without assuming it was backend-core itself


### Requirement 3: Save User Profile

**User Story:** As a user, I want to save my structured profile after reviewing/editing it, so that the system can use it for matching and suggestions.

#### Acceptance Criteria

1. PUT /me/profile receives JSON with `perfilEstructurado` (object, adheres to Pydantic model)
2. userId is extracted from JWT (never from body)
3. WHEN profile is valid, THE System SHALL:
   - Persist to Perfiles table: `userId` (PK), `perfilEstructurado`, `profileVersion += 1`, `updatedAt = now`
   - Return HTTP 200 with `{"profileVersion": N, "updatedAt": ISO8601}`
4. THE System SHALL NOT modify `resumenParaMatching` or `resumenGenerationStatus` when saving a profile; generation of `resumenParaMatching` is out of scope for backend-core (see Requirement 10)
5. WHEN saving a profile, THE System SHALL NOT recalculate scores in the synchronous response; scores with old `scoreProfileVersion` are rescored asynchronously
6. WHEN profile validation fails, THE System SHALL return HTTP 400 with validation errors
7. Logging SHALL record userId, profileVersion change, timestamp; SHALL NOT log profile content


### Requirement 4: Suggest Target Roles from Profile

**User Story:** As a user, I want the system to suggest job titles/roles based on my profile, so that I can define what positions I'm interested in.

#### Acceptance Criteria

1. POST /me/roles/suggest requires `resumenParaMatching` to exist in user's profile
2. WHEN resumen exists, THE System SHALL invoke Bedrock (BEDROCK_MODEL_SMALL) with prompt requesting role suggestions as JSON array of strings
3. THE System SHALL validate response against `List[str]` schema; IF validation fails, THE System SHALL retry with error injected; IF retry fails, THE System SHALL return HTTP 400
4. WHEN resumen does not exist, THE System SHALL return HTTP 424 (`{"error": "resume_not_ready"}`)
5. IF `resumenGenerating = true` (i.e., generation is in progress) OR `resumenParaMatching` is null, THE System SHALL return HTTP 424 with `{"error": "resume_not_ready"}`
6. THE System SHALL return HTTP 200 with `{"suggestions": ["Role1", "Role2", ...], "suggestedAt": ISO8601}`
7. Suggestions are NOT automatically saved to profile; user calls PUT /me/roles to persist


### Requirement 5: Set Active Roles

**User Story:** As a user, I want to specify which job titles I'm actively seeking, so that the system filters and scores only matching opportunities.

#### Acceptance Criteria

1. PUT /me/roles receives JSON with `cargosActivos` (List[string], 1–10 items, max 50 chars each)
2. THE System SHALL persist to Perfiles table: `cargosActivos`, `profileVersion += 1`, `updatedAt = now`
3. WHEN roles change, THE System SHALL NOT recalculate scores synchronously; instead, scores with outdated `scoreProfileVersion` are enqueued for async rescoring
4. THE System SHALL return HTTP 200 with `{"profileVersion": N, "cargosActivos": [...], "updatedAt": ISO8601}`
5. WHEN cargosActivos is empty list, THE System SHALL accept it (user may clear roles temporarily)
6. Logging SHALL record userId, previous roles, new roles, profileVersion delta


### Requirement 6: List Shared Company Catalog

**User Story:** As a user, I want to browse a shared catalog of companies, so that I can subscribe to monitor their job openings.

#### Acceptance Criteria

1. GET /companies returns list of companies from Empresas table (global, shared across all users)
2. WHEN paginating, THE System SHALL support `?limit=20&offset=0` (limit: 10–100, default 20)
3. FOR each company, THE System SHALL return the raw fields as stored in Empresas: `companyId`, `nombre`, `careersUrl`, `plataforma`, `lastScannedAt`, `lastScanStatus`, `lastVacancyCount`, `consecutiveFailures`, without computing any derived warning flag
4. THE System SHALL return HTTP 200 with `{"companies": [...], "total": N, "hasMore": bool}`
5. Sorting is by `nombre` (case-insensitive); no parameter override needed


### Requirement 7: Add Company to Catalog via URL

**User Story:** As a user, I want to add a new company to the shared catalog by providing its careers page URL, so that the system can discover and monitor its job openings.

#### Acceptance Criteria

1. POST /companies receives JSON with `careersUrl` (string, valid URL)
2. THE System SHALL normalize URL (lowercase scheme/host, remove fragment, remove trailing /) and compute `companyId` as SHA-256 hash (64 hexadecimal characters) of the normalized URL; check if this hash already exists in Empresas table
3. THE System SHALL detect platform by hostname inspection only (no HTTP fetch, no network call):
   - IF the normalized URL's hostname contains 'greenhouse' → platform = 'greenhouse'
   - ELSE IF the normalized URL's hostname contains 'lever' → platform = 'lever'
   - ELSE platform = 'html'
4. WHEN URL parsing fails (malformed URL, e.g., missing scheme or hostname), THE System SHALL return HTTP 400 with `{"error": "platform_detection_failed", "details": "..."}`
5. THE System SHALL create entry in Empresas table: `companyId` (SHA-256 hash, used internally), `nombre` (extracted from page title or URL, used for display), `careersUrl`, `plataforma`, `lastScannedAt = null`, `lastScanStatus = null`, `lastVacancyCount = 0`, `consecutiveFailures = 0`, `createdAt = now`
6. IF companyId already exists, THE System SHALL return HTTP 409 with `{"error": "company_already_exists", "companyId": "..."}`
7. THE System SHALL return HTTP 201 with `{"companyId": "...", "nombre": "...", "plataforma": "...", "createdAt": ISO8601}`
8. Logging SHALL record URL, detected platform, companyId, no validation details (URL normalization is internal)


### Requirement 8: Get User Company Subscriptions

**User Story:** As a user, I want to see which companies I'm subscribed to and their current scan status, so that I know which companies' jobs are being tracked.

#### Acceptance Criteria

1. GET /me/companies queries Suscripciones table by `userId` (PK), retrieves all rows where `activa = true`
2. FOR each subscription, THE System SHALL LEFT JOIN with Empresas to fetch the raw fields as stored: `nombre`, `careersUrl`, `plataforma`, `lastScannedAt`, `lastScanStatus`, `lastVacancyCount`, `consecutiveFailures`
3. THE System SHALL return HTTP 200 with:
   ```json
   {
     "subscriptions": [
       {
         "companyId": "...",
         "nombre": "...",
         "plataforma": "greenhouse|lever|jsonld|html|manual",
         "addedAt": "ISO8601",
         "lastScannedAt": "ISO8601|null",
         "lastScanStatus": "OK|FAILED|EMPTY_SOSPECHOSO|EMPTY_LEGITIMO|null",
         "lastVacancyCount": 42,
         "consecutiveFailures": 0
       }
     ]
   }
   ```
4. THE System SHALL NOT compute or include a derived warning flag based on `lastScanStatus` or `consecutiveFailures`; interpretation of these raw fields is left to the client
5. Subscriptions with `activa = false` are never returned (soft delete / unsubscribe pattern)
6. Sorting by `addedAt` (newest first); no override parameter


### Requirement 9: Activate or Deactivate Company Subscription

**User Story:** As a user, I want to enable or disable job tracking for a specific company without deleting the subscription, so that I can pause and resume monitoring.

#### Acceptance Criteria

1. PUT /me/companies/{companyId} receives JSON with `activa` (boolean)
2. userId is extracted from JWT
3. THE System SHALL query Suscripciones by `(userId, companyId)`. IF not found, THE System SHALL return HTTP 404 with `{"error": "subscription_not_found"}`
4. WHEN `activa = true`, THE System SHALL set `Suscripciones.activa = true`, `Suscripciones.addedAt = now` (reactivation timestamp)
5. WHEN `activa = false`, THE System SHALL set `Suscripciones.activa = false` (subscription persists, not deleted)
6. THE System SHALL return HTTP 200 with `{"companyId": "...", "activa": true/false, "updatedAt": ISO8601}`
7. IF companyId does not exist in Empresas table, THE System SHALL return HTTP 400 with `{"error": "company_not_found"}`
8. Logging SHALL record userId, companyId, activa change, timestamp


### Requirement 10: Profile Persistence Without Async Summary Generation

**User Story:** As a user, I want saving my profile to complete quickly, so that I do not experience latency waiting for AI processing that is unrelated to the save itself.

#### Acceptance Criteria

1. WHEN a user calls PUT /me/profile, THE System SHALL persist only `perfilEstructurado`, `profileVersion += 1`, and `updatedAt = now` to the Perfiles table, and return the HTTP response without invoking Bedrock
2. THE System SHALL NOT invoke Bedrock, SHALL NOT create any in-process async task, and SHALL NOT enqueue any message as part of handling PUT /me/profile
3. THE System SHALL NOT modify `resumenParaMatching` or `resumenGenerationStatus` when handling PUT /me/profile
4. Generation of `resumenParaMatching` and management of `resumenGenerationStatus` transitions are performed by a worker outside backend-core's scope; THE System SHALL treat both fields as read-only inputs when serving GET /me/profile and POST /me/roles/suggest (see Requirements 2 and 4)
5. Logging SHALL record userId, profileVersion change, timestamp; SHALL NOT log profile content


### Requirement 11: Bedrock Model Configuration and Failover

**User Story:** As an operator, I want model IDs and region to be configurable via environment variables so that I can swap models without code changes or support newer model IDs.

#### Acceptance Criteria

1. System SHALL read Bedrock inference profile IDs from environment variables:
   * `BEDROCK_MODEL_SMALL`: e.g., `us.anthropic.claude-3-haiku-20250514` or base model `anthropic.claude-3-haiku-*`
   * `BEDROCK_MODEL_MID`: e.g., `us.anthropic.claude-3-5-sonnet-20241022` or base model `anthropic.claude-3-5-sonnet-*`
   * `BEDROCK_REGION`: `us-east-1` (fixed; no runtime override)
   Model IDs may be inference profiles (prefix `us.`) or base models (prefix `anthropic.*`); both formats are valid.

2. AT STARTUP, System SHALL validate that each model ID exists and is accessible 
   by invoking a trivial Bedrock request: prompt "Respond with ok", timeout 2 seconds. 
   IF the model responds with a successful completion, the model is accessible. 
   IF timeout or error occurs, raise with clear error message (include model ID, region, actual error from API).

3. All model invocations through `backend/shared/bedrock.py` ONLY. No hardcoding 
   in other modules.

4. Logging SHALL include model ID and region for each call. On failure from Bedrock 
   (not Pydantic validation), log the error and raise to caller (no silent retry 
   at this layer).

5. Pydantic validation failure on model output SHALL retry once with same model; 
   if retry fails, raise.


### Requirement 12: Bedrock Output Validation with Retry

**User Story:** As the system, I need to validate all AI-generated output against schemas before using it, so that malformed responses don't crash the pipeline.

#### Acceptance Criteria

1. THE System SHALL NOT use `json.loads()` directly on Bedrock responses
2. FOR every Bedrock invocation that expects structured output (JSON), THE System SHALL parse and validate against a Pydantic model
3. IF validation fails on first attempt:
   - THE System SHALL log the validation error (field name, type mismatch, missing required field)
   - THE System SHALL inject error message into retry prompt: "Previous response failed validation: {error}. Please try again, ensuring JSON is valid and matches schema."
   - THE System SHALL retry up to 1 time
4. IF retry also fails, THE System SHALL:
   - Log the failure as a structured error (userId, task type, model used, attempt count)
   - Return HTTP 502 or 424 (depending on context) with descriptive error to client
   - NOT persist incomplete/partial data
5. Logging SHALL NOT include raw CV text, profile details, or full Bedrock responses; only validation error types and attempt counts


### Requirement 13: Authorization via JWT

**User Story:** As the system, I need to extract the authenticated user ID from JWT tokens, so that each user only sees and modifies their own data.

#### Acceptance Criteria

1. THE System SHALL extract `userId` from `event.requestContext.authorizer.claims.sub` (Cognito JWT, set by API Gateway Cognito Authorizer)
2. userId is NEVER read from request body, query parameters, or headers; only from JWT claims
3. FOR all endpoints under `/me/...`, THE System SHALL use extracted userId for all queries and mutations
4. IF JWT is invalid or missing, API Gateway (before reaching Lambda) SHALL reject with HTTP 401; the System does not need to handle this
5. FOR all database operations, THE System SHALL include userId in the query key to prevent cross-user data access
6. Logging SHALL include userId for debugging, but never log JWT tokens or sensitive claims


### Requirement 14: Structured JSON Logging

**User Story:** As an operator, I want all logs in structured JSON format so that I can query and analyze them programmatically in CloudWatch Logs Insights.

#### Acceptance Criteria

1. ALL logging SHALL output JSON to stdout (not files)
2. Each log record SHALL include:
   - `timestamp`: ISO 8601
   - `level`: `INFO` | `WARN` | `ERROR` | `DEBUG`
   - `requestId`: from Lambda context (for request tracing)
   - `userId`: when available (internal logs only; never in error responses sent to client)
   - `message`: short, descriptive
   - `context`: optional object with additional fields (model, attempt, status, etc.)
3. NEVER log (in external-facing error responses):
   - Raw CV text or profile content
   - Full Bedrock request/response bodies
   - JWT tokens or session secrets
   - DynamoDB query results (only summary: "queried X rows", not content)
4. Logging SHALL use Python `logging` module with JSON formatter (e.g., `python-json-logger`)
5. All Bedrock calls SHALL log model name, input size estimate, response status, retry count
6. All DynamoDB writes SHALL log operation type (put, update, delete), table, key, row count affected
7. userId and requestId SHALL be logged in all internal CloudWatch logs for debugging and tracing, but NEVER exposed to client-side error responses


### Requirement 15: Error Handling and HTTP Status Codes

**User Story:** As a frontend developer, I need consistent, semantic HTTP status codes and error messages so that I can handle failures gracefully.

#### Acceptance Criteria

1. THE System SHALL return:
   - `200 OK`: successful GET/PUT
   - `201 CREATED`: successful POST
   - `400 Bad Request`: invalid input, validation failure
   - `404 Not Found`: resource not found (profile, subscription, company)
   - `409 Conflict`: duplicate resource (e.g., company already exists)
   - `413 Payload Too Large`: CV or input exceeds size limit
   - `424 Dependency Failed`: prerequisite not ready (e.g., resumen not generated yet)
   - `502 Bad Gateway`: Bedrock invocation failed, network error
2. ALL error responses SHALL include JSON object:
   ```json
   {
     "error": "error_code",
     "message": "human_readable_message",
     "details": "optional_extra_info"
   }
   ```
3. Error codes (lowercase, underscore-separated):
   - `validation_error`: schema mismatch
   - `profile_not_found`: GET /me/profile when not exists
   - `ai_service_unavailable`: Bedrock timeout/error
   - `platform_detection_failed`: POST /companies URL detection failed
   - `resume_not_ready`: resumen generation still in progress
   - `subscription_not_found`: company subscription not found
   - etc.
4. Error responses SHALL NOT expose internal stack traces, SQL queries, secret names, or userId
5. Logging (internal, to CloudWatch) SHALL record status code, error code, userId, timestamp for all errors; however, error responses sent to client SHALL NOT include userId or sensitive internal details


### Requirement 16: Database Table Access via Environment Variables

**User Story:** As an operator, I want table names to be configurable via environment variables so that I can deploy to different DynamoDB instances without code changes.

#### Acceptance Criteria

1. THE System SHALL read table names from environment variables in `backend/shared/db.py`:
   - `DYNAMODB_TABLE_EMPRESAS`
   - `DYNAMODB_TABLE_VACANTES`
   - `DYNAMODB_TABLE_USUARIO_VACANTE`
   - `DYNAMODB_TABLE_ENTRADAS`
   - `DYNAMODB_TABLE_PERFILES`
   - `DYNAMODB_TABLE_SUSCRIPCIONES`
   - `DYNAMODB_TABLE_SCAN_JOBS`
2. IF any table name is not set, THE System SHALL fail at startup with clear error
3. All DynamoDB access goes through `backend/shared/db.py` helper functions (single source of truth)
4. Logging SHALL include table name for each DynamoDB operation (not the variable name, the resolved name)


### Requirement 17: PUT /me/profile Response Immediacy

**User Story:** As a user, I want PUT /me/profile to respond immediately after my profile is saved, so that the UI feels responsive.

#### Acceptance Criteria

1. WHEN a user calls PUT /me/profile, THE System SHALL return the HTTP response as soon as the Perfiles table write completes, without waiting on any AI generation step
2. THE System SHALL NOT use `asyncio.create_task()` or any other in-process background task as part of handling PUT /me/profile
3. IF user calls GET /me/profile shortly after saving, THE System SHALL return whatever `resumenParaMatching` and `resumenGenerationStatus` values are currently stored in the Perfiles table (per Requirement 2), without backend-core having modified them during the save


### Requirement 18: OpenAPI Schema Auto-Generation

**User Story:** As a frontend developer, I want the backend to automatically generate and serve an OpenAPI specification, so that I can generate TypeScript types without manual duplication.

#### Acceptance Criteria

1. FastAPI SHALL automatically generate OpenAPI 3.0 schema from Pydantic models and route annotations
2. THE System SHALL serve OpenAPI spec at `/openapi.json`
3. THE System SHALL serve Swagger UI at `/docs`
4. THE System SHALL NOT duplicate types in frontend code; frontend generates types from OpenAPI spec
5. Pydantic models in `backend/shared/models.py` are the single source of truth for all request/response schemas
6. OpenAPI schema SHALL include all endpoint descriptions, parameters, request/response bodies, and error responses


### Requirement 19: Bedrock Timeout Handling

**User Story:** As the system, I need to handle Bedrock API timeouts gracefully, so that temporary service issues don't crash the Lambda.

#### Acceptance Criteria

1. THE System SHALL set a timeout for all Bedrock invocations via boto3: `config.connect_timeout = 10`, `config.read_timeout = 60`
2. IF a timeout occurs, THE System SHALL log `{"level": "ERROR", "message": "bedrock_timeout", "model": "...", "elapsed": ...}`
3. THE System SHALL NOT retry on timeout (timeout = service is overloaded, retry makes it worse)
4. THE System SHALL return HTTP 502 with `{"error": "ai_service_unavailable"}`
5. On timeout, THE System SHALL NOT persist any partial or incomplete data; the client that issued the request is responsible for retrying


### Requirement 20: Pydantic Model Versioning and Compatibility

**User Story:** As a developer, I want Pydantic models to be forward-compatible with future fields so that API changes don't break existing clients.

#### Acceptance Criteria

1. ALL Pydantic models in `backend/shared/models.py` SHALL use `ConfigDict(extra="allow")` or `ConfigDict(extra="ignore")` to handle unknown fields gracefully
2. WHEN a client sends extra fields, THE System SHALL either ignore them (recommended) or log a warning (debug level only)
3. When adding new fields to models, use `Field(..., default=None)` for backward compatibility
4. Deprecation of fields SHALL be done via comments in code (not immediately removed)
5. Model changes SHALL always be backward compatible; breaking changes require API versioning (not in scope for this spec)


### Requirement 21: Health Check Endpoint

**User Story:** As an operator, I want a health check endpoint so that ALB/ELB can verify the Lambda is running and ready to serve traffic.

#### Acceptance Criteria

1. THE System SHALL expose GET /health with no authentication required
2. WHEN Lambda is ready, THE System SHALL return HTTP 200 with `{"status": "ok"}`
3. WHEN Lambda is starting up or in error state, THE System SHALL return HTTP 503 with `{"status": "unavailable"}`
4. Health check SHALL verify:
   - Lambda runtime is responsive
   - Environment variables are loaded
   - (Optional) DynamoDB connectivity, but only if a simple get operation is fast (<100ms)
5. Health check SHALL NOT log every request (too noisy); only log on status change


### Requirement 22: Cold Start Performance

**User Story:** As an operator, I want to minimize Lambda cold start time so that API latency is predictable and acceptable.

#### Acceptance Criteria

1. THE System SHALL minimize imports at module level; defer heavy imports (boto3, Bedrock client) until first use or use dependency injection
2. Lambda initialization (handler entry) SHALL complete in <500ms for an idle cold start
3. THE System SHALL use a Lambda Layer or bundled dependencies to reduce package size (<100MB uncompressed)
4. Logging on startup SHALL be minimal (no full config dumps, only essentials)
5. For cold start profiling, THE System SHALL log `{"level": "INFO", "message": "lambda_cold_start", "duration_ms": ...}` once per deployment


### Requirement 23: CORS Configuration

**User Story:** As a frontend developer, I want the backend to support CORS from the frontend domain so that browser requests are not blocked.

#### Acceptance Criteria

1. THE System SHALL configure FastAPI CORS middleware with:
   - `allow_origins`: from `CORS_ALLOWED_ORIGINS` env var (comma-separated list, e.g., `https://jobsearch.example.com, http://localhost:3000`)
   - `allow_credentials`: `true`
   - `allow_methods`: `["GET", "POST", "PUT", "DELETE", "OPTIONS"]`
   - `allow_headers`: `["*"]`
2. IF `CORS_ALLOWED_ORIGINS` is not set, THE System SHALL default to `http://localhost:3000` (dev) or fail at startup with clear error (prod)
3. Preflight requests (OPTIONS) SHALL be handled by middleware; Lambda handler does not need to implement OPTIONS routes
4. CORS headers SHALL NOT be logged for every request (debug level only on mismatch)


### Requirement 24: Request ID Propagation

**User Story:** As a developer, I want every request to have a unique ID so that I can trace logs and debugging across Lambda and downstream services.

#### Acceptance Criteria

1. THE System SHALL extract `x-request-id` header from incoming request (or generate one via UUID if not present)
2. THE System SHALL include `requestId` in all log records
3. THE System SHALL pass `x-request-id` to Bedrock invocations (via request context or header)
4. THE System SHALL include `x-request-id` in response headers for client-side tracing
5. Request ID SHALL be logged in every error and success response for correlation with logs


## End of Requirements

---

**Next Steps:**
1. User reviews requirements for completeness and clarity
2. User may request changes, clarifications, or mark as complete
3. After approval, workflow moves to Design phase
