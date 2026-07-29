# Implementation Plan: Backend Fix — Integración Frontend

## Overview

Cuatro correcciones independientes sobre la Lambda "api" (FastAPI + Mangum, Python 3.12) ya existente: (1) alta idempotente de Suscripción vía `POST /me/companies/{companyId}`, (2) disparo asíncrono de `resumenParaMatching` desde `PUT /me/profile`, (3) corrección del contrato de bloqueo 424 de `POST /me/profile/roles/suggest`, y (4) corrección del prefijo de rutas de `roles_router`. No hay cambios de infraestructura ni de esquema DynamoDB.

Orden de ejecución:

0. **Los Checkpoints (Tareas 3, 5, 7, 9) son gates reales, no puntos de revisión informativos**: ninguna tarea de un grupo posterior se ejecuta hasta que el checkpoint del grupo anterior confirma que todos sus tests pasan. Esta spec sigue el mismo precedente que `backend-core/tasks.md` (ya ejecutada en este repo), cuyo Task Dependency Graph tampoco mezcla nunca tareas de grupos separados por un checkpoint. Como consecuencia, el Grupo Suscripción (Tarea 2) y el Grupo Resumen asíncrono (Tarea 4) —aunque no comparten ningún archivo y podrían ejecutarse en paralelo en términos de dependencias de código— NO se paralelizan entre sí en el grafo, porque el Checkpoint 3 los separa como una barrera de ejecución secuencial.
1. La dependencia `hypothesis` se agrega primero (Tarea 1), porque las tareas de property-based test de los Grupos 2 y 6 la requieren en tiempo de ejecución de los tests, no solo lógicamente.
2. **Grupo Suscripción** (Tarea 2, Requirement 1) es completamente independiente del resto: toca `backend/shared/errors.py` y `backend/api/routes/companies.py`, archivos que ningún otro grupo modifica.
3. **Grupo Resumen asíncrono** (Tarea 4, Requirement 2) implementa primero el modelo Pydantic y el helper compartido `_trigger_async_resumen_generation`, porque el **Grupo Roles/suggest** (Tarea 6, Requirement 3) reutiliza ese mismo helper para su rama `BLOCK_AND_RETRY` — es una dependencia real de código, no solo de diseño.
4. **Grupo Roles/suggest** (Tarea 6, Requirement 3) se ejecuta después del Grupo Resumen porque depende del helper `_trigger_async_resumen_generation` ya implementado ahí.
5. **Grupo Prefijo de rutas** (Tarea 8, Requirement 4) es mecánicamente independiente y podría iniciarse en paralelo con los grupos 2/4/6, pero su último paso —regenerar `openapi.json`/`schema.d.ts`— se deja intencionalmente al final del documento, después de que los docstrings de `save_profile` (Grupo Resumen) y `suggest_roles` (Grupo Roles/suggest) en `profile.py` ya quedaron en su texto final, para que la regeneración capture la documentación correcta y no una versión intermedia.
6. Todas las tareas que escriben en `backend/api/routes/profile.py` (helper de resumen, integración en `save_profile`, función de decisión de roles, integración en `suggest_roles`, cambio de prefijo) se serializan entre sí porque son ediciones del mismo archivo, aunque su lógica de negocio sea independiente — ver el grafo de dependencias al final.

## Tasks

- [ ] 1. Dependencia de test para property-based testing
  - [ ] 1.1 Agregar `hypothesis` a `backend/pyproject.toml`
    - Agregar `"hypothesis>=6.100.0"` a `[project.optional-dependencies].dev`, junto a `pytest`/`pytest-cov` ya existentes
    - No agregar a `requirements.txt` de producción (no se usa en runtime Lambda)
    - _Requirements: 1.6, 3.4_

