# Requirements Document

## Introduction

Esta spec corrige dos dependencias externas descubiertas y documentadas durante la spec `frontend-spa` (ya reflejadas en la sección de contratos de API y en el modelo de datos de `.kiro/steering/contexto-tecnico-backend.md`), más un desalineamiento de rutas en el código real de `backend/api/routes/profile.py`. No introduce infraestructura nueva ni Lambdas/colas nuevas: reutiliza patrones ya existentes en `backend/api/routes/companies.py` (idempotencia de suscripción) y la Lambda "api" ya existente (segundo modo de invocación asíncrona).

Alcance:
1. Alta idempotente de Suscripción vía `POST /me/companies/{companyId}` (create-or-reactivate), complementando el `PUT /me/companies/{companyId}` ya existente que solo activa/desactiva una Suscripción ya creada.
2. Disparo asíncrono de la generación de `resumenParaMatching` desde `PUT /me/profile`, usando el campo `resumenGenerationStatus` ya existente en `Perfiles` (sin agregar un campo booleano nuevo).
3. Corrección del criterio de bloqueo HTTP 424 de `POST /me/profile/roles/suggest`, para no bloquear cuando ya existe un resumen previo válido.
4. Corrección del prefijo de rutas de `roles_router` en `profile.py`, de `/me/roles` a `/me/profile/roles`, incluyendo tests y verificación de OpenAPI.

## Glossary

- **System**: Backend API (Lambda "api", FastAPI + Mangum monolítica)
- **Suscripción**: relación usuario↔empresa persistida en la tabla `Suscripciones` (`userId` PK, `companyId` SK, `activa` BOOL, `addedAt`)
- **Empresa**: entrada del catálogo compartido en la tabla `Empresas`, identificada por `companyId`
- **Alta idempotente**: operación de creación que, al repetirse sobre el mismo estado, no produce un efecto adicional (no-op si ya existe activa; reactiva si existía inactiva)
- **Perfil (Perfiles)**: documento por usuario en la tabla `Perfiles`, incluye `resumenParaMatching` y `resumenGenerationStatus`
- **resumenParaMatching**: resumen ≤500 palabras del perfil del usuario, generado por Bedrock, usado en scoring y en sugerencia de cargos
- **resumenGenerationStatus**: campo `Optional[str]` ya existente en el modelo Pydantic `Perfiles` (`backend/shared/models.py`), con valores `'pending'` \| `'complete'` \| `'failed'` \| `None`; único campo persistido que refleja el estado de generación del resumen (no existe ni se agrega un campo BOOL `resumenGenerating` en DynamoDB)
- **resumenGenerating**: campo booleano derivado, calculado solo en la respuesta HTTP de `GET /me/profile` a partir de `resumenGenerationStatus == 'pending'`; nunca persistido
- **Lambda "api"**: la única Lambda síncrona (FastAPI + Mangum) que sirve toda la API; en esta spec se invoca a sí misma de forma asíncrona como segundo modo de operación
- **Invocación asíncrona (Event)**: llamada `boto3` a `lambda.invoke(..., InvocationType='Event')`, que retorna de inmediato sin esperar el resultado de la ejecución invocada
- **JWT Authorizer**: validador Cognito que expone `userId` en `event.requestContext.authorizer.claims.sub`
- **Decisión de bloqueo (roles/suggest)**: lógica pura que determina si `POST /me/profile/roles/suggest` responde HTTP 424 o HTTP 200, en función de `resumenParaMatching` y `resumenGenerationStatus`

## Exclusiones

Explícitamente fuera de alcance de esta spec (cubierto por otras specs, no se toca aquí):

- **Terraform / despliegue de infraestructura**: cualquier cambio en configuración de Lambda (permisos IAM para `lambda:InvokeFunction` sobre sí misma, variables de entorno, memoria/timeout) se cubre en la spec separada `backend-fix-despliegue`. Esta spec asume que el permiso de auto-invocación ya existe o se gestiona ahí.
- **Inmutabilidad de `firstSeenAt`**: cubierta por la Tarea 8 de `backend-scan-y-scoring`. No se modifica en esta spec.

