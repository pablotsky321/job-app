# Implementation Plan: backend-scan-y-scoring

## Overview

This implementation plan breaks down the backend-scan-y-scoring feature into actionable coding tasks, organized to build pure functions first (testable without AWS), then orchestration Lambdas, finally APIs and endpoints. Each task is executable with clear done criteria referencing design constraints and test validation.

---

## Tasks

### Category 1: Extraction Cascade — Pure Testable Functions (NO AWS mocks)

- [ ] 1. Implement core extraction interfaces and helpers
  - Create `backend/shared/extraction.py` with:
    - `class VacancyExtracted` (titulo, descripcion, url, modalidad, ubicacion)
    - `class ExtractionResult` (vacancies: List[VacancyExtracted], origen: str, error: Optional[str])
    - `compute_vacancyId(url: str) -> str`: SHA-256 normalized URL hash (64 hex chars, lowercase)
    - `normalize_url(url: str) -> str`: lowercase scheme/host, remove fragment, trailing slash
  - Validate: `compute_vacancyId` is deterministic (same URL → same hash), normalizes HTTPS/http and Example.COM/example.com
  - _Requirements: 1.1_

- [ ] 2. Implement Board API Client extractor
  - Create `backend/shared/board_api_client.py` with:
    - `board_api_client(empresa: Empresa) -> ExtractionResult`
    - Support plataforma='greenhouse' and 'lever' (read boardToken from Empresa)
    - Parse JSON response, map to VacancyExtracted (titulo, url required; modalidad defaults to 'sin_dato')
    - Handle HTTP errors (4xx/5xx), timeouts, invalid JSON
    - Return `ExtractionResult(vacancies=[], origen='board_api', error=...)` on failure
  - Validate without AWS boto3 calls: mock HTTP responses, test error handling
  - _Requirements: 3.1-3.6, 2.8_

- [ ] 3. Implement JSON-LD Extractor
  - Create `backend/shared/json_ld_extractor.py` with:
    - `json_ld_extractor(empresa: Empresa) -> ExtractionResult`
    - Fetch careersUrl, parse HTML, locate application/ld+json JobPosting blocks
    - Handle standalone objects, arrays, @graph nesting
    - Map JobPosting to VacancyExtracted (title, url required; modalidad defaults to 'sin_dato')
    - Handle HTTP errors (4xx/5xx), timeouts, connection errors, missing blocks
    - Return `ExtractionResult(vacancies=[...], origen='json_ld', error=None)` or error
  - Test: pure HTML parsing without boto3, mock HTTP responses
  - _Requirements: 4.1-4.5, 2.8_

- [ ] 4. Implement HTML cleaning for LLM processing
  - Create `backend/shared/html_cleaner.py` with:
    - `html_to_clean_text(html: str, max_clean_size_kb: int = 100) -> str`
    - Remove script, style, noscript, svg, iframe, meta tags and content
    - Remove HTML comments
    - Extract text, normalize whitespace (multiple spaces → one)
    - Truncate if > max_clean_size_kb (action: truncate, not skip)
  - Test: Pure BeautifulSoup (html.parser only, NO lxml), verify size limit enforcement
  - _Requirements: 5.1, tech rule_

- [ ] 5. Implement HTML+LLM Extractor with validation retry
  - Create `backend/shared/html_llm_extractor.py` with:
    - `html_llm_extractor(empresa: Empresa) -> ExtractionResult`
    - Fetch careersUrl, clean HTML via html_to_clean_text
    - Invoke Bedrock (via backend/shared/bedrock.py) with BEDROCK_MODEL_SMALL
    - Validate response against Pydantic model (vacancies: List[VacancyExtracted])
    - On first validation failure: retry once with error injected in prompt
    - On second failure: return `ExtractionResult(vacancies=[], origen='html_llm', error=...)`
    - Return `ExtractionResult(vacancies=[...], origen='html_llm', error=None)` on success
  - Test: mock Bedrock responses (valid JSON, invalid JSON, validation edge cases), pure function logic
  - _Requirements: 5.2-5.6, 2.8, tech rule (Bedrock via bedrock.py)_