- [ ] 2. Alta idempotente de Suscripción — `POST /me/companies/{companyId}`
  - [ ] 2.1 Agregar excepción `SubscriptionWriteFailed` y parametrizar `CompanyNotFound` en `backend/shared/errors.py`
    - Crear `SubscriptionWriteFailed(AppException)`: `error_code="subscription_write_failed"`, `http_status=500`
    - Modificar `CompanyNotFound.__init__` para aceptar `http_status: int = 400` (valor por defecto preserva el comportamiento exacto de `toggle_subscription`, que sigue sin pasar el argumento)
    - _Requirements: 1.2, 1.9_

  - [ ] 2.2 Implementar función pura `decide_subscription_action` y enum `SubscriptionAction` en `backend/api/routes/companies.py`
    - `SubscriptionAction(str, Enum)`: `CREATE = "created"`, `NO_OP = "no_op"`, `REACTIVATE = "reactivated"`
    - `decide_subscription_action(existing_activa: Optional[bool]) -> SubscriptionAction`: `None` → `CREATE`, `True` → `NO_OP`, `False` → `REACTIVATE`; sin llamadas a DynamoDB
    - _Requirements: 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.3 Escribir property-based tests para Property 1 y Property 2 en `backend/tests/test_companies.py`
    - **Property 1: Decisión de alta de suscripción es exhaustiva y correcta por rama** — `@given(existing_activa=st.one_of(st.none(), st.booleans()))`, `@settings(max_examples=100)`
    - **Property 2: El alta de suscripción es idempotente (convergencia a no-op)** — para cualquier `existing_activa` inicial, tras aplicar la acción resultante (deja `activa=True`), `decide_subscription_action(True)` siempre retorna `NO_OP`
    - **Validates: Requirements 1.3, 1.4, 1.5, 1.6**

  - [ ] 2.4 Implementar modelo `SubscriptionUpsertResponse` en `backend/api/routes/companies.py`
    - `BaseModel` con `companyId: str`, `activa: bool`, `addedAt: str`
    - _Requirements: 1.3, 1.4, 1.5_

  - [ ] 2.5 Implementar endpoint `POST /me/companies/{companyId}` (`create_subscription`) en `backend/api/routes/companies.py`
    - Registrar en `subscriptions_router` (ya definido con `prefix="/me/companies"`); extraer `user_id` vía `Depends(get_current_user_id)` (nunca de body/query)
    - Validar que `companyId` existe en Empresas; si no, `raise CompanyNotFound(company_id=company_id, http_status=404)`
    - Leer estado actual de Suscripciones vía `get_item`, llamar `decide_subscription_action`
    - Rama `CREATE`: `put_item` con `ConditionExpression="attribute_not_exists(userId)"`; capturar `ClientError` con código `ConditionalCheckFailedException`, re-leer el registro con `get_item` y re-decidir la acción (cae a `NO_OP`/`REACTIVATE`)
    - Implementar helper interno `_apply_no_op_or_reactivate(action, existing, table, user_id, company_id, now)`: `NO_OP` no escribe nada y retorna el `addedAt` almacenado; `REACTIVATE` hace `update_item` (`SET activa = :true, addedAt = :now`, mismo patrón que `toggle_subscription`)
    - Cualquier `ClientError` no relacionado con `ConditionalCheckFailedException` en cualquier escritura → `raise SubscriptionWriteFailed()`
    - Retornar HTTP 201 en creación nueva, HTTP 200 en no-op/reactivate, con `SubscriptionUpsertResponse`
    - Loguear `user_id`, `company_id`, y `action.value` (`created`\|`no_op`\|`reactivated`); nunca contenido de perfil/CV
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [ ]* 2.6 Escribir tests de ejemplo para `POST /me/companies/{companyId}` en `backend/tests/test_companies.py`
    - Casos: 201 create (sin registro previo), 200 no-op (registro con `activa=True`), 200 reactivate (registro con `activa=False`), 404 `company_not_found` (companyId inexistente en Empresas), 500 `subscription_write_failed` (fallo de escritura DynamoDB no relacionado con condición), y la rama de `ConditionalCheckFailedException` en el `put_item` inicial (verificar que cae correctamente a no-op/reactivate sin crear un segundo registro)
    - Seguir el patrón `TestClient` + `Mock()` de tabla ya usado en el archivo (sin `moto`)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 1.9_

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Disparo asíncrono de generación de `resumenParaMatching`
  - [ ] 4.1 Agregar modelo `ResumenParaMatchingOutput` en `backend/shared/models.py`
    - `BaseModel` con `resumen: str = Field(..., min_length=1)`, `model_config = ConfigDict(extra="ignore")`
    - No se agrega ningún campo booleano nuevo (`resumenGenerating`) al modelo `Perfiles`; ese modelo permanece sin cambios
    - _Requirements: 2.3, 2.6_

  - [ ] 4.2 Agregar discriminador `mode == "async_resumen_generation"` en `backend/main.py::handler()`
    - Agregar la rama `if event.get("mode") == "async_resumen_generation": return _handle_async_resumen_generation(event, context)`, en paralelo a la rama ya existente `event.get("source") == "eventbridge-scheduler"`
    - _Requirements: 2.2, 2.3, 3.7_

  - [ ] 4.3 Implementar helper compartido `_trigger_async_resumen_generation` en `backend/api/routes/profile.py`
    - Firma: `_trigger_async_resumen_generation(user_id: str) -> str`, retorna `'pending'`\|`'failed'`\|`'unknown'`
    - Un único `try/except` externo envuelve TODO el cuerpo (Paso 1: `update_item` de `Perfiles` con `resumenGenerationStatus = 'pending'`; Paso 2: `boto3.client("lambda").invoke(FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"], InvocationType="Event", Payload=...)` con payload `{"mode": "async_resumen_generation", "userId": user_id}`)
    - Orden estricto: escribir `'pending'` ANTES de invocar (para no pisar un resultado `'complete'`/`'failed'` que el worker asíncrono ya haya escrito)
    - Si el bloque anterior lanza cualquier excepción: loguear, e intentar una segunda escritura de `resumenGenerationStatus = 'failed'`, envuelta en su propio `try/except` interno; si esa segunda escritura también falla, loguear y retornar `'unknown'` sin propagar ninguna excepción al caller
    - _Requirements: 2.1, 2.2, 2.9, 2.10_

  - [ ] 4.4 Implementar helper de prompt `_prepare_resumen_prompt` en `backend/api/routes/profile.py`
    - Recibe `perfilEstructurado` (dict) y retorna el prompt para Bedrock, incluyendo la instrucción "≤500 palabras" como texto del prompt (no como `max_length` de Pydantic)
    - Colocarlo junto a `_prepare_cv_parsing_prompt` y `_prepare_roles_suggestion_prompt` ya existentes
    - _Requirements: 2.3_

  - [ ] 4.5 Implementar `_handle_async_resumen_generation` en `backend/main.py`
    - Imports diferidos dentro de la función (mismo patrón que `_handle_programmed_scan`): `get_dynamodb_table`, `get_bedrock_client`, `ResumenParaMatchingOutput`, `_prepare_resumen_prompt`
    - Lee `Perfiles` por `userId` EN ESE MOMENTO (no una foto tomada al invocar); si no hay `perfilEstructurado`, trátalo como fallo
    - Invoca `bedrock_client.invoke_with_retry` con `ResumenParaMatchingOutput` y `BEDROCK_MODEL_SMALL`
    - Éxito: `update_item` con `SET resumenParaMatching = :resumen, resumenGenerationStatus = :status` (`'complete'`)
    - Fallo (Bedrock o validación Pydantic tras el retry estándar): `update_item` con SOLO `resumenGenerationStatus = 'failed'`, sin modificar `resumenParaMatching` previo
    - Retorna siempre `{"statusCode": 200, ...}` a nivel de handler Lambda (invocación `Event`, sin caller HTTP esperando)
    - Loguear `user_id` y la transición de `resumenGenerationStatus`; nunca CV/perfil
    - _Requirements: 2.3, 2.4, 2.5, 2.9_

  - [ ] 4.6 Integrar `_trigger_async_resumen_generation(user_id)` al final de `save_profile` en `backend/api/routes/profile.py`
    - Agregar la llamada justo antes del `return response_data` existente, sin modificar el resto de la función (persistencia de `perfilEstructurado`/`profileVersion`/`updatedAt` permanece igual; la respuesta HTTP sigue siendo solo `{"profileVersion", "updatedAt"}`)
    - _Requirements: 2.1, 2.2_

  - [ ] 4.7 Actualizar `.kiro/steering/contexto-tecnico-backend.md`
    - En la sección `Perfiles` y en la sección "Generación asíncrona de `resumenParaMatching`", reemplazar toda referencia a un campo booleano persistido `resumenGenerating` por `resumenGenerationStatus` (`'pending'`\|`'complete'`\|`'failed'`\|`null`)
    - Aclarar que `resumenGenerating` (booleano) sigue existiendo únicamente como campo derivado en la respuesta HTTP de `GET /me/profile`, nunca persistido
    - _Requirements: 2.8_

  - [ ]* 4.8 Escribir tests de ejemplo para `_trigger_async_resumen_generation` en `backend/tests/test_profile.py`
    - (a) camino feliz: `update_item('pending')` ocurre antes de `invoke()`, y `invoke()` se llama exactamente una vez con el payload esperado, retorna `'pending'`
    - (b) `invoke()` lanza excepción → segunda escritura a `'failed'` tiene éxito → retorna `'failed'`, sin propagar la excepción
    - (c) la propia escritura de `'pending'` (Paso 1) lanza excepción → nunca se llega a llamar `invoke()` → se intenta igualmente la escritura de `'failed'`
    - (d) la segunda escritura (de `'failed'`) también falla → retorna `'unknown'` sin propagar ninguna excepción
    - Mockear `boto3.client("lambda")` y la tabla `Perfiles` con `Mock()`, sin `moto`
    - _Requirements: 2.1, 2.2, 2.9, 2.10_

  - [ ]* 4.9 Escribir tests de ejemplo para `_handle_async_resumen_generation` en `backend/tests/test_main.py` (archivo nuevo)
    - Caso éxito: Bedrock retorna un `ResumenParaMatchingOutput` válido → se persiste `resumenParaMatching` + `status='complete'`
    - Caso fallo de invocación de Bedrock → `status='failed'`, sin modificar `resumenParaMatching` previo
    - Caso fallo de validación Pydantic tras el retry → `status='failed'`, sin modificar `resumenParaMatching` previo
    - Caso adicional: verificar que el discriminador `mode == "async_resumen_generation"` en `handler()` despacha a esta función
    - Mockear Bedrock y la tabla `Perfiles` con `Mock()`, siguiendo el patrón ya usado en `test_profile.py`
    - _Requirements: 2.3, 2.4, 2.5_

  - [ ]* 4.10 Escribir test de ejemplo de `save_profile` disparando el trigger en `backend/tests/test_profile.py`
    - Verificar que, tras un `PUT /me/profile` exitoso, se invoca `_trigger_async_resumen_generation` con el `user_id` correcto (mockeando el helper o sus dependencias internas), sin alterar la respuesta HTTP existente (`{"profileVersion", "updatedAt"}`)
    - _Requirements: 2.1, 2.2_