## Requirements

### Requirement 1: Alta idempotente de Suscripción vía POST /me/companies/{companyId}

**User Story:** As a user, I want to subscribe to a company from the catalog by its companyId, so that I can start monitoring its job openings without needing a prior subscription record to exist.

#### Acceptance Criteria

1. WHEN a user sends `POST /me/companies/{companyId}`, THE System SHALL extract `userId` from `event.requestContext.authorizer.claims.sub` (JWT authorizer claim), never from the request body or query parameters.
2. IF `companyId` (in any format or length) does not match an existing entry in the Empresas catalog, THEN THE System SHALL return HTTP 404 with `{"error": "company_not_found"}`, without creating or modifying any Suscripción record.
3. IF `companyId` exists in the Empresas catalog AND no Suscripción record exists for `(userId, companyId)`, THEN THE System SHALL create a new Suscripción with `activa = true` and `addedAt = now`, and return HTTP 201 with `{"companyId", "activa": true, "addedAt": ISO8601}`.
4. IF `companyId` exists in the Empresas catalog AND a Suscripción record exists for `(userId, companyId)` with `activa = true`, THEN THE System SHALL leave the record unchanged (no-op) and return HTTP 200 with `{"companyId", "activa": true, "addedAt"}` reflecting the unchanged, previously stored `addedAt`.
5. IF `companyId` exists in the Empresas catalog AND a Suscripción record exists for `(userId, companyId)` with `activa = false`, THEN THE System SHALL set `activa = true` and refresh `addedAt = now` (reactivation), reusing the same update pattern already implemented in `PUT /me/companies/{companyId}` (`toggle_subscription`, `backend/api/routes/companies.py`), and return HTTP 200 with `{"companyId", "activa": true, "addedAt": ISO8601}`.
6. THE System SHALL implement the decision among create, no-op, and reactivate as a pure function that receives the current subscription state (absent, `activa=true`, or `activa=false`) and returns the action to perform, decoupled from any DynamoDB call, so the decision logic can be unit-tested without mocking AWS.
7. Logging SHALL record `userId`, `companyId`, and the resulting action (`created` \| `no_op` \| `reactivated`); logging SHALL NOT include unrelated profile or CV content.
8. IF two or more requests for the same `(userId, companyId)` with no prior Suscripción record are received concurrently, THEN THE System SHALL ensure that exactly one Suscripción record exists for that `(userId, companyId)` pair after all requests complete, with no duplicate records created.
9. IF the DynamoDB write to create, update, or reactivate the Suscripción record fails, THEN THE System SHALL return HTTP 500 with `{"error": "subscription_write_failed"}`, without returning a success status code, and without leaving a partially written Suscripción record.


### Requirement 2: Disparo asíncrono de la generación de resumenParaMatching desde PUT /me/profile

**User Story:** As a user, I want the system to automatically regenerate my matching summary after I save my profile, so that role suggestions and scoring stay based on up-to-date information without me waiting for AI processing during the save.

#### Acceptance Criteria