- [ ] 6. Implement Cascada_Descubrimiento orchestrator (pure function)
  - Create `backend/shared/cascada_descubrimiento.py` with:
    - `cascada_descubrimiento(empresa: Empresa) -> tuple: (vacancies, origen, error)`
    - Route by plataforma:
      - 'greenhouse'/'lever': try board_api → if 0 vacancies or error, try json_ld → if 0 vacancies or error, try html_llm
      - 'html'/'jsonld': try json_ld → if 0 vacancies or error, try html_llm
      - 'manual': skip all, return ([], None, None)
    - Stop and return immediately at the first method (board_api or json_ld) that returns N > 0 vacancies
    - html_llm is always the LAST method attempted in the sequence (never skipped when reached) and its result is accepted as final regardless of how many vacancies it returns (0 or more) or whether it raises an error — there is no subsequent fallback after html_llm
    - Return tuple: (List[VacancyExtracted], origen_str_or_none, error_str_or_none)
  - Test: No AWS calls, verify cascada order and stop logic for each plataforma
  - _Requirements: 2.1-2.13_

---

### Category 2: Scan Result Classification & Closure Logic — Pure Testable Functions

- [ ] 7. Implement scan result classification function
  - Create `backend/shared/scan_classification.py` with:
    - `classify_scan_result(empresa: Empresa, extraction_result: tuple) -> str`
    - Input: empresa with lastVacancyCount, extraction_result = (vacancies_list, origen, error)
    - Classification logic:
      - error present → 'FAILED'
      - error None AND len(vacancies) > 0 → 'OK'
      - error None AND len(vacancies) == 0 AND empresa.lastVacancyCount > 0 → 'EMPTY_SOSPECHOSO'
      - error None AND len(vacancies) == 0 AND empresa.lastVacancyCount == 0 → 'EMPTY_LEGITIMO'
    - Return exactly one classification (never ambiguous)
  - Test: exhaustive decision table (all four cases), pure function
  - _Requirements: 6.1-6.6_

- [ ] 8. Implement missCount increment and vacancy closure logic
  - Create `backend/shared/misscount_logic.py` with:
    - `apply_missCount_logic(empresa: Empresa, vacantes_nuevas_en_escan: List[VacancyExtracted], vacantes_existentes: List[Vacante]) -> List[Vacante]`
    - For each EXISTING vacancy:
      - If vacancyId NOT in scan result: missCount += 1
      - If vacancyId IS in scan result: missCount = 0
      - If missCount >= 2 AND origen != 'manual': estado = 'cerrada'
      - If estado was 'cerrada' AND vacancyId in scan: estado = 'abierta'
    - For each NEW vacancy in scan:
      - Create with vacancyId = SHA-256(url), missCount = 0, estado = 'abierta'
    - Return: list of updated/new Vacante records (ready for DynamoDB upsert)
  - Test: pure function, verify incrementing, reset, closing, reopening with various missCount sequences
  - _Requirements: 7.1-7.7_

---

### Category 3: Cargo Prefiltro — Pure Testable Function

- [ ] 9. Implement cargo prefiltro with token matching
  - Create `backend/shared/prefiltro_cargos.py` with:
    - `get_significant_tokens(text: str) -> set`
      - Lowercase, remove diacritics (NFD normalization), split on whitespace/punctuation
      - Remove Spanish stopwords (y, o, el, la, de, del, en, a, por, para, etc.)
      - Return set of remaining tokens
    - `pasa_prefiltro_cargos(titulo_vacante: str, cargosActivos: List[str], threshold: int = 1) -> bool`
      - If cargosActivos empty → return True (bypass prefiltro)
      - For each cargo: compute overlap between get_significant_tokens(titulo) and get_significant_tokens(cargo)
      - If overlap >= threshold for ANY cargo → return True
      - Otherwise → return False
  - Test: pure token matching, verify stopword removal, accent removal, threshold behavior
  - _Requirements: 16.2-16.7_

---

### Category 4: Orchestration Lambdas (SQS-driven, with AWS but pure-function core)

- [ ] 10. Implement Orquestador Lambda (POST /scans endpoint)
  - Create `backend/api/routes/orquestador.py` with:
    - `handler_post_scans(event, context)` Lambda entry point
    - Extract userId from JWT (event.requestContext.authorizer.claims.sub)
    - Resolve active Suscripciones for userId, deduplicate companyIds
    - Query each Empresa: apply Ventana_Frescura (1h for board_api/json_ld, 12h for html_llm)
    - Create ScanJob (status='RUNNING', empresasTotal=count after Ventana_Frescura)
    - Populate empresasOmitidas with companies filtered by Ventana_Frescura
    - Publish exactly one ScanMessage to SQS_Scan per eligible company
    - Handle SQS publish failures: if ALL fail → status='FAILED'; if SOME → status='PARCIAL'
    - Update ScanJob with final status
    - Return HTTP 200 with jobId
  - Test with mocks: JWT extraction, Suscripción queries, Ventana_Frescura logic, SQS send errors
  - _Requirements: 8, 9, 10, 11_

