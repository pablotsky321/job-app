# Design Document: Backend Core (backend-core)

## Overview

Monolithic Lambda-based REST API for job search platform. Single FastAPI + Mangum deployment handling all synchronous API endpoints. Integrates with Amazon Bedrock (us-east-1) for NLP tasks (CV parsing, role suggestions). Profile summary generation (`resumenParaMatching`) is performed by a worker outside backend-core's scope; backend-core only reads that field. Async work delegated to SQS-driven Lambda workers. All data persisted in separate, domain-specific DynamoDB tables.

**Tech Stack:**
- Runtime: Python 3.12 only
- Framework: FastAPI + Mangum (ASGI adapter for Lambda)
- Data: DynamoDB (separate tables per domain)
- AI: Amazon Bedrock (us-east-1), Claude 3 models via boto3
- Parsing: BeautifulSoup4 with html.parser (NOT lxml)
- Validation: Pydantic v2 with `ConfigDict(extra="ignore")`
- Logging: Structured JSON to stdout
- Packaging: ZIP archive (Lambda layer + function code)
- OpenAPI: Auto-generated from Pydantic models, exported to file via script

---

## Directory Structure and Module Organization

```
backend/
├── __init__.py
│   # Entry point package marker
├── main.py
│   # FastAPI app initialization, CORS, middleware, route registration
│   # Cold start: ~150ms, defers boto3/Bedrock client init
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   │   # GET /health (no auth required)
│   │   │   # Checks Lambda readiness, minimal logging
│   │   ├── auth.py
│   │   │   # Middleware + utilities for JWT extraction
│   │   │   # get_current_user_id() -> str from event.requestContext.authorizer.claims.sub
│   │   ├── profile.py
│   │   │   # POST /me/profile/parse (CV → PerfilEstructurado) — TASK 1
│   │   │   # GET /me/profile (fetch saved profile, read-only resumen fields)
│   │   │   # PUT /me/profile (persist perfilEstructurado/profileVersion/updatedAt
│   │   │   #   ONLY, return immediately; NO Bedrock call, NO asyncio task, NO enqueue)
│   │   │   # POST /me/roles/suggest (suggest roles from resumen) — TASK 3
│   │   │   # PUT /me/roles (save cargosActivos)
│   │   ├── companies.py
│   │   │   # GET /companies (list shared catalog)
│   │   │   # POST /companies (add URL, detect platform, normalize)
│   │   │   # GET /me/companies (list user subscriptions)
│   │   │   # PUT /me/companies/{companyId} (toggle subscription)
│   │   └── openapi.py
│   │       # GET /openapi.json (served by FastAPI auto)
│   │       # GET /docs (Swagger UI)
│   └── models/
│       ├── __init__.py
│       └── requests.py
│           # Request body Pydantic schemas (separate from domain models)
│           # ParseCVRequest, SaveProfileRequest, AddCompanyRequest, etc.
│
├── shared/
│   ├── __init__.py
│   ├── models.py
│   │   # ✅ SINGLE SOURCE OF TRUTH for all domain models
│   │   # Pydantic models: PerfilEstructurado, ResumenParaMatching, Vacante, 
│   │   #   Empresa, Suscripcion, ScanJob, etc.
│   │   # All use ConfigDict(extra="ignore") for forward compatibility
│   ├── bedrock.py
│   │   # ✅ ONLY module that reads BEDROCK_MODEL_* env vars
│   │   # Classes: BedrockClient (init, invoke, timeout handling)
│   │   # startup_validation() -> validates model accessibility at Lambda init
│   │   # Never hardcodes model IDs
│   ├── db.py
│   │   # DynamoDB access helpers: query, put, update, delete
│   │   # Reads DYNAMODB_TABLE_* env vars at module import
│   │   # Single source for all table interactions
│   ├── auth.py
│   │   # JWT validation utilities (called from routes/auth.py)
│   ├── validators.py
│   │   # Pure validation functions (no AWS calls, no network)
│   │   # normalize_url(), compute_company_id(), detect_platform_hostname_only()
│   │   # validate_cv_text(), validate_roles_list(), etc.
│   ├── normalization.py
│   │   # Pure text processing (no AWS calls)
│   │   # html_to_clean_text(), normalize_whitespace()
│   │   # extract_page_title(), extract_json_ld(), etc.
│   ├── logging_config.py
│   │   # JSON logger setup (python-json-logger or custom)
│   │   # Structured log context manager with requestId
│   └── errors.py
│       # Custom exception classes with HTTP status mappings
│       # ValidationError, AIServiceUnavailable, DependencyFailed, etc.
```