- [ ] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Corrección del contrato de bloqueo de `POST /me/profile/roles/suggest`
  - [ ] 6.1 Implementar función pura `decide_roles_suggest_action` y enum `RolesSuggestDecision` en `backend/api/routes/profile.py`
    - `RolesSuggestDecision(str, Enum)`: `ALLOW = "allow"`, `BLOCK = "block"`, `BLOCK_AND_RETRY = "block_and_retry"`
    - `decide_roles_suggest_action(resumen_para_matching: Optional[str], resumen_generation_status: Optional[str]) -> RolesSuggestDecision`: `resumen is not None` → `ALLOW` (para cualquier `status`); `resumen is None and status == 'failed'` → `BLOCK_AND_RETRY`; `resumen is None and status != 'failed'` (incluye `None`) → `BLOCK`; sin llamadas a DynamoDB ni Bedrock
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7_

  - [ ]* 6.2 Escribir property-based tests para Property 3 y Property 4 en `backend/tests/test_profile.py`
    - **Property 3: Decisión de bloqueo de roles/suggest es exhaustiva y correcta por rama** — `@given(resumen=st.one_of(st.none(), st.text(min_size=1)), status=st.one_of(st.none(), st.sampled_from(["pending", "complete", "failed"])))`
    - **Property 4: La decisión de bloqueo de roles/suggest es independiente del contenido del resumen** — metamórfica: `@given(resumen_a=st.text(min_size=1, max_size=2000), resumen_b=st.text(min_size=1, max_size=2000), status=...)`, verifica `decide_roles_suggest_action(resumen_a, status) == decide_roles_suggest_action(resumen_b, status)`
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6, 3.7**

  - [ ] 6.3 Integrar `decide_roles_suggest_action` en `suggest_roles` en `backend/api/routes/profile.py`
    - Reemplazar la condición actual `resumen is None or generation_status == "pending"` por `decision = decide_roles_suggest_action(resumen, generation_status)`
    - Rama `BLOCK_AND_RETRY`: llamar `_trigger_async_resumen_generation(user_id)` y luego `raise ResumeNotReady()`
    - Rama `BLOCK`: `raise ResumeNotReady()` directamente, sin disparar ningún trigger
    - Rama `ALLOW`: continúa el flujo existente (invocar Bedrock, validar `RolesSuggestions`, retornar 200) sin cambios
    - Actualizar el docstring de `suggest_roles`, eliminando la referencia a `resumenGenerationStatus == "generating"` y describiendo la lógica corregida (Criterios 3.1-3.3, 3.6, 3.7)
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 6.4 Escribir tests de ejemplo actualizados de `suggest_roles` en `backend/tests/test_profile.py`
    - (a) `resumenParaMatching=None`, cualquier `status` incluyendo `None` (excepto `'failed'`) → HTTP 424, sin disparar trigger
    - (b) `resumenParaMatching` existente + `status='pending'` → HTTP 200 con sugerencias
    - (c) `resumenParaMatching` existente + `status='failed'` → HTTP 200 con sugerencias, sin retry automático
    - (d) `resumenParaMatching` existente + `status='complete'` o `None` → HTTP 200 con sugerencias
    - (e) `resumenParaMatching=None` + `status='failed'` → HTTP 424 Y se dispara `_trigger_async_resumen_generation` (mockeado), verificando que no se produce ningún loop de retry automático adicional
    - _Requirements: 3.1, 3.2, 3.3, 3.6, 3.7, 3.8_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Corrección de prefijo de rutas de roles
  - [ ] 8.1 Cambiar el prefijo de `roles_router` y actualizar docstrings en `backend/api/routes/profile.py`
    - `roles_router = APIRouter(prefix="/me/roles", ...)` → `roles_router = APIRouter(prefix="/me/profile/roles", ...)`
    - Reemplazar todo literal `/me/roles/suggest` → `/me/profile/roles/suggest` y `/me/roles` → `/me/profile/roles` en el docstring del módulo y en los docstrings de `suggest_roles`/`save_roles`, sin alterar el resto del texto
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 8.2 Actualizar `backend/tests/test_profile.py` con las rutas corregidas
    - Todo `client.post("/me/roles/suggest")` → `client.post("/me/profile/roles/suggest")`
    - Todo `client.put("/me/roles", ...)` → `client.put("/me/profile/roles", ...)`
    - Docstrings de tests que mencionen la ruta vieja, actualizados a la ruta nueva, sin alterar otras aserciones o lógica de test
    - _Requirements: 4.4_

  - [ ] 8.3 Regenerar `frontend/openapi/openapi.json` y `frontend/src/api/generated/schema.d.ts`
    - Ejecutar `python scripts/export-openapi.py` seguido del script de generación de tipos ya existente en el repo
    - Verificar que las path keys `/me/profile/roles/suggest` y `/me/profile/roles` aparecen en el archivo regenerado con los mismos nombres de path key que ya existían para estas dos rutas (no se exige diff cero de todo el archivo, ya que las Tareas 4 y 6 cambian legítimamente el texto de descripción de `save_profile`/`suggest_roles`)
    - _Requirements: 4.5, 4.6_

