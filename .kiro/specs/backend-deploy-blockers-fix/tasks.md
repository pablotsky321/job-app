# Implementation Plan

**Leyenda de verificabilidad** (se repite en cada tarea como anotación `_Verificable:_`):
- 🟢 **LOCAL** — verificable completamente en esta sesión (imports Python, `terraform validate`/`plan`, `pytest`, inspección de archivos/strings). No requiere AWS real ni credenciales.
- 🔴 **AWS-REAL** — requiere una cuenta AWS real y queda **pendiente de verificación post-implementación**. No se puede cerrar en esta sesión.

---

## Fase 1 — Verificación exploratoria (contraejemplos) de cada bug condition, ANTES de tocar código

- [x] 1. Exploration test — **Property 1: Bug Condition** - Handler/Zip Consistency (`api`/`orquestador`)
  - **IMPORTANTE**: ejecutar ANTES de tocar `terraform/modules/lambda/main.tf` o `backend/main.py`.
  - Replicar localmente la estructura de zip esperada por el `handler` actual: crear un directorio temporal con `backend/` copiado dentro, y ejecutar `python -c "import main"` desde ese directorio → debe fallar con `ModuleNotFoundError: No module named 'main'`.
  - Ejecutar `python -c "from backend.main import handler"` desde el directorio padre (raíz del repo) → debe resolver sin error, confirmando que `backend.main.handler` ya existe y es el entry point correcto.
  - Documentar el contraejemplo obtenido (mensaje de error exacto) como evidencia de C1.
  - **Resultado esperado**: el primer comando FALLA (confirma el bug), el segundo comando PASA (confirma la solución objetivo).
  - _Verificable: 🟢 LOCAL_
  - _Bug_Condition: isBugCondition para target IN {api, orquestador} (design.md, Formal Specification)_
  - _Requirements: 1.1, 1.2_
  - **Validates: Property 1**

- [x] 2. Exploration test — **Property 2: Bug Condition** - Handler Name Match (`scan_worker`/`scoring_worker`)
  - **IMPORTANTE**: ejecutar ANTES de renombrar `handler_scan_worker`/`handler_scoring_worker`.
  - Ejecutar `python -c "from backend.workers.scan_worker import handler"` sobre el código actual (sin renombrar) → debe fallar con `ImportError: cannot import name 'handler'`.
  - Ejecutar `python -c "from backend.workers.scoring_worker import handler"` sobre el código actual → debe fallar de la misma forma.
  - Documentar ambos mensajes de error como contraejemplos de C2.
  - **Resultado esperado**: ambos comandos FALLAN (confirman el bug).
  - _Verificable: 🟢 LOCAL_
  - _Bug_Condition: isBugCondition para target IN {scan_worker, scoring_worker}_
  - _Requirements: 1.3, 1.4_
  - **Validates: Property 2**

- [x] 3. Exploration check — **Property 3: Bug Condition** - Ausencia de script de empaquetado (C3)
  - Ejecutar un listado de `scripts/` y confirmar que solo existe `export-openapi.py` (sin relación con empaquetado de Lambdas), y que no existe `Makefile`/`build.sh`/`setup.py` en la raíz del repo.
  - Confirmar que los 3 workflows en `.github/workflows/` (`backend-deploy.yml`, `frontend-deploy.yml`, `terraform-apply.yml`) están vacíos (0 líneas).
  - Documentar la ausencia como contraejemplo de C3 (no hay comando que "falle" per se — es una verificación de inexistencia).
  - _Verificable: 🟢 LOCAL_
  - _Bug_Condition: isBugCondition para target == "packaging_pipeline"_
  - _Requirements: 1.5_
  - **Validates: Property 3**