**NOTE:** Worker Lambda functions (orquestador, scan-worker, scoring-worker, notificador) are defined in separate specs and deployed as individual Lambda functions. Backend-core is ONLY the synchronous FastAPI API. No worker code lives here.

**Module Docstrings and Responsibilities:**

```python
# backend/__init__.py
"""
job-app backend package.
Monolithic FastAPI Lambda for REST API + async workers for heavy lifting.
"""

# backend/main.py
"""
FastAPI application factory and Lambda handler.
- CORS middleware (from CORS_ALLOWED_ORIGINS env var)
- JWT extraction middleware
- Structured JSON logging
- Route registration
- Mangum ASGI adapter
- Cold start: defers boto3/Bedrock client init until first use
"""

# backend/api/__init__.py
"""API layer: routes and request models."""

# backend/api/routes/health.py
"""
Health check endpoint.
GET /health → {"status": "ok"} (HTTP 200)
No authentication required. Minimal logging.
"""

# backend/api/routes/auth.py
"""
JWT extraction and authorization utilities.
- get_current_user_id() -> str: extracts userId from JWT claims.sub
- never reads userId from body or query params
"""

# backend/api/routes/profile.py
"""
Profile management endpoints.
- POST /me/profile/parse: CV → PerfilEstructurado (Bedrock SMALL model)
- GET /me/profile: fetch saved profile; resumenParaMatching/resumenGenerationStatus
  are read as-is from the Perfiles table (written by a worker outside this scope)
- PUT /me/profile: persist perfilEstructurado, profileVersion += 1, updatedAt = now
  ONLY, then return immediately. Does NOT invoke Bedrock, does NOT create an
  asyncio task, does NOT enqueue any message. Does NOT modify resumenParaMatching
  or resumenGenerationStatus.
- POST /me/roles/suggest: suggest roles from resumen (Bedrock SMALL); reads
  resumenParaMatching/resumenGenerationStatus read-only
- PUT /me/roles: save cargosActivos
All endpoints extract userId from JWT.
"""

# backend/api/routes/companies.py
"""
Company catalog and subscription management.
- GET /companies: list shared Empresas (global, paginated)
- POST /companies: add company by URL (platform detection, normalization)
- GET /me/companies: list user's active Suscripciones with company details
- PUT /me/companies/{companyId}: toggle subscription activa flag
"""

# backend/shared/models.py
"""
Domain models (Pydantic v2).
SINGLE SOURCE OF TRUTH. All models ConfigDict(extra="ignore").
- PerfilEstructurado: structure from CV parsing
- ResumenParaMatching: ≤500-word summary for scoring
- Vacante: individual job posting
- Empresa: company in shared catalog
- Suscripcion: user → company relationship
- ScanJob: async scan job tracker
- Internal models for API responses (inherit from domain models as needed)
"""

# backend/shared/bedrock.py
"""
Bedrock integration (ONLY module that reads BEDROCK_MODEL_* env vars).
- BedrockClient class: init, invoke_with_retry()
- Timeout: connect=10s, read=20s (strict limit < API Gateway ~29s cutoff)
- Pydantic validation with 1 retry on failure
- startup_validation(): verify models accessible at Lambda init
- All model IDs read from env, never hardcoded
"""

# backend/shared/db.py
"""
DynamoDB access helpers (reads DYNAMODB_TABLE_* env vars at import).
- query_by_pk(table, userId, ...)
- query_by_sk(table, ...)
- put_item(table, item)
- update_item(table, key, updates)
- delete_item(table, key)
Minimal error handling (log + re-raise); Lambda will return 502.
"""

# backend/shared/validators.py
"""
Pure validation functions (NO AWS calls, NO network, 100% testable).
- detect_platform_hostname_only(url) -> str: checks hostname for 'greenhouse'
  or 'lever' substring, else returns 'html'. Fully pure and self-contained;
  this is the ONLY platform detection function used by POST /companies.
  No network-based wrapper is needed for this spec.
"""

# backend/shared/normalization.py
"""
Pure text processing (NO AWS calls, 100% testable).
- html_to_clean_text(html) -> str: BeautifulSoup with html.parser
- normalize_whitespace(text) -> str: strip, collapse multiple spaces
- extract_page_title(html) -> str: <title> tag content or fallback
- extract_json_ld(html) -> dict|None: parse application/ld+json
- extract_careers_url_from_html(html, base_url) -> str|None: find href matching 'career'|'job'
"""

# backend/shared/logging_config.py
"""
Structured JSON logging (python-json-logger).
- get_logger(name) -> logger with JSON formatter
- RequestContext: context manager for requestId injection
- All logs include: timestamp (ISO8601), level, requestId, userId (when available), message, context
- Never log: CV text, profile content, JWT tokens, DB contents
"""

# backend/shared/errors.py
"""
Custom exceptions with HTTP status code mapping.
- ValidationError (400)
- ProfileNotFound (404)
- AIServiceUnavailable (502)
- PlatformDetectionFailed (400)
- ResumeNotReady (424)
- SubscriptionNotFound (404)
- CompanyAlreadyExists (409)
- CVTooLarge (413)
"""
```

