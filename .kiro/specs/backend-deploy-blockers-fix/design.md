# Backend Deploy Blockers Fix — Bugfix Design

## Overview

Los 4 bloqueadores descritos en `bugfix.md` comparten una misma naturaleza: son desajustes entre lo que Terraform *asume* sobre cómo se empaqueta y despliega el código Python, y lo que el código real (`backend/`) efectivamente expone. Ninguno es un bug de lógica de negocio — todos son de configuración de despliegue (handler/zip/IAM/CI).

La estrategia de fix es:

1. **Handler `api`/`orquestador`** (2.1, 2.2): fijar `handler = "backend.main.handler"` en Terraform, consistente con que `backend/main.py` ya expone `handler(event, context)` a nivel de módulo (líneas 373-384) y ya enruta tanto el shape de evento de EventBridge Scheduler como el de auto-invocación async como el de API Gateway. El `.zip` debe preservar el paquete `backend/` completo.
2. **Handler `scan_worker`/`scoring_worker`** (2.3, 2.4): renombrar `handler_scan_worker`/`handler_scoring_worker` → `handler`, actualizar Terraform y los tests que importan el nombre viejo por nombre literal.
3. **Script de empaquetado** (2.5): crear `scripts/build_lambda_packages.py`, Python (consistente con `scripts/export-openapi.py` ya existente), que construye y sube los 5 `.zip` a S3 en las rutas exactas que `terraform/modules/lambda/main.tf` espera.
4. **Permiso IAM de auto-invocación** (2.6): agregar `lambda:InvokeFunction` al `api_policy`, restringido a un ARN literal (mismo patrón wildcard ya usado en `eventbridge_scheduler_policy`), sin crear un ciclo de dependencia.
5. **CI/CD** (2.7, 2.8): implementar `backend-deploy.yml` invocando el script de empaquetado vía OIDC, y corregir el patrón de `Resource` roto en el statement S3 de `github_actions_policy`.

Ningún cambio de esta spec toca lógica de negocio, `notificador`, roles IAM distintos de `api_role`/`github_actions`, ni los `event_source_mapping` ya definidos (preservación explícita, ver sección "Expected Behavior").

## Glossary

- **Bug_Condition (C)**: cualquiera de las 4 condiciones de desajuste handler/zip/IAM/CI descritas en `bugfix.md` (Bloqueadores 1-4).
- **Property (P)**: para cada bloqueador, el despliegue deja de fallar (`HandlerNotFound`/`ImportModuleError`/`AccessDeniedException`) y el recurso Terraform correspondiente queda consistente y verificable localmente.
- **Preservation**: comportamiento de `notificador`, lógica de negocio de todos los workers, `event_source_mapping` existentes, y permisos IAM de roles no tocados — deben permanecer exactamente iguales.
- **`backend.main.handler`**: función definida en `backend/main.py` líneas 373-384, que enruta `event.get("source") == "eventbridge-scheduler"` → `_handle_programmed_scan`, `event.get("mode") == "async_resumen_generation"` → `_handle_async_resumen_generation`, y cualquier otro evento → `_mangum_handler` (API Gateway/FastAPI).
- **`lambda_handler.py`**: archivo en la raíz del repo (`from backend.main import handler`) que documenta la Opción B (`handler = "lambda_handler.handler"`), nunca aplicada en Terraform — código huérfano tras la Decisión 1.
- **ARN literal**: string construido a mano (`"arn:aws:lambda:*:*:function/job-search-api"`) en vez de una referencia de Terraform (`aws_lambda_function.api.arn`), usado para romper ciclos de dependencia entre recursos.

## Bug Details

### Bug Condition

El bug se manifiesta en 4 formas independientes, todas activas simultáneamente en el estado actual del repo:

**C1 — Handler/zip inconsistente para `api`/`orquestador`:**
`terraform/modules/lambda/main.tf` (recursos `aws_lambda_function.api` línea 46-56, `aws_lambda_function.orquestador` línea 115-122) configura `handler = "main.handler"`. El código real vive en `backend/main.py`, que usa imports internos `from backend.shared...`, `from backend.api.routes...` (verificado en `backend/main.py` líneas 15-16, 300-301). Esos imports solo resuelven si el `.zip` preserva la estructura de paquete `backend/` en su raíz — lo cual es incompatible con un handler `main.handler` (que asumiría un módulo `main.py` suelto en la raíz del zip).

**C2 — Mismatch de nombre de función en `scan_worker`/`scoring_worker`:**
`terraform/modules/lambda/main.tf` (recursos `aws_lambda_function.scan_worker` línea ~178, `aws_lambda_function.scoring_worker` línea ~229) configura `handler = "main.handler"`. El código real expone `handler_scan_worker(event, context)` (`backend/workers/scan_worker.py`, última función del archivo) y `handler_scoring_worker(event, context)` (`backend/workers/scoring_worker.py`, línea 132) — ningún atributo llamado `handler` existe en ninguno de los dos módulos.

**C3 — Ausencia de script de empaquetado:**
No existe ningún script ejecutable que produzca los `.zip` esperados en `s3://{lambda_code_bucket}/{lambda_code_key_prefix}/{nombre_funcion}/code.zip`. `scripts/export-openapi.py` es el único script existente en `scripts/` y genera `frontend/openapi/openapi.json`, sin relación con empaquetado de Lambdas (verificado leyendo el archivo completo).