- [ ] 11. Implement Scan_Worker Lambda (SQS_Scan consumer)
  - Create `backend/workers/scan_worker.py` with:
    - `handler_scan_worker(event, context)` Lambda entry point
    - For each SQS record: extract jobId, companyId from ScanMessage
    - Execute cascada_descubrimiento(empresa)
    - Classify result via classify_scan_result
    - Update Empresa (consecutiveFailures, lastVacancyCount, ultimoOrigenExitoso)
    - If OK: apply_missCount_logic, upsert Vacantes to DynamoDB
    - If OK: query active Suscripciones, enqueue ScoringMessages for new vacancies
    - ADD companyId to ScanJob.empresasCompletadas (String Set, idempotent)
    - If FAILED/EMPTY_SOSPECHOSO: also ADD to empresasFallidas
    - Return success or raise (SQS retries on error)
  - Test with mocks: cascada flow, classification routing, Vacante upsert, SQS_Scoring publish
  - _Requirements: 2, 6, 7, 12, 13_

- [ ] 12. Implement Scoring_Worker Lambda (SQS_Scoring consumer)
  - Create `backend/workers/scoring_worker.py` with:
    - `handler_scoring_worker(event, context)` Lambda entry point
    - For each SQS record: extract userId, vacancyId from ScoringMessage
    - Fetch Perfil(userId), check scoreProfileVersion vs profileVersion (Requirement 13.6)
    - If scoreProfileVersion == profileVersion: skip (return, no error)
    - Fetch Vacante by vacancyId
    - Apply pasa_prefiltro_cargos(titulo, cargosActivos)
    - If filtered: PUT UsuarioVacante with estado='filtered_out', return
    - If passes: invoke Bedrock_Client with scoring prompt
    - Validate response against ScoringResult model
    - On first validation error: retry with error injected in prompt
    - On second validation error: log error (NOT raw response), raise (SQS retry)
    - On success: PUT UsuarioVacante with score, scoreDetalle, scoreProfileVersion, estado='scored'
    - Log structured JSON (score, veredicto only, NOT resumen/coincidencias/faltantes)
  - Test with mocks: idempotence (scoreProfileVersion check), Bedrock response validation, prefiltro routing
  - _Requirements: 13, 16, 17_

- [ ] 13. Implement GET /scans/{jobId} endpoint
  - Create `backend/api/routes/scans.py` with:
    - `handler_get_scans(event, context)` Lambda entry point
    - Extract userId from JWT
    - Fetch ScanJob(jobId)
    - 404 if not found
    - 404 if userId set and differs from requesting user
    - Zombie detection: if status='RUNNING' AND now - startedAt > 600s → status='PARCIAL'
    - Auto-DONE: if status='RUNNING' AND empresasCompletadas >= empresasTotal → status='DONE'
    - Build response: status, empresasTotal, completados count, omitidos count, fallidos count, startedAt
    - If status='PARCIAL': include list of pending companyIds (not in completados nor omitidos)
    - Include canStop: true if status in [DONE, PARCIAL, FAILED], false if RUNNING
    - Return HTTP 200 with response body
  - Test with mocks: authorization, zombie detection timing, status transitions, response fields
  - _Requirements: 14, 15_

---

### Category 5: Shared Helpers & Rescoring Support

- [ ] 14. Implement Rescoring_Detector pure functions
  - Create `backend/shared/rescoring.py` with:
    - `is_score_stale(usuario_vacante: UsuarioVacante, perfil: Perfiles) -> bool`
      - Pure function: no I/O
      - Compare scoreProfileVersion with perfil.profileVersion
      - Return True if not equal, False if equal or usuario_vacante None
    - `enqueue_rescore(userId: str, vacancyId: str) -> bool`
      - Publish exactly one ScoringMessage to SQS_Scoring
      - Return True on success, False on error (log error, no raise)
      - Non-blocking (returns immediately)
  - Test: pure boolean logic for staleness, mock SQS send for enqueue
  - _Requirements: 18.1-18.6_

---

### Category 6: Unit Tests for Pure Functions (NO AWS mocks, focused)

- [ ] 15. Write unit tests for extraction cascade
  - Create `backend/tests/test_cascada_descubrimiento.py` with:
    - Test compute_vacancyId: determinism, URL normalization (case, fragment, trailing slash)
    - Test cascada_descubrimiento: order by plataforma, stop logic (first N>0), manual skip
    - Test each extractor (board_api, json_ld, html_llm) error handling
    - Test extraction result classification (OK vs EMPTY_SOSPECHOSO vs FAILED)
  - Run: `pytest backend/tests/test_cascada_descubrimiento.py -v`
  - _Requirements: 2, 6_