---

### Functions Requiring AWS Services or Network

Functions that CANNOT be unit-tested without AWS mocks, network mocks, or integration tests:

**backend/shared/bedrock.py:**
- `invoke_bedrock()`: Invokes Amazon Bedrock API (requires real or mocked credentials)
- `startup_validation_models()`: Tests model accessibility at Lambda startup

**backend/shared/db.py:**
- All DynamoDB query/put/update/delete functions
- Testing: Use moto mocks or DynamoDB local

**NOTE:** POST /companies (`backend/api/routes/companies.py`) does NOT require network
mocks. It uses only `detect_platform_hostname_only(url)` from `validators.py`, which
is fully pure. No HTTP fetch or JSON-LD detection is performed by this endpoint.

---

### Pure Functions by Module (100% Testable, No AWS)

**backend/shared/validators.py:**
```python
def normalize_url(url: str) -> str
def compute_company_id(url: str) -> str  # SHA-256 hash
def detect_platform_hostname_only(url: str) -> str  # Pure: 'greenhouse'|'lever'|'html'
def validate_cv_text(text: str) -> tuple[bool, str | None]
def validate_roles_list(roles: List[str]) -> tuple[bool, str | None]
def validate_empresa_url(url: str) -> tuple[bool, str | None]
```

`detect_platform_hostname_only()` is fully pure (no network, no AWS calls) and is
sufficient on its own for POST /companies. It requires no HTTP-fetching wrapper in
this spec:
- IF the normalized URL's hostname contains 'greenhouse' → 'greenhouse'
- ELSE IF the normalized URL's hostname contains 'lever' → 'lever'
- ELSE → 'html'
- IF URL parsing fails (malformed URL: missing scheme or hostname) → raises, mapped
  to `platform_detection_failed` (HTTP 400). This error is only ever raised for
  malformed URL parsing, never for fetch/timeout errors (no fetch is performed).

**backend/shared/normalization.py:**
```python
def html_to_clean_text(html: str) -> str
def normalize_whitespace(text: str) -> str
def extract_page_title(html: str) -> str | None
def extract_json_ld(html: str) -> dict | None
def extract_careers_url_from_html(html: str, base_url: str) -> str | None
```

**Testing:** Pytest with parametrized fixtures, no AWS mocks needed.

---

## Environment Variables Reference

All variables configured in Lambda environment at deployment time via Terraform.
**No secrets hardcoded in code.**