- [x] 4. Exploration check — **Property 4: Bug Condition** - Permiso IAM faltante para auto-invocación (C4)
  - Inspeccionar `terraform/modules/iam/main.tf`, sección `aws_iam_role_policy.api_policy`, y confirmar por lectura literal que ningún statement contiene `lambda:InvokeFunction`.
  - Documentar la ausencia del statement (cita de archivo+línea) como contraejemplo estático de C4.
  - **Nota**: la confirmación en runtime (`AccessDeniedException` real al invocar `PUT /me/profile`) NO es verificable en esta sesión — queda marcada como pendiente en la tarea 4.1.
  - _Verificable: 🟢 LOCAL (inspección estática)_
  - _Verificable adicional: 🔴 AWS-REAL — `AccessDeniedException` en ejecución real, pendiente post-implementación_
  - _Bug_Condition: isBugCondition para target == "api_self_invocation"_
  - _Requirements: 1.6_
  - **Validates: Property 4**

- [x] 5. Exploration check — **Property 6: Bug Condition** - Patrón S3 roto (bucket de código Lambda, C5)
  - Evaluar el patrón `arn:aws:s3:::*-lambda-code-bucket` (y su variante `/*`) contra el nombre real `job-search-lambda-code-5155151158151` mediante comparación literal de strings (o un fnmatch local) → confirmar que NO matchea porque el nombre real no termina en `-lambda-code-bucket`.
  - Documentar el resultado de la comparación como contraejemplo de C5.
  - _Verificable: 🟢 LOCAL (comparación de strings, sin AWS)_
  - _Bug_Condition: isBugCondition para target == "ci_pipeline_s3_upload" (sub-patrón lambda-code)_
  - _Requirements: (contexto de 2.8, ver bugfix.md sección "Nota — nombres reales de bucket")_
  - **Validates: Property 6**

- [x] 6. Exploration check — **Property 6.1: Bug Condition** - Patrón S3 roto (bucket de Terraform state, C6)
  - Evaluar el patrón `arn:aws:s3:::*-terraform-state-bucket` (y su variante `/*`) contra el nombre real `job-search-terraform-state-5543569870` → confirmar que NO matchea porque el nombre real no termina en `-terraform-state-bucket`.
  - Documentar el resultado como contraejemplo de C6.
  - _Verificable: 🟢 LOCAL (comparación de strings, sin AWS)_
  - _Bug_Condition: isBugCondition para target == "ci_pipeline_s3_upload" (sub-patrón terraform-state)_
  - _Requirements: (contexto de 2.8.1)_
  - **Validates: Property 6.1**

---

## Fase 2 — Preservation baseline (ANTES de tocar código)

- [x] 7. Preservation baseline — **Property 7: Preservation** - Baseline de `pytest` y `terraform plan`
  - **IMPORTANTE**: capturar el estado ANTES de cualquier cambio de código/Terraform, siguiendo la metodología observation-first.
  - Ejecutar la suite completa `pytest` sobre el repo actual (sin modificar) y registrar el conteo exacto de `passed`/`failed`/`skipped`. Si hay fallos preexistentes no relacionados con este fix (ej. `test_logging_config.py`), documentarlos explícitamente aquí antes de excluirlos de comparaciones futuras.
  - Ejecutar `terraform plan` sobre el módulo `lambda` y sobre el módulo `iam` (estado actual, sin cambios) y guardar el resultado como referencia de "no-diff" para comparar después del fix.
  - **Resultado esperado**: ambos comandos se ejecutan y su salida se guarda como baseline — no se espera fallo aquí.
  - _Verificable: 🟢 LOCAL_
  - _Requirements: 2.3.1, 2.4.1, 3.1, 3.2, 3.3, 3.4_
  - **Validates: Property 7**

---

## Fase 3 — Implementación