- [ ] 9. Checkpoint final - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- **Orden Grupo 1 (hypothesis) antes de property tests**: es una dependencia real de ejecución (`import hypothesis` fallaría en los tests de las Tareas 2.3 y 6.2 si el paquete no está instalado), no solo una preferencia de organización.
- **Checkpoints como gates reales (no informativos)**: los Checkpoints de las Tareas 3, 5, 7 y 9 bloquean el inicio de cualquier tarea del grupo siguiente hasta que todos los tests del grupo anterior pasen. El Task Dependency Graph refleja esto estrictamente: ninguna wave mezcla tareas de dos grupos separados por un checkpoint, siguiendo el mismo patrón ya usado en `backend-core/tasks.md`. Esto significa que el Grupo Suscripción (Tarea 2) y el Grupo Resumen asíncrono (Tarea 4), aunque no comparten archivos y son independientes en términos de dependencias de código, se ejecutan en waves secuenciales separadas por el Checkpoint 3, no en paralelo — se prioriza la semántica de gate real sobre la paralelización máxima posible.
- **Serialización de `backend/api/routes/profile.py`**: las Tareas 4.3, 4.4, 4.6, 6.1, 6.3 y 8.1 editan el mismo archivo; aunque su lógica de negocio es independiente entre sí, el grafo de dependencias las serializa en waves distintas tanto por evitar conflictos de edición concurrente como por los Checkpoints 5 y 7, que actúan como gates entre los segmentos a los que pertenecen (4.3/4.4/4.6 en el Segmento B, 6.1/6.3 en el Segmento C, 8.1 en el Segmento D). Esto es lo que fuerza que la Tarea 8.1 (prefijo) quede después de que los docstrings de `save_profile` (4.6) y `suggest_roles` (6.3) ya estén en su versión final — coincide además con el requisito explícito de que la regeneración de OpenAPI (8.3) sea el último paso.
- **`backend/tests/test_main.py` es un archivo nuevo** (no existe hoy en el repo): se crea en la Tarea 4.9 exclusivamente para los tests de `_handle_async_resumen_generation` y del discriminador `mode` en `handler()`, sin tocar los tests existentes de `_handle_programmed_scan` en otro archivo.
- **Fuera de alcance** (ver Exclusiones de `requirements.md`): cualquier cambio de Terraform/IAM (incluyendo el permiso `lambda:InvokeFunction` de la función sobre sí misma) — se gestiona en `backend-fix-despliegue`; la inmutabilidad de `firstSeenAt` — cubierta por `backend-scan-y-scoring`. Ninguna tarea de este plan modifica infraestructura ni esos otros módulos.
- **Sin moto/localstack**: todos los tests de endpoint e integración usan `TestClient` + `unittest.mock.Mock()` sobre las tablas DynamoDB, siguiendo el patrón ya estándar en `test_profile.py`/`test_companies.py`. La invocación real de `lambda.invoke(..., InvocationType='Event')` contra AWS no se mockea con `moto` ni se cubre con un test automatizado end-to-end (Requirement 2, nota operativa); solo se mockea el cliente `boto3.client("lambda")` para verificar que se llama con los parámetros esperados.
- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido; cubren property-based tests y tests de ejemplo. Las tareas de nivel superior nunca están marcadas como opcionales.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "2.2", "2.4"] },
    { "id": 1, "tasks": ["2.3", "2.5"] },
    { "id": 2, "tasks": ["2.6"] },
    { "id": 3, "tasks": ["4.1", "4.2", "4.3", "4.4", "4.7"] },
    { "id": 4, "tasks": ["4.5", "4.6"] },
    { "id": 5, "tasks": ["4.8", "4.9", "4.10"] },
    { "id": 6, "tasks": ["6.1"] },
    { "id": 7, "tasks": ["6.2", "6.3"] },
    { "id": 8, "tasks": ["6.4"] },
    { "id": 9, "tasks": ["8.1"] },
    { "id": 10, "tasks": ["8.2"] },
    { "id": 11, "tasks": ["8.3"] }
  ]
}
```