| Variable Name | Required? | Default | Example | Description |
|---|---|---|---|---|
| **AWS Region & Bedrock** | | | | |
| `BEDROCK_REGION` | Required | N/A | `us-east-1` | Amazon Bedrock region (fixed, no override at runtime) |
| `BEDROCK_MODEL_SMALL` | Required | N/A | `us.anthropic.claude-3-haiku-20250514` or `anthropic.claude-3-haiku-*` | Model ID for lightweight tasks (CV parsing, role suggestions). Can be inference profile (prefix `us.`) or base model. |
| `BEDROCK_MODEL_MID` | Required | N/A | `us.anthropic.claude-3-5-sonnet-20241022` or `anthropic.claude-3-5-sonnet-*` | Model ID for medium complexity (scoring context). |
| **DynamoDB Tables** | | | | |
| `DYNAMODB_TABLE_EMPRESAS` | Required | N/A | `dev-empresas` or `prod-empresas` | Companies catalog (global, shared across users). Pattern: `{ENV}-empresas` |
| `DYNAMODB_TABLE_VACANTES` | Required | N/A | `dev-vacantes` or `prod-vacantes` | Job postings (global, keyed by vacanteSha256). Pattern: `{ENV}-vacantes` |
| `DYNAMODB_TABLE_USUARIO_VACANTE` | Required | N/A | `dev-usuario-vacante` or `prod-usuario-vacante` | User-specific job interest tracking (userId + vacanteSha256). Pattern: `{ENV}-usuario-vacante` |
| `DYNAMODB_TABLE_PERFILES` | Required | N/A | `dev-perfiles` or `prod-perfiles` | User profiles (userId PK): estructura, resumen, cargos, versions. Pattern: `{ENV}-perfiles` |
| `DYNAMODB_TABLE_SUSCRIPCIONES` | Required | N/A | `dev-suscripciones` or `prod-suscripciones` | User subscriptions (userId + companyId composite key). Pattern: `{ENV}-suscripciones` |
| `DYNAMODB_TABLE_SCAN_JOBS` | Required | N/A | `dev-scan-jobs` or `prod-scan-jobs` | Async scan job tracking (scanJobId PK). Pattern: `{ENV}-scan-jobs` |
| `DYNAMODB_TABLE_ENTRADAS` | Required | N/A | `dev-entradas` or `prod-entradas` | Audit log / entry log for scan history. Pattern: `{ENV}-entradas` |
| **SQS Queues** | | | | |
| `SQS_QUEUE_SCAN_URL` | Required | N/A | `https://sqs.us-east-1.amazonaws.com/123456789/dev-scan` | SQS queue URL for scan jobs. Pattern: `{ENV}-scan` |
| `SQS_QUEUE_SCAN_DLQ_URL` | Required | N/A | `https://sqs.us-east-1.amazonaws.com/123456789/dev-scan-dlq` | Dead-letter queue for scan failures. Pattern: `{ENV}-scan-dlq` |
| `SQS_QUEUE_SCORING_URL` | Required | N/A | `https://sqs.us-east-1.amazonaws.com/123456789/dev-scoring` | SQS queue URL for scoring jobs. Pattern: `{ENV}-scoring` |
| `SQS_QUEUE_SCORING_DLQ_URL` | Required | N/A | `https://sqs.us-east-1.amazonaws.com/123456789/dev-scoring-dlq` | Dead-letter queue for scoring failures. Pattern: `{ENV}-scoring-dlq` |
| **CORS** | | | | |
| `CORS_ALLOWED_ORIGINS` | Required | N/A | `https://jobsearch.example.com,http://localhost:3000` | Comma-separated list of allowed frontend origins |
| **Logging** | | | | |
| `LOG_LEVEL` | Optional | `INFO` | `DEBUG` or `INFO` | Minimum log level (stdout, CloudWatch Logs) |
| **Lambda Cold Start Tracking** | | | | |
| `ENABLE_COLD_START_LOGGING` | Optional | `true` | `true` or `false` | Log `lambda_cold_start` event on first invocation |

**Table Naming Convention:**
- Pattern: `{ENV}-{TABLE_NAME}`
- `{ENV}` = `dev` or `prod` (single environment per design)
- `{TABLE_NAME}` = empresas, vacantes, usuario-vacante, perfiles, suscripciones, scan-jobs, entradas
- Example: `dev-empresas`, `prod-perfiles`, etc.

**Validation at Startup:**
```python
# pseudo-code in backend/main.py on_event():
required_vars = [
    "BEDROCK_REGION", "BEDROCK_MODEL_SMALL", "BEDROCK_MODEL_MID",
    "DYNAMODB_TABLE_EMPRESAS", "DYNAMODB_TABLE_VACANTES",
    "DYNAMODB_TABLE_USUARIO_VACANTE", "DYNAMODB_TABLE_PERFILES",
    "DYNAMODB_TABLE_SUSCRIPCIONES", "DYNAMODB_TABLE_SCAN_JOBS",
    "DYNAMODB_TABLE_ENTRADAS",
    "SQS_QUEUE_SCAN_URL", "SQS_QUEUE_SCAN_DLQ_URL",
    "SQS_QUEUE_SCORING_URL", "SQS_QUEUE_SCORING_DLQ_URL",
    "CORS_ALLOWED_ORIGINS"
]
for var in required_vars:
    if not os.getenv(var):
        raise RuntimeError(f"Missing required env var: {var}")
# Then startup_validation() tests model accessibility
```

---

## Bedrock Tasks: Models, Schemas, and Retry Strategy

### Task 1: Parse CV into Structured Profile

**Endpoint:** `POST /me/profile/parse`  
**Model:** `BEDROCK_MODEL_SMALL`  
**Timeout:** 20s (read), 10s (connect)  
**Max Retries:** 1 (on Pydantic validation failure)