**C4 — Permiso IAM faltante para auto-invocación:**
`backend/api/routes/profile.py`, función `_trigger_async_resumen_generation` (líneas 128-134), ejecuta `boto3.client("lambda").invoke(FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"], InvocationType="Event", ...)`. `terraform/modules/iam/main.tf`, `aws_iam_role_policy.api_policy` (líneas 45-90), no incluye ningún statement con `lambda:InvokeFunction`.

**C5 (2.8) — Patrón de recurso S3 roto en `github_actions_policy` (bucket de código Lambda):**
`terraform/modules/iam/main.tf`, `aws_iam_role_policy.github_actions_policy`, statement S3 (líneas ~421-436), usa `Resource = ["arn:aws:s3:::*-terraform-state-bucket", ..., "arn:aws:s3:::*-lambda-code-bucket", "arn:aws:s3:::*-lambda-code-bucket/*"]`. El bucket real, `lambda_code_bucket = "job-search-lambda-code-5155151158151"` (nombre real confirmado desde la consola de AWS; el valor actual en `terraform/terraform.tfvars` línea 90, `"job-search-lambda-code"`, está desactualizado), termina en el sufijo de cuenta `-5155151158151`, no en `-lambda-code-bucket` — el patrón wildcard nunca matchea.

**C6 (2.8.1) — Patrón de recurso S3 roto en `github_actions_policy` (bucket de Terraform state):**
`terraform/modules/iam/main.tf`, `aws_iam_role_policy.github_actions_policy`, mismo statement S3 que C5, usa `Resource` incluyendo `"arn:aws:s3:::*-terraform-state-bucket"` / `"arn:aws:s3:::*-terraform-state-bucket/*"`. El bucket real, `terraform_state_bucket = "job-search-terraform-state-5543569870"` (`terraform/terraform.tfvars`, ya correcto en su valor), termina en el sufijo de cuenta `-5543569870`, no en `-terraform-state-bucket` — el patrón wildcard nunca matchea. A diferencia de C5, aquí el valor de la variable ya es correcto; solo el patrón de la policy IAM está roto.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type DeploymentAttempt
         (target IN {api, orquestador, scan_worker, scoring_worker}
          OR target == "ci_pipeline_s3_upload"
          OR target == "api_self_invocation")
  OUTPUT: boolean

  RETURN
    (input.target IN {api, orquestador}
       AND input.terraform_handler == "main.handler"
       AND input.zip_preserves_backend_package == true)
    OR
    (input.target IN {scan_worker, scoring_worker}
       AND input.terraform_handler == "main.handler"
       AND input.module_exposes_attr_named("handler") == false)
    OR
    (input.target == "packaging_pipeline"
       AND NOT exists_executable_packaging_script())
    OR
    (input.target == "api_self_invocation"
       AND input.api_role_policy_grants("lambda:InvokeFunction") == false)
    OR
    (input.target == "ci_pipeline_s3_upload"
       AND (
         NOT input.github_actions_s3_resource_pattern.matches("job-search-lambda-code-5155151158151")
         OR NOT input.github_actions_s3_resource_pattern.matches("job-search-terraform-state-5543569870")
       ))