- [x] 8. Fix Bloqueador 2 — Renombrar `handler_scan_worker`/`handler_scoring_worker` → `handler`
  - [x] 8.1 Renombrar `def handler_scan_worker(event, context)` → `def handler(event, context)` en `backend/workers/scan_worker.py` (última función, sección "LAMBDA HANDLER"). Cuerpo sin cambios.
    - _Bug_Condition: isBugCondition para scan_worker (C2)_
    - _Requirements: 2.3_
  - [x] 8.2 Renombrar `def handler_scoring_worker(event, context)` → `def handler(event, context)` en `backend/workers/scoring_worker.py` (línea ~132, sección "MAIN HANDLER"). Cuerpo sin cambios.
    - _Bug_Condition: isBugCondition para scoring_worker (C2)_
    - _Requirements: 2.4_
  - [x] 8.3 Actualizar `backend/tests/test_scan_worker.py`: reemplazar las 5 ocurrencias de `from backend.workers.scan_worker import handler_scan_worker` (líneas 140, 179, 273, 302, 331) por `from backend.workers.scan_worker import handler`, y las 5 invocaciones `handler_scan_worker(...)` (líneas 160, 209, 286, 315, 343) por `handler(...)`.
    - _Requirements: 2.3.1_
  - [x] 8.4 Actualizar `backend/tests/test_scoring_worker.py`: reemplazar las ocurrencias de `from backend.workers.scoring_worker import handler_scoring_worker` (líneas 225, 263, 315, 375, 418) por `from backend.workers.scoring_worker import handler`, y las invocaciones `handler_scoring_worker(...)` (líneas 242, 292, 349, 393, 446) por `handler(...)`.
    - _Requirements: 2.4.1_
  - [x] 8.5 Ejecutar `pytest` completo y comparar el conteo de `passed` contra el baseline de la tarea 7 — debe ser idéntico (mismos passed, mismos fallos preexistentes documentados, ninguno nuevo).
    - _Verificable: 🟢 LOCAL_
    - _Requirements: 2.3.1, 2.4.1_
    - **Validates: Property 7 (preservation), Property 2 (expected behavior tras el fix)**

- [ ] 9. Fix Bloqueadores 1 y 2 — Actualizar `terraform/modules/lambda/main.tf`
  - [x] 9.1 `aws_lambda_function.api` (líneas ~46-56): reemplazar `handler = "main.handler"` por `handler = "backend.main.handler"`; eliminar el bloque de comentario `FLAGGED` (ya resuelto).
    - _Requirements: 2.1_
  - [x] 9.2 `aws_lambda_function.orquestador` (línea ~119): reemplazar `handler = "main.handler"` por `handler = "backend.main.handler"`.
    - _Requirements: 2.2_
  - [x] 9.3 `aws_lambda_function.scan_worker` (línea ~178): reemplazar `handler = "main.handler"` por `handler = "backend.workers.scan_worker.handler"`.
    - _Requirements: 2.3_
  - [x] 9.4 `aws_lambda_function.scoring_worker` (línea ~229): reemplazar `handler = "main.handler"` por `handler = "backend.workers.scoring_worker.handler"`.
    - _Requirements: 2.4_
  - [x] 9.5 Confirmar que `aws_lambda_function.notificador` no se toca (verificación de preservación 3.1).
  - [x] 9.6 Ejecutar `terraform validate` y `terraform plan` sobre el módulo `lambda` y confirmar: (a) sin errores de sintaxis, (b) el diff se limita exactamente a los 4 atributos `handler` de 9.1-9.4, sin diff en `notificador`, timeouts, memoria, env vars, concurrencia reservada ni `event_source_mapping`.
    - _Verificable: 🟢 LOCAL_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.3_
    - **Validates: Property 1, Property 2 (expected behavior), Property 7 (preservation)**

- [ ] 10. Fix Bloqueador 3 — Crear `scripts/build_lambda_packages.py`
  - [x] 10.1 Implementar el script (Decisión 3 de design.md): para cada una de las 5 Lambdas, crea un directorio de build temporal, copia `backend/` completo preservando estructura de paquete, instala dependencias de `backend/pyproject.toml` (nunca un `requirements.txt` duplicado), genera el `.zip` vía `zipfile.ZipFile`.
  - [x] 10.2 Para `api`/`orquestador`: construir el `.zip` una sola vez (mismo contenido) y subirlo a las dos rutas S3 distintas (`lambda-code/api/code.zip`, `lambda-code/orquestador/code.zip`), evitando reconstrucción duplicada.
  - [x] 10.3 Leer `lambda_code_bucket`/`lambda_code_key_prefix` de variables de entorno o argumentos CLI (`--bucket`, `--key-prefix`), nunca hardcodeados.
  - [x] 10.4 Soportar `--dry-run`: construye el `.zip` localmente, imprime/inspecciona su listado de archivos, omite la subida a S3. Sin Docker/contenedores (regla de stack cerrado).
  - [x] 10.5 Ejecutar `python scripts/build_lambda_packages.py --dry-run` para las 5 Lambdas e inspeccionar que cada `.zip` contiene `backend/__init__.py` y el módulo correspondiente (`backend/main.py` para api/orquestador, `backend/workers/scan_worker.py`/`scoring_worker.py`, estructura ya vigente para `notificador`) en las rutas esperadas.
    - _Verificable: 🟢 LOCAL (modo `--dry-run`, sin credenciales AWS)_
    - _Verificable adicional: 🔴 AWS-REAL — subida real vía `aws s3api head-object` contra el bucket real, pendiente post-implementación_
    - _Bug_Condition: isBugCondition para target == "packaging_pipeline" (C3)_
    - _Expected_Behavior: expectedBehavior de Property 3 (design.md)_
    - _Requirements: 2.5_
    - **Validates: Property 3**