**Input:**
```python
class ParseCVRequest(BaseModel):
    cvText: str  # Max 50KB
```

**Output Pydantic Model:**
```python
class ExperienciaLaboral(BaseModel):
    puesto: str
    empresa: str
    duracion: str  # e.g., "2 years", "Jan 2020 - Dec 2021"
    descripcion: str
    tecnologias: List[str] = []
    model_config = ConfigDict(extra="ignore")

class Educacion(BaseModel):
    titulo: str
    institucion: str
    ano: str
    especializacion: str | None = None
    model_config = ConfigDict(extra="ignore")

class Proyecto(BaseModel):
    nombre: str
    descripcion: str
    tecnologias: List[str] = []
    url: str | None = None
    model_config = ConfigDict(extra="ignore")

class Certificacion(BaseModel):
    nombre: str
    emisor: str
    ano: str
    model_config = ConfigDict(extra="ignore")

class PerfilEstructurado(BaseModel):
    """CV parsed into structured profile"""
    experiencia: List[ExperienciaLaboral]
    educacion: List[Educacion]
    proyectos: List[Proyecto] = []
    certificaciones: List[Certificacion] = []
    skills: List[str]
    lenguajes: List[str] = []
    model_config = ConfigDict(extra="ignore")
```

**Prompt Template:**
```
Extract the following information from the CV text and return a JSON object:
- experiencia: array of work experience (puesto, empresa, duracion, descripcion, tecnologias)
- educacion: array of education (titulo, institucion, ano, especializacion)
- proyectos: array of projects (nombre, descripcion, tecnologias, url)
- certificaciones: array of certifications (nombre, emisor, ano)
- skills: array of technical skills
- lenguajes: array of languages

CV Text:
{cvText}

Return ONLY valid JSON matching the schema above. No explanation.
```

**Retry Prompt (on validation failure):**
```
Previous response failed validation. Error: {validation_error}
Please try again, ensuring the JSON is valid and matches this schema:
{schema_definition}

CV Text:
{cvText}

Return ONLY valid JSON. No explanation.
```

**Response Mapping:**
- Success (HTTP 200): Return `PerfilEstructurado` object
- Validation fails after retry (HTTP 400): `{"error": "validation_error", "details": "..."}`
- Timeout/Bedrock error (HTTP 502): `{"error": "ai_service_unavailable"}`
- CV too large (HTTP 413): `{"error": "payload_too_large"}`

---

### Task 3: Suggest Target Roles from Profile

**Endpoint:** `POST /me/roles/suggest`  
**Model:** `BEDROCK_MODEL_SMALL`  
**Timeout:** 20s (read), 10s (connect)  
**Max Retries:** 1 (on Pydantic validation failure)  
**Prerequisite:** `resumenParaMatching` must exist AND `resumenGenerating != true`

**Input:**
```python
class SuggestRolesRequest(BaseModel):
    # Uses resumenParaMatching from user's profile (no input needed)
    pass
```

**Output Pydantic Model:**
```python
class RolesSuggestions(BaseModel):
    suggestions: List[str]  # Array of 3-7 role titles
    suggestedAt: datetime
    model_config = ConfigDict(extra="ignore")
```

**Prompt Template:**
```
Based on this professional profile summary, suggest 5-7 job titles/roles that would be a good fit.
Return as JSON array of strings.

Profile Summary:
{resumenParaMatching}

Return ONLY a JSON array of strings: ["Role1", "Role2", ...]. No explanation.
```

**Retry Prompt (on validation failure):**
```
Previous response failed validation. Return a JSON array of 5-7 job title strings.
Error: {validation_error}

Profile Summary:
{resumenParaMatching}

Return ONLY: ["Role1", "Role2", ...]. Valid JSON array. No explanation.
```

**Response Mapping:**
- Success (HTTP 200): `{ suggestions: [...], suggestedAt: ISO8601 }`
- Resumen not ready (HTTP 424): `{ error: "resume_not_ready" }`
- Validation fails (HTTP 400): `{ error: "validation_error", details: "..." }`
- Timeout (HTTP 502): `{ error: "ai_service_unavailable" }`

---

## Pure Functions and AWS-Free Testing

Functions below require NO AWS services and are 100% unit-testable with deterministic inputs/outputs.

### Pure Functions by Module

**backend/shared/validators.py** (all pure, no AWS):

