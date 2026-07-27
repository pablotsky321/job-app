# Implementation Plan: Backend Vacantes y Notificaciones

## Overview

Convert the feature design into a series of prompts for a code-generation LLM that will implement each step with incremental progress. Each task builds on the previous ones and ends with wiring things together; there is no hanging or orphaned code left unintegrated.

Implementation language: **Python 3.12** (FastAPI + Mangum, Pydantic v2, boto3), per the design document and the closed-stack tech rules.

Tasks are ordered exactly as follows: (1) vacancy listing and detail, (2) manual vacancy registration, (3) apply, (4) CV-ATS generation, (5) question bank / notes (entries), (6) Notificador Lambda + EventBridge Scheduler integration — last, since it depends on ScanJob terminal transitions, UsuarioVacante records, and Suscripciones already existing.

Testing scope is intentionally narrow: only pure functions that take plain data structures (no boto3/DynamoDB/SQS/SES/Bedrock calls) get unit test sub-tasks — vacancy listing sort/filter/staleness logic, the language-detection heuristic, Notificador email body construction, and the zero-qualified-vacancies "no email" guard. No moto, no localstack, no boto3 mocking of any kind.

Terraform, frontend, and `.docx` generation are out of scope. Infrastructure (EventBridge Scheduler rule, IAM roles, SES domain verification, and — critically — DynamoDB Streams on the `ScanJobs` table plus the Lambda Event Source Mapping with its terminal-status FilterPolicy) is provisioned by the Terraform/infra spec, not here. Per `.kiro/steering/infraestructura-desplegada.md`, `ScanJobs` was created with only TTL enabled (`aws dynamodb update-time-to-live`) — no `update-table` call ever enabled a `StreamSpecification`, so as of today that stream does NOT exist yet. Task 11 (Notificador_Lambda) can be implemented and unit-tested here, but it has no possible trigger event in the currently deployed environment until the infra spec provisions the stream and event source mapping. See the explicit blocker note on task 11 below.

## Tasks

- [ ] 1. Extend shared domain models for this feature
  - 1.1 Add `UsuarioVacante` and `Entrada` Pydantic models to `backend/shared/models.py`
    - Add `UsuarioVacante`: `userId`, `companyId`, `vacancyId`, `estado` (`nueva`/`vista`/`aplicada`/`filtered_out`), `score` (Optional), `scoreProfileVersion` (Optional), `cvAtsTexto` (Optional), `cvGeneratedAt` (Optional), `appliedAt` (Optional), `createdAt`, using `ConfigDict(extra="ignore")` per project convention
    - Add `Entrada`: `pk` (`{userId}#{companyId}#{vacancyId}`), `entryId` (ULID string), `tipo` (`preguntas`/`nota_entrevista`), `contenido`, `createdAt`, using `ConfigDict(extra="ignore")`
    - Do NOT redefine `Empresa`, `Vacante`, `ScanJob`, `Suscripcion`, or `Perfiles` — those remain owned by `backend-core` / `backend-scan-y-scoring`; only add the two models this spec introduces
    - _Requirements: Glossary (UsuarioVacante, Entradas), 1.10, 2.1, 3.7, 4.1, 5.6, 6.3, tech rule 5_