- [ ] 11. Fix Bloqueador 4 — Permiso IAM de auto-invocación (`api_policy`)
  - [x] 11.1 Agregar el nuevo statement a `aws_iam_role_policy.api_policy` en `terraform/modules/iam/main.tf`:
    ```hcl
    {
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = "arn:aws:lambda:*:*:function/job-search-api"
    }
    ```
    Usar el ARN literal — NUNCA `aws_lambda_function.api.arn` (evita el ciclo `api_policy` → `aws_lambda_function.api` → `api_role` → `api_policy`).
  - [x] 11.2 Ejecutar `terraform validate`/`terraform plan` sobre el módulo `iam` y confirmar: el nuevo statement aparece con el `Resource` literal esperado, sin errores de ciclo de dependencia entre módulos `iam` y `lambda`.
    - _Verificable: 🟢 LOCAL_
    - _Verificable adicional: 🔴 AWS-REAL — confirmar que `_trigger_async_resumen_generation` deja de fallar con `AccessDeniedException` en ejecución real, pendiente post-implementación_
    - _Bug_Condition: isBugCondition para target == "api_self_invocation" (C4)_
    - _Expected_Behavior: expectedBehavior de Property 4 (design.md)_
    - _Requirements: 2.6_
    - **Validates: Property 4**

- [ ] 12. Prerequisito de la tarea 13 — Crear `terraform/modules/iam/variables.tf` y actualizar `terraform/main.tf`
  - [x] 12.1 Crear `terraform/modules/iam/variables.tf` (nuevo archivo) declarando:
    ```hcl
    variable "lambda_code_bucket" {
      description = "S3 bucket name where Lambda function .zip files are stored"
      type        = string
    }

    variable "terraform_state_bucket" {
      description = "S3 bucket name for Terraform state storage"
      type        = string
    }
    ```
  - [x] 12.2 Actualizar el bloque `module "iam"` en `terraform/main.tf` para pasar ambas variables explícitamente:
    - Leer el bloque `module "iam"` actual en `terraform/main.tf` para confirmar su contenido exacto antes de reemplazarlo (ya verificado en el diseño de esta spec como `source = "./modules/iam"` sin otros argumentos, pero se debe re-confirmar en el momento de la implementación, no asumir por una verificación anterior).
    ```hcl
    module "iam" {
      source = "./modules/iam"

      lambda_code_bucket     = var.lambda_code_bucket
      terraform_state_bucket = var.terraform_state_bucket
    }
    ```
    (ambas variables ya existen a nivel raíz en `terraform/variables.tf` — no requieren creación ahí).
  - [x] 12.3 Ejecutar `terraform validate` sobre el árbol completo y confirmar que el módulo `iam` ahora acepta ambas variables sin error.
    - _Verificable: 🟢 LOCAL_
    - _Requirements: 2.8.1 (prerequisito explícito)_
    - **Validates: Property 6.1 (prerequisito)**