```python
def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.
    - Lowercase scheme and host
    - Remove fragment (#)
    - Remove trailing /
    - Return absolute URL
    Example: https://EXAMPLE.com/careers/#jobs → https://example.com/careers
    """
    # Uses urllib.parse, no network calls

def compute_company_id(url: str) -> str:
    """
    Compute SHA-256 hash of normalized URL (64 hex chars).
    Used as unique company identifier.
    Example: normalize_url(...) → SHA-256 hash
    """
    # Uses hashlib, deterministic

def detect_platform_hostname_only(url: str) -> str:
    """
    Detect job posting platform from URL hostname only. Fully pure, no
    network call, no HTTP fetch.
    Returns: 'greenhouse' | 'lever' | 'html'
    - If 'greenhouse' in hostname → 'greenhouse'
    - Else if 'lever' in hostname → 'lever'
    - Else → 'html'
    Raises on malformed URL (missing scheme or hostname), mapped by the
    route to HTTP 400 `platform_detection_failed`.
    This is the ONLY platform detection function used by POST /companies.
    """
    # Uses urllib.parse, deterministic, no network calls

def validate_cv_text(text: str) -> tuple[bool, str | None]:
    """
    Validate CV text: non-empty, <50KB.
    Returns: (is_valid, error_message)
    """
    # Uses len(), str.strip(), no AWS calls

def validate_roles_list(roles: List[str]) -> tuple[bool, str | None]:
    """
    Validate cargosActivos: 1-10 items, each ≤50 chars, non-empty.
    Returns: (is_valid, error_message)
    """
    # Pure string validation

def validate_empresa_url(url: str) -> tuple[bool, str | None]:
    """
    Validate company URL format: http/https, non-empty.
    Returns: (is_valid, error_message)
    """
    # Uses urllib.parse.urlparse(), no AWS calls
```

**Testing Strategy for Pure Functions:**
- No AWS mocks needed (moto, etc.)
- Use `pytest` with parametrized fixtures
- Test deterministic inputs → outputs
- Example test:
  ```python
  @pytest.mark.parametrize("input_url,expected_normalized", [
      ("https://EXAMPLE.COM/careers/#jobs", "https://example.com/careers"),
      ("http://example.com/careers/", "http://example.com/careers"),
  ])
  def test_normalize_url(input_url, expected_normalized):
      assert normalize_url(input_url) == expected_normalized
  ```

**backend/shared/normalization.py** (all pure, no AWS):

```python
def html_to_clean_text(html: str) -> str:
    """
    Parse HTML with BeautifulSoup (html.parser, NOT lxml).
    Extract text, preserve structure (keep newlines between blocks).
    Remove script/style tags.
    Example: "<h1>Jobs</h1><p>Apply now</p>" → "Jobs\nApply now"
    """
    # Uses BeautifulSoup with html.parser

def normalize_whitespace(text: str) -> str:
    """
    Strip leading/trailing whitespace, collapse multiple spaces.
    Example: "  hello   world  " → "hello world"
    """
    # Pure string operations

def extract_page_title(html: str) -> str | None:
    """
    Extract <title> tag content.
    Falls back to empty string if not found.
    """
    # Uses BeautifulSoup, no network

def extract_json_ld(html: str) -> dict | None:
    """
    Find and parse application/ld+json block in HTML.
    Returns parsed dict or None if not found.
    """
    # Uses BeautifulSoup + json.loads(), no network

def extract_careers_url_from_html(html: str, base_url: str) -> str | None:
    """
    Find href matching 'career' or 'job' keywords in HTML.
    Resolve relative URLs to absolute using base_url.
    Returns first match or None.
    """
    # Uses BeautifulSoup + urllib.parse.urljoin(), no network
```

**Testing Strategy for Normalization:**
- Fixture-based HTML strings
- Example:
  ```python
  def test_html_to_clean_text():
      html = "<h1>Jobs</h1><p>Apply</p>"
      assert "Jobs" in html_to_clean_text(html)
      assert "Apply" in html_to_clean_text(html)
  ```

---

## Lambda Packaging and Deployment (ZIP Format)

### Zip Layout

**Structure:**
```
job-app-backend-dev.zip
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── health.py
│   │   │   ├── auth.py
│   │   │   ├── profile.py
│   │   │   ├── companies.py
│   │   │   └── openapi.py
│   │   └── models/
│   │       ├── __init__.py
│   │       └── requests.py
│   └── shared/
│       ├── __init__.py
│       ├── models.py
│       ├── bedrock.py
│       ├── db.py
│       ├── auth.py
│       ├── validators.py
│       ├── normalization.py
│       ├── logging_config.py
│       └── errors.py
├── lambda_handler.py
│   # Entry point: imports main.handler from backend/main.py
│   # from backend.main import handler
└── [dependencies installed via pip -t .]
```