- [ ] 16. Write unit tests for scan classification
  - Create `backend/tests/test_scan_classification.py` with:
    - Test classify_scan_result: all four classifications (OK, FAILED, EMPTY_SOSPECHOSO, EMPTY_LEGITIMO)
    - Test exhaustive decision table: (error, vacancies_count, lastVacancyCount) tuples
    - Verify exactly one classification per input (no ambiguity)
  - Run: `pytest backend/tests/test_scan_classification.py -v`
  - _Requirements: 6_

- [ ] 17. Write unit tests for missCount logic
  - Create `backend/tests/test_misscount_logic.py` with:
    - Test increment on missing vacancies (missCount += 1)
    - Test reset on reappearance (missCount = 0)
    - Test closing condition (missCount >= 2 AND origen != 'manual')
    - Test reopening when vacante reappears (estado='cerrada' → 'abierta')
    - Test manual origen protection (never closes)
    - Test new vacancy creation (missCount=0, estado='abierta', firstSeenAt set)
    - Test existing vacancy update (lastSeenAt updated, firstSeenAt unchanged)
  - Run: `pytest backend/tests/test_misscount_logic.py -v`
  - _Requirements: 7_

- [ ] 18. Write unit tests for HTML cleaning
  - Create `backend/tests/test_html_cleaner.py` with:
    - Test script/style/noscript/svg removal (no content leakage)
    - Test comment removal
    - Test whitespace normalization
    - Test size truncation (max_clean_size_kb enforced)
    - Test BeautifulSoup with html.parser (no lxml)
  - Run: `pytest backend/tests/test_html_cleaner.py -v`
  - _Requirements: 5_

- [ ] 19. Write unit tests for prefiltro_cargos
  - Create `backend/tests/test_prefiltro_cargos.py` with:
    - Test get_significant_tokens: lowercasing, diacritic removal, stopword filtering
    - Test pasa_prefiltro_cargos: token overlap >= threshold
    - Test empty cargosActivos (bypass, return True)
    - Test no overlap (return False)
    - Test threshold configurable
    - Test Spanish stopwords removal
  - Run: `pytest backend/tests/test_prefiltro_cargos.py -v`
  - _Requirements: 16_

---

## Notes

- **Pure functions first**: Tasks 1-9 are testable without AWS mocks. Use pytest with real HTTP mocks (responses library) for network tests.
- **Orchestration next**: Tasks 10-13 integrate AWS (SQS, DynamoDB, Bedrock via shared bedrock.py). Mock boto3 client methods.
- **Tests last**: Tasks 15-19 validate pure functions. NO moto/botocore mocking; focus on business logic.
- **Tech rules enforced**:
  - NO lxml in HTML parsing (only html.parser)
  - Bedrock model IDs read from env vars via backend/shared/bedrock.py (NEVER hardcoded)
  - All LLM responses validated against Pydantic models with retry logic
  - userId from JWT only (never body/params)
  - Structured JSON logging (stdout), never CV text or scoreDetalle.resumen
  - Visibility timeout = 6× Lambda timeout (set via Terraform, not here)
  - Reserved concurrency enforced (Scan_Worker: 5, Scoring_Worker: 3 — via Terraform)
- **Idempotence safeguards**:
  - vacancyId as dedup key (SHA-256 normalized URL)
  - String Set ADD for empresasCompletadas/empresasFallidas
  - scoreProfileVersion staleness check
  - No duplicated Vacante records on SQS retry
- **User notes from request**:
  - Test cascada against 8-10 real seed companies before completing
  - Force EMPTY_SOSPECHOSO (empty HTML 200 OK) and verify vacancies don't close
  - Publish SQS message twice manually; verify ScanJob doesn't break
  - If resuming: check which tasks from backend-scan-y-scoring are already complete

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2", "3", "4", "5"] },
    { "id": 1, "tasks": ["6", "7", "8", "9"] },
    { "id": 2, "tasks": ["10", "11", "12", "13", "14"] },
    { "id": 3, "tasks": ["15", "16", "17", "18", "19"] }
  ]
}
```

---

## Workflow Completion

This task document is now ready for implementation. To begin:

1. Open `tasks.md` in the editor
2. Click "Start task" next to any Category 1 task to begin coding
3. Follow the sequential order (Category 1 → 2 → 3 → 4 → 5 → 6)
4. Each task references specific requirements; validate against design.md and requirements.md
5. Run tests after each category completes to validate pure functions and integration

Once all tasks are complete, the backend-scan-y-scoring feature is ready for:
- Lambda packaging and deployment (handled by CI/CD)
- Integration testing with real AWS services
- Frontend integration (GET /scans endpoint + score display in vacancy listing)