- [ ] 13. Fix valor de `lambda_code_bucket` en `terraform/terraform.tfvars` (cambio local, gitignored) — **debe completarse ANTES de la tarea 14.2**
  - **IMPORTANTE**: esta tarea SHALL ejecutarse antes de la tarea 14.2 (`terraform plan` del fix de `github_actions_policy`). La tarea 14.2 verifica que el `Resource` interpolado (`${var.lambda_code_bucket}`) coincide con el bucket real; si esta tarea 13 no se ha completado, ese `terraform plan` mostraría el valor VIEJO del bucket (`"job-search-lambda-code"`) sin error de sintaxis, dando una falsa verificación positiva.
  - [x] 13.1 Corregir `lambda_code_bucket = "job-search-lambda-code"` → `lambda_code_bucket = "job-search-lambda-code-5155151158151"` en el archivo local `terraform/terraform.tfvars`.
  - [x] 13.2 Confirmar que `terraform.tfvars` sigue listado en `.gitignore` y que el cambio NO se añade a ningún commit (verificar con `git status` que el archivo no aparece como staged/tracked).
    - _Verificable: 🟢 LOCAL_
    - _Requirements: 2.8 (corrección de valor, prerequisito de que cualquier despliegue real funcione)_
    - **Validates: Property 6 (prerequisito de valor real)**

- [ ] 14. Fix statement S3 de `github_actions_policy` (depende de las tareas 12 y 13)
  - [x] 14.1 En `terraform/modules/iam/main.tf`, reemplazar el `Resource` del statement S3 de `aws_iam_role_policy.github_actions_policy` (líneas ~421-436):
    ```hcl
    # Antes
    Resource = [
      "arn:aws:s3:::*-terraform-state-bucket",
      "arn:aws:s3:::*-terraform-state-bucket/*",
      "arn:aws:s3:::*-lambda-code-bucket",
      "arn:aws:s3:::*-lambda-code-bucket/*"
    ]
    # Después
    Resource = [
      "arn:aws:s3:::${var.terraform_state_bucket}",
      "arn:aws:s3:::${var.terraform_state_bucket}/*",
      "arn:aws:s3:::${var.lambda_code_bucket}",
      "arn:aws:s3:::${var.lambda_code_bucket}/*"
    ]
    ```
    Ningún `Action` cambia (ya otorgados: `s3:PutObject`, `s3:GetObject`, `s3:ListBucket`, `lambda:UpdateFunctionCode` con `Resource = "*"` en el statement Lambda — ese statement no se toca).
  - [x] 14.2 Ejecutar `terraform plan` sobre el módulo `iam` y confirmar que el único diff es el `Resource` de ambos sub-patrones (código Lambda y Terraform state) en ese statement específico — sin cambios de `Action`, sin diff en ningún otro rol (`orquestador_role`, `scan_worker_role`, `scoring_worker_role`, `notificador_role`, `eventbridge_scheduler_role`).
    - **PRERREQUISITO**: la tarea 13 (corrección de `lambda_code_bucket` en `terraform.tfvars`) SHALL estar completa antes de ejecutar este `terraform plan` — de lo contrario el `Resource` interpolado se verificaría contra el valor viejo del bucket, no contra el valor real.
    - _Verificable: 🟢 LOCAL_
    - _Bug_Condition: isBugCondition para target == "ci_pipeline_s3_upload" (C5, C6)_
    - _Preservation: Preservation Requirements de design.md (statement Lambda de github_actions_policy sin cambios; otros roles sin cambios)_
    - _Requirements: 2.8, 2.8.1, 3.4 (excepción documentada)_
    - **Validates: Property 6, Property 6.1, Property 7 (preservation del resto del statement/roles)**