1. WHEN a user successfully saves their profile via `PUT /me/profile` (persists `perfilEstructurado` and increments `profileVersion`), THE System SHALL additionally set `resumenGenerationStatus = 'pending'` in the Perfiles record for that `userId`, before returning the HTTP 200 response.
2. WHEN `PUT /me/profile` sets `resumenGenerationStatus = 'pending'`, THE System SHALL invoke asynchronously, via `boto3` `lambda.invoke(..., InvocationType='Event')`, the same Lambda "api", passing a payload that identifies the asynchronous resumen-generation mode and the `userId`, without blocking the HTTP response on the result of that invocation.
3. WHEN processing an asynchronous resumen-generation invocation payload, THE System SHALL read the Perfiles record for that `userId` at the time of processing (not a snapshot captured at invocation time) and generate `resumenParaMatching` from that current record's `perfilEstructurado` by invoking Bedrock using the model ID read from `BEDROCK_MODEL_SMALL` (via `backend/shared/bedrock.py`), and SHALL validate the Bedrock output against a Pydantic model before persisting it, so that a profile save occurring after invocation but before processing is reflected in the generated summary.
4. WHEN asynchronous resumen generation completes successfully, THE System SHALL persist the validated `resumenParaMatching` and set `resumenGenerationStatus = 'complete'` in the Perfiles record for that `userId`.
5. IF asynchronous resumen generation fails (Bedrock invocation error, or Pydantic validation failure after the standard single retry), THEN THE System SHALL set `resumenGenerationStatus = 'failed'` in the Perfiles record for that `userId`, without modifying the previously stored `resumenParaMatching` value.
6. THE System SHALL NOT add a new boolean field (e.g., `resumenGenerating`) to the `Perfiles` Pydantic model in `backend/shared/models.py`; `resumenGenerationStatus` (`Optional[str]`, values `'pending'` \| `'complete'` \| `'failed'` \| `None`), already defined there, SHALL remain the single persisted field representing generation state.
7. THE System SHALL NOT create a new SQS queue or a new Lambda function to implement this generation flow; it SHALL reuse the existing Lambda "api" with a second invocation mode (synchronous API Gateway requests vs. asynchronous self-invocation).
8. THE System SHALL update `.kiro/steering/contexto-tecnico-backend.md`: the `Perfiles` table section and the "Generación asíncrona de `resumenParaMatching`" section SHALL describe `resumenGenerationStatus` (string, states `'pending'` \| `'complete'` \| `'failed'` \| `null`) as the persisted field, instead of describing a persisted boolean `resumenGenerating`.
9. Logging for the asynchronous invocation and its completion SHALL record `userId` and the resulting `resumenGenerationStatus` transition (`pending` → `complete` or `pending` → `failed`); logging SHALL NOT include CV text or profile content, per the existing structured-logging rule.
10. IF the `boto3` `lambda.invoke(..., InvocationType='Event')` call in `PUT /me/profile` raises an exception before completing dispatch, THEN THE System SHALL catch the exception, SHALL NOT fail or roll back the HTTP 200 response already returned for the profile save, SHALL log the failure together with the `userId`, and SHALL set `resumenGenerationStatus = 'failed'` (not `'pending'`) in the Perfiles record for that `userId`, since at this point the System has confirmed the invocation was never dispatched — this is a confirmed failure, not an in-progress state. This failure path is automatically covered by the retry mechanism in Requirement 3 Criterion 7, without requiring any extension of that criterion to the `'pending'` status.

Nota (no automatizable): la invocación asíncrona real de `lambda.invoke` con `InvocationType='Event'` contra AWS no se mockea ni se cubre con un test automatizado en esta spec; su funcionamiento end-to-end se verifica manualmente una vez desplegada, según lo indicado en la sección de Consideraciones de Testing.

**Nota operativa — dependencia de despliegue con `backend-fix-despliegue`:**

Este requirement no es funcional en producción hasta que `backend-fix-despliegue` otorgue `lambda:InvokeFunction` sobre la propia función. Si esta spec se despliega antes, la invocación asíncrona fallará con `AccessDenied` al momento del despacho (Criterio 10 ya decide no fallar la respuesta HTTP ante esto), y el síntoma visible será `resumenGenerationStatus='failed'` de forma inmediata, indistinguible de un fallo real de Bedrock en los logs actuales. Con esta corrección, un permiso IAM faltante ya no deja al usuario atascado indefinidamente: el siguiente llamado a `POST /me/profile/roles/suggest` dispara el retry automáticamente (Requirement 3, Criterio 7), aunque ese retry también fallará por el mismo motivo de permisos hasta que se corrija el IAM en `backend-fix-despliegue`. Verificar el orden real de despliegue entre ambas specs antes de aplicar esta en producción.


### Requirement 3: Contrato de bloqueo de POST /me/profile/roles/suggest

**User Story:** As a user, I want to receive role suggestions using my existing matching summary even if a new summary is currently regenerating or failed to regenerate, so that a background regeneration process does not block me from getting suggestions.

#### Acceptance Criteria