END FUNCTION
```

### Examples

- **C1**: desplegar `api` con `handler = "main.handler"` y un `.zip` que contiene `backend/main.py` (no `main.py` en la raíz) → `Runtime.HandlerNotFound: main.handler` en la primera invocación real.
- **C2**: desplegar `scan_worker` con `handler = "main.handler"` sobre cualquier `.zip` que contenga `backend/workers/scan_worker.py` con solo `handler_scan_worker` definido → `Runtime.HandlerNotFound`, sin importar cómo se empaquete.
- **C3**: ejecutar `terraform apply` con los 5 `aws_lambda_function.*` referenciando `s3_key = "lambda-code/api/code.zip"` cuando ese objeto no existe en S3 → `apply` falla con `NoSuchKey` o similar al intentar crear la función.
- **C4**: usuario hace `PUT /me/profile`, el handler dispara `_trigger_async_resumen_generation`, el `lambda.invoke()` interno lanza `AccessDeniedException` (capturado internamente, no rompe la respuesta HTTP — pero `resumenParaMatching` nunca se genera).
- **C5 (edge case)**: incluso después de arreglar 2.5-2.7, el workflow de CI sigue fallando con `AccessDeniedException` al subir a S3, porque el patrón de recurso de `github_actions_policy` nunca matchea `job-search-lambda-code-5155151158151`.
- **C6 (edge case)**: incluso después de arreglar 2.8, cualquier operación de Terraform (vía `terraform-apply.yml` o el propio `backend-deploy.yml`) que necesite leer/escribir el state en S3 sigue fallando con `AccessDeniedException`, porque el mismo statement nunca matchea `job-search-terraform-state-5543569870`.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `notificador` sigue usando `handler = "backend.workers.notificador.handler.handler"` exactamente como está hoy (`terraform/modules/lambda/main.tf`, resource `aws_lambda_function.notificador`) — no se toca.
- Toda la lógica de negocio de los workers (cascada de descubrimiento, missCount, prefiltro de cargos, prompt de scoring, generación de `resumenParaMatching`) permanece byte-a-byte igual — solo se renombra la función de entry point, nunca su cuerpo.
- Los `aws_lambda_event_source_mapping` de SQS (`scan_worker_sqs`, `scoring_worker_sqs`) y de DynamoDB Streams (`notificador_dynamodb_stream`) permanecen sin modificar.
- Los roles IAM `orquestador_role`, `scan_worker_role`, `scoring_worker_role`, `notificador_role`, `eventbridge_scheduler_role` no reciben ningún grant nuevo ni pierden ninguno.
- En `github_actions_policy`, solo cambia el `Resource` del statement S3, en ambos sub-patrones (criterios 2.8 y 2.8.1) — ningún `Action` se agrega, quita, ni se modifica el statement Lambda (que ya otorga `lambda:UpdateFunctionCode` con `Resource = "*"`, verificado en `terraform/modules/iam/main.tf`).
- `frontend-deploy.yml` y `terraform-apply.yml` permanecen vacíos, sin modificar.
- La suite completa de `pytest` mantiene el mismo conteo de `passed` antes y después del renombrado de `handler_scan_worker`/`handler_scoring_worker`, una vez actualizados los imports/invocaciones en los tests correspondientes.

**Scope:**
Todo input que NO involucre los 5 puntos de bug (handler `api`/`orquestador`, handler `scan_worker`/`scoring_worker`, ausencia de script, permiso IAM de auto-invocación, patrón S3 roto) queda completamente inafectado por este fix. Esto incluye: comportamiento de `notificador`, cualquier endpoint de `backend/api/routes/*` que no sea el mecanismo de enrutamiento del handler Lambda, y cualquier statement IAM de un rol distinto de `api_role`/`github_actions`.

## Hypothesized Root Cause

1. **Configuración de Terraform escrita antes de que el código convergiera**: el propio comentario `FLAGGED` en `terraform/modules/lambda/main.tf` (líneas 48-53) documenta que quien escribió el módulo Terraform sabía que había ambigüedad sin resolverla — sugiere que el módulo Lambda se escribió en paralelo/antes de que `backend/main.py` terminara de definir su propio `handler()` a nivel de módulo.

2. **Documento de diseño desactualizado** (`backend-core/design.md`, sección "Lambda Packaging and Deployment (ZIP Format)"): especifica `lambda_handler.py` como entry point y `handler = "lambda_handler.handler"` (implícito), pero el código evolucionó a exponer `backend.main.handler` directamente. Nadie actualizó el diseño ni Terraform tras ese cambio de implementación.

3. **Copy-paste del handler placeholder** (`"main.handler"`) al definir los 4 `aws_lambda_function.*` restantes sin adaptar cada uno a su módulo real — explica por qué `scan_worker`/`scoring_worker` heredan el mismo string genérico pese a exponer funciones con nombres distintos (`handler_scan_worker`, `handler_scoring_worker`).

4. **Ausencia de pipeline de CI/CD funcional desde el inicio del proyecto**: los 3 workflows nacieron vacíos (0 líneas) — nunca hubo necesidad de resolver el empaquetado real hasta este punto, por lo que el gap simplemente no se cerró.

5. **Statement IAM copiado de una plantilla genérica con convención de nombre de bucket distinta** (`*-lambda-code-bucket` / `*-terraform-state-bucket`) sin adaptarlo a los nombres reales confirmados en la consola de AWS (`job-search-lambda-code-5155151158151`, `job-search-terraform-state-5543569870`), que siguen la convención `{project}-{tipo}-{sufijo de cuenta}` en vez de terminar literalmente en `-bucket`.

6. **Módulo `iam` sin variables de entrada, por lo que nunca pudo referenciar las variables reales**: `terraform/main.tf`, bloque `module "iam"`, se invoca hoy sin ningún input variable ("No input variables - IAM module creates all roles with hardcoded names", verificado), y `terraform/modules/iam/` no tiene ningún `variables.tf` (solo `main.tf` y `outputs.tf`, verificado con listado de directorio) — esto explica por qué el patrón roto nunca pudo referenciar `var.lambda_code_bucket`/`var.terraform_state_bucket`: esas variables, aunque ya existen a nivel raíz (`terraform/variables.tf`), simplemente no eran accesibles dentro del módulo `iam` hasta ahora.

## Correctness Properties

Property 1: Bug Condition — Handler/Zip Consistency for `api` and `orquestador`

_For any_ deployment attempt where the bug condition holds for `target IN {api, orquestador}` (Terraform `handler` and `.zip` package structure are mutually inconsistent with `backend/main.py`'s actual location and imports), the fixed configuration SHALL set `handler = "backend.main.handler"` in Terraform and produce a `.zip` that preserves the `backend/` package structure at its root, such that `python -c "from backend.main import handler"` succeeds when run from a directory replicating the `.zip` layout, and `terraform validate`/`terraform plan` show no errors on the `handler` attribute.

**Validates: Requirements 2.1, 2.2**

Property 2: Bug Condition — Handler Name Match for `scan_worker` and `scoring_worker`

_For any_ deployment attempt where the bug condition holds for `target IN {scan_worker, scoring_worker}` (the module does not expose an attribute literally named `handler`), the fixed code SHALL expose `handler(event, context)` (renamed from `handler_scan_worker`/`handler_scoring_worker`) in the respective module, and Terraform SHALL configure `handler = "backend.workers.scan_worker.handler"` / `handler = "backend.workers.scoring_worker.handler"`, such that `python -c "from backend.workers.<module> import handler"` succeeds, and the full pytest suite (with test imports/invocations updated to the new name) SHALL pass with the same count of `passed` as before the rename.

**Validates: Requirements 2.3, 2.3.1, 2.4, 2.4.1**

Property 3: Bug Condition — Packaging Script Produces and Uploads Correct Artifacts

_For any_ of the 5 Lambdas (`api`, `orquestador`, `scan_worker`, `scoring_worker`, `notificador`), running `scripts/build_lambda_packages.py` SHALL produce a `.zip` containing the package structure required by that function's fixed handler (per Properties 1 and 2, or the untouched `notificador` structure), install the dependencies declared in `backend/pyproject.toml`, and upload the result to exactly `s3://{lambda_code_bucket}/{lambda_code_key_prefix}/{nombre_funcion}/code.zip` as read by `terraform/modules/lambda/main.tf`'s `s3_bucket`/`s3_key` attributes — verifiable by running the script in `--dry-run` mode and inspecting the local `.zip` contents, or by a real run followed by `aws s3api head-object` against the computed key.

**Validates: Requirements 2.5**

Property 4: Bug Condition — IAM Self-Invocation Permission Without Cycle

_For any_ invocation of `_trigger_async_resumen_generation` by the `api` Lambda, the fixed `aws_iam_role_policy.api_policy` SHALL grant `lambda:InvokeFunction` scoped to a literal ARN string (`"arn:aws:lambda:*:*:function/job-search-api"`, never `aws_lambda_function.api.arn` and never `"*"`), such that `terraform plan`/`terraform validate` show the new statement without introducing a dependency cycle between the `iam` and `lambda` Terraform modules.

**Validates: Requirements 2.6**

Property 5: Bug Condition — CI/CD Workflow Invokes Packaging Script via OIDC

_For any_ trigger of `.github/workflows/backend-deploy.yml` (manual `workflow_dispatch`), the fixed workflow SHALL authenticate via OIDC against `aws_iam_role.github_actions` (no long-lived credentials), install Python 3.12, and invoke `scripts/build_lambda_packages.py` for the 5 Lambdas — verifiable by inspecting the resulting YAML against the cited OIDC role and, where possible, via a manual `workflow_dispatch` run.

**Validates: Requirements 2.7**

Property 6: Bug Condition — S3 Resource Pattern Matches Real Bucket Name (Lambda Code)

_For any_ evaluation of the S3 statement in `aws_iam_role_policy.github_actions_policy`, the fixed `Resource` SHALL include `["arn:aws:s3:::${var.lambda_code_bucket}", "arn:aws:s3:::${var.lambda_code_bucket}/*"]` (referencing the existing `lambda_code_bucket` variable, never a hardcoded string or the broken `*-lambda-code-bucket` pattern), such that it matches the real bucket name `job-search-lambda-code-5155151158151` — verifiable via `terraform plan` showing only the `Resource` change on that statement, with no `Action` changes.

**Validates: Requirements 2.8**

Property 6.1: Bug Condition — S3 Resource Pattern Matches Real Bucket Name (Terraform State)

_For any_ evaluation of the same S3 statement in `aws_iam_role_policy.github_actions_policy`, the fixed `Resource` SHALL also include `["arn:aws:s3:::${var.terraform_state_bucket}", "arn:aws:s3:::${var.terraform_state_bucket}/*"]` (referencing the already-existing root-level variable `terraform_state_bucket` from `terraform/variables.tf`, never a hardcoded string or the broken `*-terraform-state-bucket` pattern), such that it matches the real bucket name `job-search-terraform-state-5543569870`. This requires the `iam` module to expose `lambda_code_bucket` and `terraform_state_bucket` as new input variables — verifiable via `terraform plan` showing only the `Resource` change on that statement (both sub-patterns) plus the new module input variables, with no `Action` changes.

**Validates: Requirements 2.8.1**

Property 7: Preservation — Untouched Resources and Business Logic Remain Identical

_For any_ evaluation of `notificador`'s handler configuration, worker business logic (cascada de descubrimiento, missCount, prefiltro de cargos, scoring prompt/validation, generación de resumenParaMatching), the SQS/DynamoDB-Streams `event_source_mapping` resources, and the IAM policies of roles other than `api_role`/`github_actions`, the fixed configuration SHALL produce exactly the same result as the original configuration — including the `pytest` suite's total `passed` count before and after the `scan_worker`/`scoring_worker` handler rename (once test imports/invocations are updated to match).

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Property 8: Preservation — Cross-Spec Contract Consistency

_For any_ contract already established in `backend-core/design.md` or `backend-scan-y-scoring/design.md` (Lambda timeouts, reserved concurrency, environment variable names, SQS message schemas), the packaging changes made in this spec SHALL continue to satisfy them without breaking them, except for the explicitly documented and superseded handler/packaging convention in `backend-core/design.md`'s "Lambda Packaging and Deployment (ZIP Format)" section (see "Cross-Spec Verification" below).

**Validates: Requirements 3.6**

## Fix Implementation

### Changes Required

**File**: `terraform/modules/lambda/main.tf`

**Specific Changes**:
1. **`aws_lambda_function.api`** (líneas ~46-56): reemplazar `handler = "main.handler"` (y eliminar el bloque de comentario `FLAGGED`, ya resuelto) por `handler = "backend.main.handler"`.
2. **`aws_lambda_function.orquestador`** (línea ~119): reemplazar `handler = "main.handler"` por `handler = "backend.main.handler"`.
3. **`aws_lambda_function.scan_worker`** (línea ~178): reemplazar `handler = "main.handler"` por `handler = "backend.workers.scan_worker.handler"`.
4. **`aws_lambda_function.scoring_worker`** (línea ~229): reemplazar `handler = "main.handler"` por `handler = "backend.workers.scoring_worker.handler"`.
5. `aws_lambda_function.notificador` no cambia.

**File**: `backend/workers/scan_worker.py`

**Specific Changes**:
6. Renombrar `def handler_scan_worker(event, context)` → `def handler(event, context)` (última función del archivo, sección "LAMBDA HANDLER"). Cuerpo de la función sin cambios.

**File**: `backend/workers/scoring_worker.py`

**Specific Changes**:
7. Renombrar `def handler_scoring_worker(event, context)` → `def handler(event, context)` (línea 132, sección "MAIN HANDLER"). Cuerpo sin cambios.

**File**: `backend/tests/test_scan_worker.py`

**Specific Changes**:
8. Reemplazar las 5 ocurrencias de `from backend.workers.scan_worker import handler_scan_worker` (líneas 140, 179, 273, 302, 331) por `from backend.workers.scan_worker import handler`, y las 5 invocaciones correspondientes (líneas 160, 209, 286, 315, 343) de `handler_scan_worker(...)` por `handler(...)`.

**File**: `backend/tests/test_scoring_worker.py`

**Specific Changes**:
9. Reemplazar las ocurrencias de `from backend.workers.scoring_worker import handler_scoring_worker` (líneas 225, 263, 315, y las restantes citadas en `bugfix.md`: 375, 418) por `from backend.workers.scoring_worker import handler`, y las invocaciones `handler_scoring_worker(...)` (líneas 242, 292, y las restantes: 349, 393, 446) por `handler(...)`.

**File**: `scripts/build_lambda_packages.py` (nuevo)

**Specific Changes**:
10. Script Python (usa `zipfile`, `subprocess`/`pip`, `boto3`, `argparse`) que:
    - Para cada una de las 5 Lambdas, crea un directorio de build temporal (`tempfile.TemporaryDirectory`).
    - Copia `backend/` completo preservando la estructura de paquete.
    - Instala las dependencias de `backend/pyproject.toml` en ese directorio vía `pip install . -t <build_dir>` (o `pip install -e . --target`, a confirmar en implementación) apuntando al propio `pyproject.toml` como fuente de dependencias — nunca un `requirements.txt` duplicado.
    - Para `api`/`orquestador`: construye el `.zip` una sola vez (mismo contenido) y lo sube a las dos rutas S3 distintas (`lambda-code/api/code.zip`, `lambda-code/orquestador/code.zip`), evitando reconstrucción duplicada.
    - Genera el `.zip` con `zipfile.ZipFile`.
    - Sube a `s3://{lambda_code_bucket}/{lambda_code_key_prefix}/{nombre_funcion}/code.zip` vía `boto3.client("s3").upload_file(...)`.
    - Lee `lambda_code_bucket`/`lambda_code_key_prefix` de variables de entorno o argumentos CLI (`--bucket`, `--key-prefix`), nunca hardcodeados.
    - Soporta `--dry-run`: construye el `.zip` localmente, imprime/inspecciona su listado de archivos, y omite la subida a S3.
    - No usa Docker/contenedores (regla de stack cerrado).

**File**: `terraform/modules/iam/main.tf`

**Specific Changes**:
11. **`aws_iam_role_policy.api_policy`** (statement list, tras el statement de `execute-api:Invoke`): agregar un nuevo statement:
    ```hcl
    {
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = "arn:aws:lambda:*:*:function/job-search-api"
    }
    ```
12.a **`terraform/modules/iam/variables.tf`** (nuevo archivo) — prerequisito de 12, dado que hoy el módulo `iam` no recibe ninguna variable de entrada (`terraform/main.tf`, bloque `module "iam"`, dice explícitamente "No input variables..."; `terraform/modules/iam/` solo tiene `main.tf` y `outputs.tf`, sin `variables.tf`):
    - Crear el archivo con:
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
    - Actualizar el bloque `module "iam"` en `terraform/main.tf` (que hoy no pasa ninguna variable) para agregar:
      ```hcl
      module "iam" {
        source = "./modules/iam"

        lambda_code_bucket     = var.lambda_code_bucket
        terraform_state_bucket = var.terraform_state_bucket
      }
      ```
      (ambas variables ya existen a nivel raíz en `terraform/variables.tf` — no requieren creación ahí).

12. **`aws_iam_role_policy.github_actions_policy`**, statement S3 (líneas ~421-436): reemplazar
    ```hcl
    Resource = [
      "arn:aws:s3:::*-terraform-state-bucket",
      "arn:aws:s3:::*-terraform-state-bucket/*",
      "arn:aws:s3:::*-lambda-code-bucket",
      "arn:aws:s3:::*-lambda-code-bucket/*"
    ]
    ```
    por
    ```hcl
    Resource = [
      "arn:aws:s3:::${var.terraform_state_bucket}",
      "arn:aws:s3:::${var.terraform_state_bucket}/*",
      "arn:aws:s3:::${var.lambda_code_bucket}",
      "arn:aws:s3:::${var.lambda_code_bucket}/*"
    ]
    ```
    (depende de 12.a — ambos sub-patrones, código Lambda y Terraform state, se corrigen en el mismo statement).

**File**: `terraform/terraform.tfvars` (gitignored — no se versiona en el repo)

**Specific Changes**:
12.b Corregir `lambda_code_bucket = "job-search-lambda-code"` → `lambda_code_bucket = "job-search-lambda-code-5155151158151"` (nombre real confirmado desde la consola de AWS). **Nota importante**: este archivo está gitignored porque contiene valores sensibles reales del entorno de despliegue — el cambio se aplica directamente sobre el archivo local del entorno de desarrollo/CI, nunca se commitea ni se versiona en el repo. Quien ejecute las tareas de implementación de este fix SHALL aplicar este cambio localmente y NO debe intentar añadir `terraform.tfvars` a un commit.

**File**: `.github/workflows/backend-deploy.yml`

**Specific Changes**:
13. Reemplazar el archivo vacío por un workflow con:
    - Trigger: `workflow_dispatch` únicamente (decisión explícita — ver justificación abajo).
    - Job que hace `aws-actions/configure-aws-credentials@v4` con `role-to-assume: arn:aws:iam::<account>:role/job-search-github-actions-role` (o referenciado vía secret/variable de repo, a definir en implementación) y `aws-region`.
    - Setup Python 3.12 (`actions/setup-python@v5`).
    - Ejecuta `python scripts/build_lambda_packages.py` (sin `--dry-run`) para las 5 Lambdas.

**File**: `lambda_handler.py` (recomendación de limpieza, NO obligatoria para los criterios de aceptación)

**Specific Changes**:
14. Eliminar el archivo. Queda como código muerto tras la Decisión 1 (`backend.main.handler` ya es el entry point directo). Esto es una recomendación de limpieza documentada aquí; no forma parte de los criterios 2.1/2.2, que solo exigen consistencia handler/zip — se puede diferir a una tarea separada y opcional.

### Riesgo de tamaño de paquete (documentado, no bloqueante)

`backend/pyproject.toml` declara un único conjunto de dependencias: `fastapi==0.104.1`, `mangum==0.26.0`, `pydantic==2.5.0`, `boto3==1.34.0`, `python-json-logger==2.0.7`, `beautifulsoup4==4.12.2`, `python-multipart==0.0.6`, `python-ulid==2.7.0`, `requests==2.31.0`. Si las 5 Lambdas empaquetan este mismo set completo, `scan_worker`/`scoring_worker` (que nunca usan `fastapi`/`mangum`/`python-multipart`) cargan dependencias que nunca ejecutan, inflando el `.zip` innecesariamente y acercándose a los límites de Lambda (50MB comprimido, 250MB descomprimido). Adicionalmente, `boto3` ya viene preinstalado en el runtime administrado `python3.12`, por lo que incluirlo en el `.zip` es redundante en tamaño (aunque es práctica común para pinnear versión).

**Decisión de diseño para esta spec** (alcance limitado, no se reestructura `pyproject.toml`): instalar el mismo set completo de dependencias para las 5 Lambdas por simplicidad, consistente con el patrón ya usado en `backend-core/design.md` (sección "Build Script"), aceptando el tamaño de paquete resultante como conocido y no bloqueante para el volumen actual del proyecto (hackathon/MVP, sin locks de tamaño).

**Mejora futura fuera de alcance**: separar `requirements-api.txt`/`requirements-worker.txt`, o usar Lambda Layers (como ya contempla `backend-core/design.md` en su sección "Layer vs. Bundled") para reducir el tamaño de los workers.

### Cross-Spec Verification (Requirement 3.6)

**Contradicción detectada y resuelta conscientemente con `backend-core/design.md`:**

`backend-core/design.md`, sección "## Lambda Packaging and Deployment (ZIP Format)", especifica una estructura de zip con `lambda_handler.py` como entry point (`from backend.main import handler`) y, de forma implícita, `handler = "lambda_handler.handler"`. Esto es una contradicción directa con la Decisión 1 de esta spec, que fija `handler = "backend.main.handler"` (sin pasar por `lambda_handler.py`).

**Resolución**: `backend/main.py` (líneas 373-384, función `handler()` a nivel de módulo) evolucionó más allá de lo que `backend-core/design.md` documentó originalmente — el código ya expone `handler()` directamente, haciendo innecesaria la capa de indirección de `lambda_handler.py`. Esta spec formaliza el estado real del código como fuente de verdad operativa para el despliegue. `backend-core/design.md` NO se modifica en esta spec (fuera de alcance) — la discrepancia queda documentada aquí como decisión consciente, no como omisión.

**Verificación — sin contradicción real con `backend-scan-y-scoring/design.md`:**

`backend-scan-y-scoring/design.md`, líneas ~960-961 y ~1079-1080, muestra `def handler_scan_worker(event, context):` y (para scoring) el inicio de la sección "Pseudocódigo: Scoring_Worker Lambda" con `def handler_scoring_worker(event, context):` como pseudocódigo de implementación de la lógica de negocio del worker — no como especificación del nombre exacto del entry point de Lambda/Terraform. Ese documento nunca fija un `handler = "..."` de Terraform ni discute el atributo de configuración de AWS Lambda. Por lo tanto, el renombrado a `handler` (Decisión 2 de esta spec, criterios 2.3/2.4) no contradice ningún contrato de diseño ya establecido en `backend-scan-y-scoring/design.md` — solo corrige un nombre de función interno que ese documento nunca comprometió como parte de la interfaz pública.

**Otros contratos verificados sin romper** (Requirement 3.6): timeouts de Lambda (`scan_worker: 90s`, `scoring_worker: 30s` — `terraform/modules/lambda/main.tf` `timeout = 90`/`timeout = 30`, sin cambios en esta spec), concurrencia reservada (`scan_worker: 5`, `scoring_worker: 3` — sin cambios), nombres de variables de entorno (sin cambios, esta spec solo toca `handler`/empaquetado/IAM/CI), y esquemas de mensajes SQS (`ScanMessage`, `ScoringMessage` en `backend/workers/scan_worker.py` — sin cambios, el body de las funciones no se toca).

## Testing Strategy

### Validation Approach

La estrategia sigue el enfoque de dos fases: primero, surfacear contraejemplos que demuestren cada bloqueador sobre el código/config sin arreglar; luego, verificar que el fix resuelve cada bloqueador y preserva todo lo demás.

### Exploratory Bug Condition Checking

**Goal**: confirmar o refutar la causa raíz hipotetizada para cada uno de los 5 sub-bugs, antes de tocar código/Terraform.

**Test Plan**: para cada bloqueador, ejecutar un chequeo local que reproduzca el fallo sin necesidad de AWS real (salvo donde se indique explícitamente lo contrario).

**Test Cases**:
1. **Handler `api` roto** (C1): replicar localmente la estructura de zip esperada (`backend/` en la raíz de un directorio temporal) y ejecutar `python -c "import main"` desde ese directorio → falla con `ModuleNotFoundError: No module named 'main'`, confirmando que `"main.handler"` nunca resuelve contra esa estructura. Luego `python -c "from backend.main import handler"` desde el directorio padre → SÍ resuelve, confirmando la causa raíz y la solución (`backend.main.handler`).
2. **Handler `scan_worker` roto** (C2): `python -c "from backend.workers.scan_worker import handler"` sobre el código actual (sin renombrar) → falla con `ImportError: cannot import name 'handler'`, confirmando C2. Tras renombrar, se repite y debe resolver.
3. **Ausencia de script** (C3): `ls scripts/` / `Get-ChildItem scripts/` muestra solo `export-openapi.py` — confirmado ya en esta sesión.
4. **Permiso IAM faltante** (C4): inspección estática de `terraform/modules/iam/main.tf`, sección `aws_iam_role_policy.api_policy` → ningún statement contiene `lambda:InvokeFunction` (confirmado ya en esta sesión, ver evidencia arriba). La confirmación en runtime (`AccessDeniedException` real) queda pendiente de verificación post-implementación, marcada explícitamente como tal.
5. **Patrón S3 roto — bucket de código Lambda** (C5/2.8): evaluar el patrón `arn:aws:s3:::*-lambda-code-bucket` contra el nombre real `job-search-lambda-code-5155151158151` → no matchea (el string no termina en `-lambda-code-bucket`), confirmado por inspección literal de ambos strings.
6. **Patrón S3 roto — bucket de Terraform state** (C6/2.8.1): evaluar el patrón `arn:aws:s3:::*-terraform-state-bucket` contra el nombre real `job-search-terraform-state-5543569870` → no matchea (el string no termina en `-terraform-state-bucket`), confirmado por inspección literal de ambos strings.

**Expected Counterexamples**:
- C1/C2: `ImportError`/`ModuleNotFoundError` al intentar resolver el handler configurado hoy en Terraform contra la ubicación real del código.
- C4: ausencia del statement de permiso, confirmable estáticamente; el `AccessDeniedException` en ejecución real queda como pendiente post-implementación.
- C5/C6: falta de coincidencia de patrón de string para ambos buckets (código Lambda y Terraform state), confirmable sin AWS.

### Fix Checking

**Goal**: verificar que, para cada bloqueador, el fix produce el comportamiento esperado.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := applyFix(input)
  ASSERT expectedBehavior(result)
END FOR
```

Aplicado concretamente:
- C1/C2: `python -c "from <módulo_resuelto> import handler"` ejecuta sin error, replicando la estructura de zip real generada por `scripts/build_lambda_packages.py`.
- C3: `python scripts/build_lambda_packages.py --dry-run` produce 5 `.zip` (o 1 compartido + 4, dado que `api`/`orquestador` comparten contenido) con la estructura de paquete correcta, sin subir nada a S3.
- C4: `terraform validate` y `terraform plan` sobre el módulo `iam` muestran el nuevo statement de `api_policy` sin errores de sintaxis ni de ciclo de dependencia entre módulos.
- C5/C6/2.7/2.8/2.8.1: `terraform plan` sobre el módulo `iam` muestra el cambio de `Resource` en ambos sub-patrones (código Lambda y Terraform state) del statement S3 de `github_actions_policy`, más los nuevos input variables del módulo `iam`; inspección del YAML de `backend-deploy.yml` contra el rol OIDC citado.

### Preservation Checking

**Goal**: verificar que, para todo lo que NO es parte de los 5 bloqueadores, el comportamiento no cambia.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing Approach**: dado que los cambios de esta spec son principalmente de configuración (Terraform, nombres de entry point) y no de lógica de negocio, la preservación se verifica mayormente mediante:
- Ejecución de la suite `pytest` completa antes y después del renombrado (`handler_scan_worker`→`handler`, `handler_scoring_worker`→`handler`), comparando el conteo total de `passed`/`failed`. Cualquier fallo preexistente no relacionado con este fix (por ejemplo en `backend/tests/test_logging_config.py` u otro módulo, si existiera) SHALL documentarse explícitamente antes de excluirlo de la comparación — no se asume su existencia sin verificarlo primero.
- `terraform plan` sobre el módulo `iam` completo, confirmando que el único diff son los dos statements descritos (nuevo `lambda:InvokeFunction` en `api_policy`, `Resource` corregido en `github_actions_policy`) — ningún otro rol/statement cambia.
- `terraform plan` sobre el módulo `lambda` completo, confirmando que el único diff son los 4 atributos `handler` (api, orquestador, scan_worker, scoring_worker) — `notificador`, timeouts, memoria, concurrencia reservada, variables de entorno y `event_source_mapping` permanecen idénticos.

**Test Plan**: capturar el resultado de `pytest` y `terraform plan` ANTES de aplicar cualquier cambio de código, luego repetir después, y diff-ear ambos resultados.

**Test Cases**:
1. **Suite pytest preservation**: correr `pytest` completo antes del renombrado, guardar el conteo; correr después, comparar.
2. **Terraform plan — módulo lambda**: confirmar que solo los 4 `handler` cambian, nada más (timeouts, memoria, env vars, `reserved_concurrent_executions`, `event_source_mapping` sin diff).
3. **Terraform plan — módulo iam**: confirmar que solo los 2 statements descritos cambian (api_policy nuevo statement, github_actions_policy Resource corregido en ambos sub-patrones — código Lambda y Terraform state). Además del `Resource` corregido, el plan mostrará la adición de las dos nuevas variables de entrada del módulo `iam` (`lambda_code_bucket`, `terraform_state_bucket`) — esto no constituye un cambio de comportamiento para ningún rol existente, son solo inputs nuevos; ningún otro rol (`orquestador_role`, `scan_worker_role`, `scoring_worker_role`, `notificador_role`, `eventbridge_scheduler_role`) ni statement no relacionado con el bucket S3 muestra diff.
4. **notificador sin diff**: confirmar explícitamente que `aws_lambda_function.notificador` no aparece en el plan de Terraform.

### Unit Tests

- Test que `python -c "from backend.main import handler"` resuelve sin error desde una réplica de la estructura de zip.
- Test que `python -c "from backend.workers.scan_worker import handler"` y `from backend.workers.scoring_worker import handler` resuelven tras el renombrado.
- Test de `backend/tests/test_scan_worker.py` y `test_scoring_worker.py` actualizados, pasando con el mismo conteo que antes.
- Test unitario de `scripts/build_lambda_packages.py --dry-run` verificando que el `.zip` generado contiene `backend/__init__.py`, `backend/main.py` (o el módulo worker correspondiente) en las rutas esperadas dentro del archivo.

### Property-Based Tests

- Generar variaciones de estructura de directorio de build (con/sin `backend/__init__.py` en algún subpaquete) y verificar que el script de empaquetado falla de forma explícita y detectable si falta algún `__init__.py` requerido, en vez de producir un `.zip` silenciosamente incompleto.
- Generar combinaciones de `lambda_code_bucket`/`lambda_code_key_prefix` (vía variables de entorno/CLI) y verificar que la clave S3 calculada por el script siempre coincide con el patrón `{prefix}/{nombre_funcion}/code.zip` esperado por `terraform/modules/lambda/main.tf`, para las 5 combinaciones de nombre de función.

### Integration Tests

- Ejecutar `terraform validate` sobre el árbol completo de `terraform/` tras aplicar todos los cambios de esta spec.
- Ejecutar `terraform plan` (contra el backend S3 real de state, sin `apply`) y confirmar que el diff se limita exactamente a lo descrito en "Preservation Checking".
- (Pendiente de verificación post-implementación, requiere AWS real) `workflow_dispatch` manual de `backend-deploy.yml` end-to-end: subida real de los 5 `.zip` a S3, seguida de un `terraform apply` manual y una invocación de prueba de `api` para confirmar ausencia de `HandlerNotFound`/`AccessDeniedException`.