**NOTE:** Workers (orquestador, scan_worker, scoring_worker, notificador) are separate Lambda functions, not part of backend-core.

### Dependencies (requirements.txt)

```
fastapi==0.104.1
mangum==0.26.0
pydantic==2.5.0
boto3==1.34.0
python-json-logger==2.0.7
beautifulsoup4==4.12.2
python-multipart==0.0.6
```

### Layer vs. Bundled

**Option A: Dependencies in Lambda Layer (Recommended)**
- Create separate `job-app-dependencies.zip` with `/python/lib/python3.12/site-packages/*`
- Publish as Lambda Layer (name: `job-app-deps-python312`)
- Main function zip contains ONLY `backend/` + `lambda_handler.py` (~50KB)
- Layer size: ~150MB uncompressed (typical for these deps)
- Attach layer to Lambda function in Terraform

**Option B: Bundled (Fallback)**
- Run `pip install -r requirements.txt -t .` in a build directory
- Copy `backend/` + `lambda_handler.py` + site-packages into zip
- Result: ~150MB total
- Simpler for small deployments, slower cold start

**Recommended: Use Layer** to keep cold start quick.

### Build Script (scripts/build-lambda-zip.sh)

```bash
#!/bin/bash
set -e

PYTHON_VERSION="3.12"
BUILD_DIR="build"
ZIP_FILE="job-app-backend-prod.zip"

# Clean previous builds
rm -rf $BUILD_DIR $ZIP_FILE

# Create build directory
mkdir -p $BUILD_DIR

# Install dependencies into build dir (NOT into layer)
pip install -r backend/requirements.txt -t $BUILD_DIR/python/lib/python$PYTHON_VERSION/site-packages

# Copy backend source
cp -r backend $BUILD_DIR/
cp lambda_handler.py $BUILD_DIR/

# Create zip
cd $BUILD_DIR
zip -r ../$ZIP_FILE .
cd ..

echo "✓ Created $ZIP_FILE"
du -h $ZIP_FILE
```

### Zip Size Constraints

- **Max upload size (zip):** 50MB (Lambda limit)
- **Max uncompressed size (code + layer):** 250MB (Lambda limit)
- **Target for this project:** ~150-200MB uncompressed (slim)

---

## Function Declarations and Pure Functions Summary



---

## Bedrock Task Configuration

### Task 1: Parse CV → PerfilEstructurado

**Endpoint:** `POST /me/profile/parse`  
**Model ID:** Read from `BEDROCK_MODEL_SMALL` env var  
**Timeout:** 20s (read), 10s (connect)  
**Max Retries:** 1 retry on Pydantic validation failure

**Output Pydantic Model:**
```python
class PerfilEstructurado(BaseModel):
    """User's structured CV profile"""
    experiencia: List[ExperienciaLaboral]
    educacion: List[Educacion]
    proyectos: List[Proyecto] = []
    certificaciones: List[Certificacion] = []
    skills: List[str]
    lenguajes: List[str] = []
    model_config = ConfigDict(extra="ignore")
```

**Retry Strategy:**
- 1st attempt: Send CV text to Bedrock SMALL model
- If Pydantic validation fails: Inject error message + retry once
- If retry fails: Return HTTP 400 with validation error
- On timeout: Return HTTP 502

### Task 3: Suggest Roles

**Endpoint:** `POST /me/roles/suggest`  
**Model ID:** Read from `BEDROCK_MODEL_SMALL` env var  
**Input:** User's `resumenParaMatching`  
**Output:** Array of 5-7 role suggestions (JSON)

**Retry Strategy:**
- 1st attempt: Send resumen to Bedrock SMALL
- If validation fails: Retry with schema error injected
- If retry fails: Return HTTP 400

---

## Timeout Constraints

**Critical:** All Bedrock API calls use **connect=10s, read=20s** (NOT 60s).

**Rationale:**
- API Gateway default integration timeout: ~29 seconds for Lambda
- Leaving margin for other operations: read timeout must be < 25s to be safe
- 20s read timeout ensures Lambda completes well before API Gateway cutoff
- If Bedrock takes >20s: Return HTTP 502 ("ai_service_unavailable")