- [ ] 15. Implementar `.github/workflows/backend-deploy.yml` (depende de las tareas 3, 9, 10, 11, 12, 13, 14)
  (nota de numeración: la tarea 13 es ahora la corrección de `terraform.tfvars` y la 14 es el fix de `github_actions_policy` — ver reordenación explicada en las tareas 13-14)
  - [x] 15.1 Reemplazar el archivo vacío por un workflow con: trigger `workflow_dispatch` únicamente; job con `aws-actions/configure-aws-credentials@v4` (OIDC, `role-to-assume` apuntando a `aws_iam_role.github_actions`, sin claves de larga vida); `actions/setup-python@v5` con Python 3.12; ejecución de `python scripts/build_lambda_packages.py` (sin `--dry-run`) para las 5 Lambdas.
  - [x] 15.2 Confirmar por inspección del YAML que no se usan claves de larga vida y que el rol referenciado coincide con `aws_iam_role.github_actions` ya existente en `terraform/modules/iam/main.tf`.
    - _Verificable: 🟢 LOCAL (inspección estática del YAML)_
    - _Verificable adicional: 🔴 AWS-REAL — ejecución real de `workflow_dispatch` end-to-end (subida de los 5 `.zip`, `terraform apply`, invocación de prueba de `api`), pendiente post-implementación y explícitamente fuera de esta sesión_
    - _Bug_Condition: isBugCondition para target == "packaging_pipeline" (falta de CI funcional)_
    - _Requirements: 2.7_
    - **Validates: Property 5**
    - **Nota de dependencia real**: este workflow solo funciona en la práctica si las tareas 9, 10, 11, 12, 13 y 14 están completas — de lo contrario fallaría con `HandlerNotFound`/`AccessDeniedException` al ejecutarse.

- [x] 16. (Opcional, no bloqueante) Eliminar `lambda_handler.py`
  - Eliminar el archivo huérfano de la raíz del repo — código muerto tras la Decisión 1 (`backend.main.handler` ya es el entry point directo).
  - **Esta tarea es una recomendación de limpieza documentada en design.md, NO forma parte de los criterios de aceptación 2.1/2.2**. Puede diferirse o saltarse sin afectar el cierre de la spec.
  - _Requirements: ninguno (limpieza opcional)_

---

## Fase 4 — Verificación final

- [ ] 17. Checkpoint — Verificación final de preservación sobre el árbol completo
  - [x] 17.1 Ejecutar `terraform validate` sobre el árbol completo de `terraform/`.
  - [x] 17.2 Ejecutar `terraform plan` (contra el backend S3 real de state, sin `apply`) sobre el árbol completo y confirmar que el diff se limita EXACTAMENTE a lo descrito en "Preservation Checking" de design.md: 4 atributos `handler` en el módulo `lambda`, 2 statements + 2 variables nuevas en el módulo `iam` — ningún otro recurso, rol o statement cambia. `aws_lambda_function.notificador` no debe aparecer en el plan.
  - [x] 17.3 Ejecutar la suite `pytest` completa y comparar el conteo de `passed` contra el baseline capturado en la tarea 7 — deben coincidir (mismos passed, mismos fallos preexistentes ya documentados, ningún fallo nuevo).
    - _Verificable: 🟢 LOCAL_
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
    - **Validates: Property 7**

- [ ] 18. Checkpoint — Verificación cruzada final contra specs previas
  - [x] 18.1 Releer `.kiro/specs/backend-core/design.md`, sección "Lambda Packaging and Deployment (ZIP Format)", y confirmar que la contradicción con la Decisión 1 de esta spec (`backend.main.handler` vs. `lambda_handler.py`) sigue siendo exactamente la ya documentada y conscientemente resuelta en `design.md` de esta spec — no una contradicción nueva ni distinta.
  - [x] 18.2 Releer `.kiro/specs/backend-scan-y-scoring/design.md` (líneas ~960-961, ~1079-1080) y confirmar que el pseudocódigo `handler_scan_worker`/`handler_scoring_worker` ahí presente nunca comprometió el nombre del entry point de Lambda/Terraform como contrato — por lo tanto el renombrado a `handler` (tarea 8) no rompe ningún contrato de ese documento.
  - [x] 18.3 Confirmar que timeouts (`scan_worker: 90s`, `scoring_worker: 30s`), concurrencia reservada (`scan_worker: 5`, `scoring_worker: 3`), nombres de variables de entorno y esquemas de mensajes SQS (`ScanMessage`, `ScoringMessage`) permanecen sin cambios tras todas las tareas de esta spec (cita archivo+línea de ambos documentos de diseño reales, no resúmenes).
    - _Verificable: 🟢 LOCAL (lectura e inspección cruzada de documentos y código, sin AWS)_
    - _Requirements: 3.6_
    - **Validates: Property 8**