1. IF `resumenParaMatching` is `None`, THEN THE System SHALL return HTTP 424 with `{"error": "resume_not_ready"}`, regardless of the value of `resumenGenerationStatus` (including when `resumenGenerationStatus` is `None`).
2. WHILE `resumenParaMatching` is not `None` AND `resumenGenerationStatus` equals `'pending'`, WHEN `POST /me/profile/roles/suggest` is called, THE System SHALL use the existing `resumenParaMatching` value to generate role suggestions and return HTTP 200, without blocking on the in-progress regeneration.
3. WHILE `resumenParaMatching` is not `None` AND `resumenGenerationStatus` equals `'failed'`, WHEN `POST /me/profile/roles/suggest` is called, THE System SHALL use the existing `resumenParaMatching` value to generate role suggestions and return HTTP 200, without automatically retrying resumen generation from this endpoint.
4. THE System SHALL implement the block/allow decision as a pure function that receives `(resumenParaMatching, resumenGenerationStatus)`, where `resumenGenerationStatus` may be `'pending'`, `'complete'`, `'failed'`, or `None`, and returns the decision, decoupled from any DynamoDB or Bedrock call, covering all cases above (Acceptance Criteria 1-3 and 6) so the decision logic can be unit-tested without mocking AWS.
5. THE System SHALL remove the condition `OR resumenGenerationStatus == 'pending'` from the blocking logic currently implemented in `suggest_roles` (`backend/api/routes/profile.py`); the blocking decision SHALL depend solely on whether `resumenParaMatching` is `None`.
6. WHILE `resumenParaMatching` is not `None` AND `resumenGenerationStatus` equals `'complete'` or `None`, WHEN `POST /me/profile/roles/suggest` is called, THE System SHALL use the existing `resumenParaMatching` value to generate role suggestions and return HTTP 200.
7. WHEN `POST /me/profile/roles/suggest` is called AND `resumenParaMatching` is `None` AND `resumenGenerationStatus` equals `'failed'`, THEN THE System SHALL, in addition to returning HTTP 424 per Criterion 1, invoke the same asynchronous resumen-generation invocation described in Requirement 2 Criterion 2 (`boto3` `lambda.invoke(..., InvocationType='Event')` targeting Lambda "api"), and set `resumenGenerationStatus = 'pending'` in the Perfiles record for that `userId` before returning the HTTP 424 response.
8. THE System SHALL NOT implement any automatic client-side or server-side retry loop that repeatedly re-calls `POST /me/profile/roles/suggest` after triggering the regeneration described in Criterion 7; whether and when to retry the request SHALL be the responsibility of the frontend (e.g., via polling `GET /me/profile` as already documented in `.kiro/steering/contexto-tecnico-backend.md`), not of this endpoint.
9. THE System SHALL update the docstring/comments of `suggest_roles` in `backend/api/routes/profile.py` to accurately describe the corrected blocking logic (Criteria 1-3, 6, and 7), removing any pre-existing docstring text describing a stale or incorrect check — specifically, the text pattern `resumenGenerationStatus == "generating"` (as currently reflected in the committed `frontend/openapi/openapi.json` and `frontend/src/api/generated/schema.d.ts`), which does not correspond to any code path; the real, corrected logic checks only whether `resumenParaMatching` is `None` (plus the additional side effect in Criterion 7 for the `resumenParaMatching is None AND resumenGenerationStatus == 'failed'` case).


### Requirement 4: Corrección del prefijo de rutas de roles (/me/roles → /me/profile/roles)

**User Story:** As a frontend developer, I want the backend's actual roles endpoints to match the documented and already-generated OpenAPI routes, so that the frontend's generated API client works without a mismatch between code and documentation.

#### Acceptance Criteria