- [ ] 2. Implement Vacancy_Listing_API (`GET /me/vacancies`)
  - 2.1 Implement pure filter/sort/staleness function
    - In `backend/shared/services/vacancy_service.py`, implement `build_vacancy_listing(usuario_vacantes: list[dict], vacantes_by_id: dict, profile_version: int | None, estado_filter: str) -> list[dict]` (or equivalent), taking only plain dicts/values, with no I/O
    - Filters records: `activas` → estado ∈ {nueva, vista}; `aplicadas` → estado == aplicada
    - Sorts `activas` by `score` descending (nulls last), tie-broken by `Vacante.lastSeenAt` descending; sorts `aplicadas` by `appliedAt` descending
    - Marks each record with `staleFlag=true` when `scoreProfileVersion != profile_version`, or when `scoreProfileVersion` is null and `estado == nueva`; otherwise `staleFlag=false`
    - Excludes `cvAtsTexto` from every returned record
    - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.10_
  - 2.2* Write unit tests for the filter/sort/staleness function
    - Cover: `activas` filter, `aplicadas` filter, score-descending with nulls last, `lastSeenAt` tie-break, `appliedAt` descending, staleness flag on version mismatch, staleness flag on null version + `nueva`, `cvAtsTexto` never present in output
    - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8_
  - 2.3 Implement the `GET /me/vacancies` endpoint
    - Create `backend/api/routes/vacancies.py`, add a router (`/me/vacancies`), and register it in `backend/main.py`
    - Extract `userId` via `Depends(get_current_user_id)` (401 if claim missing, per existing `auth.py` convention)
    - Validate `estado` query param: default `activas`; if present and not exactly `activas` or `aplicadas` (case-sensitive) → HTTP 400
    - Query `UsuarioVacante` by `userId` only (no GSI), fetch corresponding `Vacante`/`Empresa` summaries and the user's `Perfiles.profileVersion`
    - Call the function from 2.1 to filter/sort/flag staleness; for each stale record, invoke `enqueue_rescore` (reused from `backend-scan-y-scoring`'s `backend/shared/rescoring.py`) for `(userId, companyId, vacancyId)`; on failure, log and still return the existing score with `staleFlag=true`
    - Return HTTP 200 with an empty list when there are no matching records (never 404)
    - Log structured JSON without vacancy descriptions, profile content, or PII (opaque `userId` only)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.9, 1.10, 1.11, 9.1, 9.2, 9.3, 9.4, 11.1, 11.2, 11.3_

- [ ] 3. Implement Vacancy_Detail_API (`GET /me/vacancies/{companyId}/{vacancyId}`)
  - 3.1 Implement the endpoint in `backend/api/routes/vacancies.py`
    - Extract `userId` from JWT (401 if claim missing)
    - Read `Vacante` by `(companyId, vacancyId)`, `UsuarioVacante` by `(userId, {companyId}#{vacancyId})`, and `Empresa` by `companyId`; return 404 if any is missing
    - Build response combining `Vacante` fields, `EmpresaSummary` (`nombre`, `plataforma` only), and `UsuarioVacante`
    - Treat `cvAtsTexto` null/empty as a valid HTTP 200 response with an empty field (never 404/error)
    - Return the same response structure for `cerrada` vacancies as for open ones (no special-casing)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 9.1, 9.2, 9.3, 9.4, 11.1, 11.2, 11.3_

- [ ] 4. Checkpoint - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement Manual_Vacancy_Service (`POST /me/vacancies/manual`)
  - 5.1 Implement the `POST /me/vacancies/manual` endpoint
    - Add `ManualVacancyRequest` to `backend/api/models/requests.py`: `textoPegado` (1-20000 chars), `enlace` (absolute http/https URL), `nombreEmpresa` (1-200 chars after trim)
    - Add endpoint to `backend/api/routes/vacancies.py`; validate input per the above constraints, returning HTTP 400 with a descriptive message and creating no records on failure
    - Reuse `normalize_url`/hashing helpers already defined for `backend-scan-y-scoring` (e.g. `compute_vacancyId` in `backend/shared/extraction.py`) to compute `vacancyId` as SHA-256 of the normalized `enlace` — do not reimplement URL normalization/hashing locally
    - Resolve `Empresa`: normalize `nombreEmpresa` (trim + lowercase) and compare against existing catalog names under the same normalization; create a new `Empresa` (`plataforma=manual`, `careersUrl=null`) only if no match is found; never create/modify a `Suscripcion` as part of this flow
    - If no `Vacante` exists for the computed `vacancyId`: invoke `Bedrock_Client` (via `backend/shared/bedrock.py`) to extract `titulo`, `descripcion`, `modalidad`, `ubicacion` from `textoPegado`, validating against a local `BedRockExtractVacancyOutput` Pydantic model with one retry (error injected into the prompt); on second failure, return HTTP 400 and create no `Empresa`/`Vacante`/`UsuarioVacante` records; on success, create the `Vacante` with `origen=manual`, `estado=abierta`
    - If a `Vacante` for that `vacancyId` already exists: reuse it unmodified and skip the Bedrock call entirely
    - If no `UsuarioVacante` exists for `(userId, vacancyId)`: create it with `estado=nueva` and publish exactly one `ScoringMessage` to the scoring SQS queue; if one already exists: return HTTP 200 without creating a duplicate or publishing another message
    - Never make an HTTP request to `enlace`; persist it only in `Vacante.url`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 11.1, 11.2, 11.3, 11.4_

- [ ] 6. Implement Apply_Service (`POST /me/vacancies/{companyId}/{vacancyId}/apply`)
  - 6.1 Implement the endpoint in `backend/api/routes/vacancies.py`
    - Extract `userId` from JWT; read `UsuarioVacante` by `(userId, {companyId}#{vacancyId})`; return 404 if missing
    - Set `estado=aplicada` and `appliedAt=now()` only when `estado` was not already `aplicada`; if it was already `aplicada`, return HTTP 200 without modifying `appliedAt`
    - Behavior is identical regardless of `Vacante.estado` (`abierta` or `cerrada`)
    - _Requirements: 4.1, 4.2, 4.3, 9.1, 9.2, 9.3, 9.4, 11.1, 11.2, 11.3_

- [ ] 7. Implement CV_ATS_Service (`POST /me/vacancies/{companyId}/{vacancyId}/cv`)
  - 7.1 Implement the language-detection heuristic as a pure function
    - Add `detect_language(titulo: str, descripcion: str) -> str` to `backend/shared/normalization.py` (or a new `backend/shared/language_detection.py`): a simple keyword/heuristic-based detector over `titulo` + `descripcion`, defaulting to Spanish (`"es"`) when undetermined
    - _Requirements: 5.3, design Section 9.9 (Language Detection)_
  - 7.2* Write unit tests for the language-detection heuristic
    - Cover: clearly Spanish text, clearly English text, empty/ambiguous text (defaults to Spanish), mixed-language text
    - _Requirements: 5.3_
  - 7.3 Implement the `POST /me/vacancies/{companyId}/{vacancyId}/cv` endpoint
    - Add endpoint to `backend/api/routes/vacancies.py`; extract `userId` from JWT
    - Read `UsuarioVacante` by `(userId, companyId, vacancyId)`; return HTTP 404 if missing BEFORE evaluating `Vacante.estado` or calling Bedrock
    - If `UsuarioVacante` exists and `Vacante.estado == cerrada`, return HTTP 409 (`vacancy_closed`) regardless of any previously generated `cvAtsTexto`, without calling Bedrock
    - Otherwise, detect language via 7.1 from `Vacante.titulo`/`descripcion`, invoke `Bedrock_Client` with `Perfiles.perfilEstructurado` + `resumenParaMatching` + `Vacante`, validating against a local `CVATSOutput` model (`texto: str`, min length 1) with one retry (error injected in prompt)
    - On second validation failure: HTTP 400 if the input was the problem, HTTP 502 if Bedrock failed to respond at all; persist nothing in either case
    - On success: persist `cvAtsTexto` and `cvGeneratedAt` (overwriting any previous value), and return HTTP 200 with the text as `text/plain` (never uploaded to object storage, never a URL)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 11.1, 11.2, 11.3, 11.4_

- [ ] 8. Checkpoint - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement Entries_Service (question bank and notes)
  - 9.1 Implement `GET /me/vacancies/{companyId}/{vacancyId}/entries`
    - Create `backend/api/routes/entries.py`, add a router, and register it in `backend/main.py`
    - Extract `userId` from JWT; return HTTP 404 if `UsuarioVacante` or `Vacante` for `(userId, companyId, vacancyId)` do not exist
    - Query `Entrada` by `pk = {userId}#{companyId}#{vacancyId}`, ordered by `createdAt` ascending; return HTTP 200 with an empty list when there are none
    - _Requirements: 6.1, 6.2, 9.1, 9.2, 9.3, 9.4, 11.1, 11.2, 11.3_
  - 9.2 Implement `POST /me/vacancies/{companyId}/{vacancyId}/entries`
    - Add `CreateEntryRequest` to `backend/api/models/requests.py`: `tipo` (`preguntas`/`nota_entrevista`), `contenido` (1-5000 chars)
    - Add endpoint to `backend/api/routes/entries.py`; validate `tipo`/`contenido`, returning HTTP 400 and creating no record on failure
    - Return HTTP 404 (creating no record) if `UsuarioVacante` or `Vacante` for `(userId, companyId, vacancyId)` do not exist
    - Create the `Entrada` with `entryId` as a new ULID and `createdAt=now()`; the service never exposes update or delete operations on `Entrada`
    - _Requirements: 6.3, 6.4, 6.5, 6.6, 9.1, 9.2, 9.3, 9.4, 11.1, 11.2, 11.3_
  - 9.3 Implement `POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer`
    - Add endpoint to `backend/api/routes/entries.py`; extract `userId` from JWT
    - Read the referenced `Entrada`; return HTTP 404 if it does not belong to `(userId, companyId, vacancyId)`
    - Return HTTP 400 (without calling Bedrock) if the referenced `Entrada.tipo != preguntas`
    - Return HTTP 409 if `Vacante.estado == cerrada` (this restriction applies ONLY to this sub-endpoint, not to GET/POST entries)
    - Detect language via the function from 7.1 using the `Vacante`, then invoke `Bedrock_Client` with the question, `Perfiles.resumenParaMatching`, and the `Vacante`, validating against a local `SuggestedAnswerOutput` model (`respuesta: str`, min length 1) with one retry; on second failure return HTTP 400 and persist nothing
    - On success, create a NEW append-only `Entrada` with `tipo=nota_entrevista` containing the original question and the suggested answer (never modify the referenced `Entrada`)
    - _Requirements: 6.7, 6.8, 6.9, 6.10, 6.11, 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 11.1, 11.2, 11.3, 11.4_

- [ ] 10. Checkpoint - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Implement Notificador_Lambda stream handling and qualification logic
  - **Prerequisite / External Blocker**: DynamoDB Streams (`NEW_AND_OLD_IMAGES`) on the `ScanJobs` table, and the Lambda Event Source Mapping wiring that stream to this handler with the terminal-status `FilterPolicy`, must be provisioned by the infrastructure/Terraform spec BEFORE task 11 (and its sub-tasks 11.1–11.8) can be executed end-to-end or deployed. Per `.kiro/steering/infraestructura-desplegada.md`, `ScanJobs` was created with only `update-time-to-live` run against it — no `update-table` call ever set a `StreamSpecification`, so this stream currently does NOT exist. The code below can still be implemented and unit-tested (11.2/11.3 and 11.4/11.5 are pure functions with no AWS dependency), but the handler has no possible source of events until that infra gap is closed. Do not attempt to create the stream or event source mapping as part of this spec — that remains explicitly out of scope here.
  - 11.1 Implement DynamoDB Stream event parsing and filtering
    - Create `backend/workers/notificador/handler.py` with a Lambda entry point that, for each stream record, extracts `scanJobId`, `userId`, `status`, `empresasCompletadas`, `startedAt` from the new image
    - Skip the record (no further processing) when `userId` is not null (manual scan) or when the record is not a transition into a terminal status (`DONE`/`PARCIAL`/`FAILED`)
    - Note: this parsing logic can be implemented and unit-tested against synthetic stream-record payloads now; it cannot receive real events until the DynamoDB Stream + Event Source Mapping described above exist (infra spec)
    - _Requirements: 7.1, 7.2, 11.1, 11.2, 11.3_
  - 11.2 Implement the pure qualified-vacancy determination function
    - In `backend/workers/notificador/qualification.py`, implement `determine_qualified_vacancies(usuario_vacantes: list[dict], empresas_completadas: set[str], started_at: str) -> dict[str, list[dict]]` (or equivalent) taking only plain data (no I/O): for each `userId`, a "vacante nueva calificada" is any `UsuarioVacante` with `estado == nueva` (never `filtered_out` or any other estado), `Vacante.firstSeenAt >= startedAt`, and `companyId` in `empresasCompletadas`
    - Also implement `should_send_email(qualified_vacancies: list[dict]) -> bool`, returning `False` when the list is empty (zero-vacancies guard)
    - _Requirements: 7.3, 7.5_
  - 11.3* Write unit tests for qualified-vacancy determination and the zero-vacancies guard
    - **Property 3: Zero Vacancies → No Email** — **Validates: Requirement 7.5**
    - Cover: `estado=nueva` included, `filtered_out`/other estados excluded, `firstSeenAt` boundary (`==` and `<` `startedAt`), `companyId` not in `empresasCompletadas` excluded, empty qualified list → `should_send_email` returns `False`, non-empty list → returns `True`
    - _Requirements: 7.3, 7.5_
  - 11.4 Implement the pure email body/subject construction function
    - In `backend/workers/notificador/email_builder.py`, implement `build_notification_email(user_display_data: dict, qualified_vacancies: list[dict]) -> tuple[str, str]` (subject, body), taking only plain data (no I/O)
    - Subject: `"{count} nuevas vacante(s) de interés - {fecha_UTC}"`; body: plain text (no HTML) per the design's email template, listing at most 5 vacancies per call (caller sends multiple emails if more), truncating vacancy description to 250 characters and `cvAtsTexto` (when present) to 500 characters
    - _Requirements: 7.4, design Section 7 (Email Body Structure)_
  - 11.5* Write unit tests for the email body construction function
    - Cover: subject formatting, plain-text-only body (no HTML tags), description truncation at 250 chars, `cvAtsTexto` truncation at 500 chars, `cvAtsTexto` omitted when absent, max-5-vacancies-per-call truncation
    - _Requirements: 7.4_
  - 11.6 Implement SES sending with per-recipient error isolation
    - In `backend/workers/notificador/handler.py` (or a `ses_sender.py` helper), send the constructed email via SES to the user's registered address; on any failure (unverified address in sandbox mode, missing address, SES error), log the `userId` and a truncated (≤500 chars) failure reason without sensitive content, and continue processing remaining recipients without raising
    - _Requirements: 7.4, 7.6, 11.1, 11.2, 11.3, 11.4_
  - 11.7 Implement idempotency handling for `(scanJobId, userId)`
    - Ensure at most one email is sent per `(ScanJob.scanJobId, userId)` pair even if the Lambda is invoked more than once for the same transition (e.g. via a `notificacionesEnviadas` String Set on `ScanJob` updated with `ADD`, never decremented)
    - _Requirements: 7.7, tech rule 3_
  - 11.8 Wire the Notificador_Lambda handler end to end
    - In `backend/workers/notificador/handler.py`, integrate stream parsing (11.1) → qualification + zero-vacancies guard (11.2) → idempotency check (11.7) → email construction (11.4) → SES sending (11.6), emitting structured JSON logs to stdout that never include vacancy descriptions, profile content, or full email addresses
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 11.1, 11.2, 11.3, 11.4_

- [ ] 12. Implement Orquestador_Lambda programmed-mode integration (EventBridge Scheduler)
  - 12.1 Add the programmed-mode branch to the existing Orquestador Lambda
    - When invoked with `event.get("source") == "eventbridge-scheduler"` (no `userId`, no JWT claim, no other user-identifying value in the payload), resolve the set of companies to scan as the deduplicated union of `companyId` across ALL users' `Suscripciones` with `activa=true` (instead of a single user's subscriptions)
    - Create the `ScanJob` with `userId` left unset (null) in this mode
    - Leave the existing JWT-authenticated (manual) invocation path unchanged
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 13. Final checkpoint - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; they are all pure-function unit tests with no AWS mocking.
- Per explicit scope constraints, no unit tests are written for anything that requires mocking boto3, DynamoDB, SQS, SES, or Bedrock — those code paths (endpoint wiring, persistence, Bedrock invocation, SES sending, idempotency storage) are implemented but not unit tested here.
- Requirement 9 (JWT-only `userId`), Requirement 10 (Pydantic validation + one retry on Bedrock output), and Requirement 11 (structured logging without sensitive content) are cross-cutting and are referenced on every endpoint task that touches them.
- Terraform, frontend, and `.docx` generation are explicitly out of scope for this spec and are not represented by any task above.
- Known infra gap (discovered against `.kiro/steering/infraestructura-desplegada.md`): DynamoDB Streams on `ScanJobs` were never enabled (only TTL was) — task 11 (Notificador_Lambda) is fully codeable/testable now but has no real trigger until the Terraform/infra spec adds the `StreamSpecification` and the Event Source Mapping with its FilterPolicy. Do not assume this stream exists again without checking that steering doc.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["5.1"] },
    { "id": 5, "tasks": ["6.1"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3"] },
    { "id": 8, "tasks": ["9.1"] },
    { "id": 9, "tasks": ["9.2"] },
    { "id": 10, "tasks": ["9.3"] },
    { "id": 11, "tasks": ["11.1", "12.1"] },
    { "id": 12, "tasks": ["11.2", "11.4"] },
    { "id": 13, "tasks": ["11.3", "11.5"] },
    { "id": 14, "tasks": ["11.6"] },
    { "id": 15, "tasks": ["11.7"] },
    { "id": 16, "tasks": ["11.8"] }
  ]
}
```