**All Bedrock tasks in this design use: read=20s, connect=10s**

---

## Lambda ZIP Packaging

**Build process:**
1. `pip install -r backend/requirements.txt -t build/`
2. Copy `backend/` + `lambda_handler.py` to build dir
3. `zip -r job-app-backend.zip build/*`
4. Upload to S3 + reference in Terraform

**Size constraints:**
- Max upload: 50MB
- Max uncompressed: 250MB
- Target: ~150MB with dependencies

**Dependencies (requirements.txt):**
```
fastapi==0.104.1
mangum==0.26.0
pydantic==2.5.0
boto3==1.34.0
python-json-logger==2.0.7
beautifulsoup4==4.12.2
python-multipart==0.0.6
```

---

## OpenAPI Export for Frontend

**Export script:** `scripts/export-openapi.py`

```python
from backend.main import app
import json

openapi_schema = app.openapi()
with open("frontend/openapi/openapi.json", "w") as f:
    json.dump(openapi_schema, f, indent=2)
```

**Frontend type generation:** `scripts/generate-types.sh`
```bash
npx openapi-typescript frontend/openapi/openapi.json -o frontend/src/api/types.ts
```

**Integration:**
- CI/CD runs export after backend deploy
- Commits updated `openapi.json` to repo
- Frontend regenerates types automatically

---

## Unit Tests (Pure Functions Only)

**Test coverage:** `backend/shared/validators.py` + `backend/shared/normalization.py`

**Example test cases:**

| Function | Input | Expected Output |
|---|---|---|
| `normalize_url()` | `"https://EXAMPLE.COM/careers/#jobs"` | `"https://example.com/careers"` |
| `compute_company_id()` | normalized URL | SHA-256 hash (64 hex chars) |
| `validate_cv_text()` | `""` (empty) | `(False, "...")` |
| `validate_cv_text()` | 60KB string | `(False, "...")` |
| `validate_roles_list()` | `[]` | `(False, "...")` |
| `html_to_clean_text()` | `"<h1>Title</h1>"` | contains `"Title"` |

**Run tests:**
```bash
pytest backend/tests/ -v --cov=backend/shared/validators,backend/shared/normalization
```

**No AWS mocks required** (except for integration tests, not in MVP).

---

## Cold Start Optimization

**Deferred imports in backend/main.py:**
- Import `logging`, `fastapi` at module level (lightweight)
- Defer `boto3`, `BeautifulSoup`, `httpx` until first use via lazy getters

**Startup validation:**
- Check all env vars present
- Test Bedrock models accessible (trivial prompt "Respond with ok", 2s timeout)
- Log cold start duration if > 100ms

**Target:** <500ms cold start

---

## Error Handling

**HTTP Status Codes:**
| Code | Condition |
|---|---|
| 200 | Success (GET/PUT) |
| 201 | Created (POST) |
| 400 | Validation error, bad input |
| 404 | Resource not found |
| 409 | Duplicate (company already exists) |
| 413 | Payload too large |
| 424 | Dependency failed (resumen not ready) |
| 502 | Bedrock timeout/error |

**Error Response Format:**
```json
{
  "error": "error_code",
  "message": "human readable message",
  "details": "optional extra info"
}
```

---

## Logging

**Format:** Structured JSON to stdout  
**Fields:** timestamp (ISO8601), level, requestId, userId (internal only), message, context  
**Never log:** CV text, profile content, JWT tokens, DB contents

**Example:**
```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "requestId": "abc-123",
  "userId": "user-456",
  "message": "profile_saved",
  "context": {
    "profileVersion": 2,
    "resumenStatus": "pending"
  }
}
```

---

## Completion Checklist

- [x] Directory structure: `api/`, `shared/`, `workers/` with docstrings
- [x] Environment variables: All 24+ vars documented with defaults, examples
- [x] Bedrock tasks: 2 tasks (Parse CV, Suggest Roles) with models, prompts, retry strategies
- [x] Pure functions: Validators + normalization (100% testable)
- [x] AWS functions: Bedrock, DynamoDB (require mocks/integration)
- [x] ZIP packaging: Build script, size constraints, dependencies
- [x] OpenAPI: Export script, frontend type generation
- [x] Testing: Unit tests for pure functions (no AWS mocks)
- [x] Error handling: Custom exceptions, HTTP status codes
- [x] Logging: Structured JSON, no PII
- [x] Cold start: Deferred imports, startup validation

**This design is complete and ready for implementation.**