1. THE System SHALL define `roles_router` with `prefix="/me/profile/roles"` in `backend/api/routes/profile.py`, replacing the current `prefix="/me/roles"`.
2. THE System SHALL expose `POST /me/profile/roles/suggest` (function `suggest_roles`) and `PUT /me/profile/roles` (function `save_roles`) under the prefix defined in Criterion 1.
3. THE System SHALL update every occurrence of the literal old route text (`/me/roles/suggest`, `/me/roles`) that appears in comments or docstrings within `backend/api/routes/profile.py` — including the module-level docstring, function docstrings, and section-header comments — to the corresponding new route text (`/me/profile/roles/suggest`, `/me/profile/roles`), without altering any other text in those comments or docstrings.
4. THE System SHALL update `backend/tests/test_profile.py` so that: (a) every `client.post("/me/roles/suggest")` call becomes `client.post("/me/profile/roles/suggest")`; (b) every `client.put("/me/roles", ...)` call becomes `client.put("/me/profile/roles", ...)`; and (c) every test function docstring referencing the old route text (`/me/roles/suggest`, `/me/roles`) is updated to reference the corresponding new route text; without altering any other assertions or test logic.
5. WHEN `python scripts/export-openapi.py` is executed after Criteria 1-2 of this requirement have been applied, THE regenerated `frontend/openapi/openapi.json` SHALL contain the path keys `/me/profile/roles/suggest` and `/me/profile/roles` with the same path key names as those already present in the currently committed `frontend/openapi/openapi.json` (i.e., the prefix correction alone SHALL introduce no new or renamed path keys for these two routes). THE System SHALL NOT require a zero-diff comparison of the entire `openapi.json` file, because: (a) the currently committed file already contains a pre-existing docstring inaccuracy in the `suggest_roles` description (`resumenGenerationStatus == "generating"`), which does not match any value ever written by the code (the real, pre-existing check compares against `"pending"`) and which Requirement 3 Criterion 9 corrects; and (b) Requirements 2 and 3 of this document change the actual documented behavior of `save_profile` and `suggest_roles`, so their description text is expected to change in the regenerated file relative to what is committed today.
6. THE System SHALL register `profile.roles_router` in `backend/main.py` via `app.include_router(profile.roles_router)` without passing an additional `prefix` argument, relying solely on the prefix defined on the router itself in `backend/api/routes/profile.py`.
7. THE System SHALL NOT modify the closed documents `.kiro/specs/backend-core/requirements.md`, `.kiro/specs/backend-core/design.md`, and `.kiro/specs/backend-core/tasks.md` as part of this route-prefix correction; those documents are historical records of already-executed work, not live code.


## Consideraciones de Testing

Aplicando el criterio de `.kiro/steering/pitfalls.md` (solo funciones puras para lógica de negocio nueva, sin suite de mocks de AWS):

- **Requirement 1**: cubrir con tests de función pura la decisión create \| no-op \| reactivate dado el estado actual de la Suscripción (ausente, activa, inactiva).
- **Requirement 3**: cubrir con tests de función pura los cuatro casos: (a) `resumenParaMatching=None` (cualquier `resumenGenerationStatus`, incluyendo `None`) → bloquear (HTTP 424); (b) `resumenParaMatching` existente + `'pending'` → permitir (HTTP 200); (c) `resumenParaMatching` existente + `'failed'` → permitir (HTTP 200); (d) `resumenParaMatching` existente + `'complete'` o `None` → permitir (HTTP 200); (e) `resumenParaMatching=None` + `resumenGenerationStatus == 'failed'` → bloquear (HTTP 424) Y disparar la invocación asíncrona de regeneración, actualizando `resumenGenerationStatus` a `'pending'` antes de responder (Criterio 7); verificar que este quinto caso no dispare ningún retry loop automático (Criterio 8).
- **Tests de integración de endpoint** (FastAPI `TestClient` + `Mock()` de tabla DynamoDB, sin `moto`): seguir el patrón ya existente en `backend/tests/test_profile.py` y `backend/tests/test_companies.py`. Esto no viola el criterio "solo funciones puras", ya que ese patrón (TestClient + Mock en lugar de moto) ya es el estándar aceptado en el repo para tests de endpoint.
- **Invocación asíncrona real (`lambda.invoke`, `InvocationType='Event'`)**: NO se mockea ni se cubre con un test automatizado. Se verifica manualmente contra AWS una vez desplegado. Esto es una nota operativa, no un criterio de aceptación automatizable.


## End of Requirements

---

**Next Steps:**
1. User reviews requirements for completeness and clarity
2. User may request changes, clarifications, or mark as complete
3. After approval, workflow moves to Design phase