- [x] 19. Checkpoint final — Asegurar que todos los tests pasan
  - Confirmar que las tareas 17 y 18 están completas, que no quedan diffs de Terraform fuera del alcance documentado, y que el conteo de `pytest` coincide con el baseline.
  - Preguntar al usuario si surgen dudas sobre algún resultado antes de cerrar la spec como completa.
  - **Recordatorio explícito de items que quedan pendientes de verificación post-implementación (requieren AWS real, marcados 🔴 en tareas anteriores)**:
    - Tarea 4: `AccessDeniedException` real al invocar `_trigger_async_resumen_generation` sin el permiso (antes del fix) y ausencia del error después del fix.
    - Tarea 10: subida real de los `.zip` a S3 y verificación vía `aws s3api head-object`.
    - Tarea 11: confirmación en runtime de que el `lambda:InvokeFunction` agregado resuelve el `AccessDeniedException`.
    - Tarea 15: ejecución real de `workflow_dispatch` de `backend-deploy.yml`, incluyendo `terraform apply` real y una invocación de prueba de `api`.
    - **`terraform apply` real contra la cuenta AWS**: completar todas las tareas de esta spec (incluida la 15) NO equivale a tener el backend desplegado en AWS. El `apply` real sigue siendo una acción manual que alguien con acceso a la cuenta debe ejecutar después de que `workflow_dispatch` de `backend-deploy.yml` suba los `.zip` reales a S3. Este paso es deliberadamente posterior y fuera de alcance de esta spec (`terraform-apply.yml` permanece vacío).

---

## Task Dependency Graph

```
1 (explore C1) ─┐
2 (explore C2) ─┤
3 (explore C3) ─┼──> 7 (preservation baseline) ──┐
4 (explore C4) ─┤                                 │
5 (explore C5) ─┤                                 │
6 (explore C6) ─┘                                 │
                                                   ▼
                                          8 (rename workers + tests)
                                                   │
                                                   ▼
                                          9 (terraform lambda handlers)
                                                   │
        10 (build_lambda_packages.py) ─────────────┤
                                                   │
        11 (api_policy: lambda:InvokeFunction) ───┤
                                                   │
        12 (iam/variables.tf + main.tf module) ───┤
                                                   │
        13 (terraform.tfvars bucket value) ───────┴──> 14 (github_actions_policy S3 fix)
                                                                │
                    9, 10, 11, 12, 13, 14  ───────────────> 15 (backend-deploy.yml)
                                                                │
                    16 (opcional: borrar lambda_handler.py) ───┤ (independiente, no bloquea nada)
                                                                ▼
                                                       17 (terraform validate/plan + pytest final)
                                                                │
                                                                ▼
                                                       18 (cross-spec verification)
                                                                │
                                                                ▼
                                                       19 (checkpoint final)
```

**Dependencias críticas a respetar durante la ejecución:**
- Las tareas 1-6 (exploración) y 7 (baseline de preservación) SHALL ejecutarse ANTES de cualquier cambio de código o Terraform.
- La tarea 8 (renombrado + tests) SHALL completarse antes de la tarea 9 (Terraform apunta al nuevo `handler`), para que `terraform plan` de la tarea 9.6 sea coherente con el código real.
- La tarea 12 es prerequisito estricto de la tarea 14 (sin `variables.tf` del módulo `iam`, `${var.lambda_code_bucket}`/`${var.terraform_state_bucket}` no resuelven).
- La tarea 13 (corrección de `terraform.tfvars`) SHALL completarse ANTES de la tarea 14.2 (`terraform plan` de `github_actions_policy`), no solo antes de la 15 — de lo contrario el `Resource` interpolado se verifica contra el valor viejo del bucket, dando una falsa verificación positiva.
- La tarea 15 (workflow CI/CD) depende de que 9, 10, 11, 12, 13 y 14 estén completas para funcionar en la práctica — se puede escribir el YAML antes, pero no se puede considerar "funcionalmente completo" sin las demás.
- La tarea 16 es independiente y opcional — no bloquea ninguna otra tarea.
- Las tareas 17-19 son de verificación final y SHALL ejecutarse después de todas las tareas de implementación (8-15).
