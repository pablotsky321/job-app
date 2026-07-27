# Design Document: Backend Vacantes y Notificaciones

## Overview

Este design especifica la arquitectura para la API síncrona de gestión de vacantes (listado, detalle, registro manual, aplicación, CV-ATS, banco de preguntas) y el ciclo de notificación asíncrona tras escaneo programado.

La solución integra dos canales de activación:
- **Síncrono**: Endpoints REST en Lambda API (FastAPI + Mangum) para consultas y operaciones del usuario.
- **Asíncrono**: Notificador Lambda disparado por cierre de ScanJob programado (desacoplado del scan-worker).

Todos los componentes aplican validación Pydantic con reintento, logging estructurado JSON, e identidad extraída del JWT del authorizer de Cognito.

**NOTA**: Esta spec cubre únicamente la lógica de negocio y comportamiento de la API y Notificador. La infraestructura base (EventBridge Scheduler, DynamoDB Streams, roles IAM, nuevas tablas) está a cargo de la spec de Terraform. Fuera de alcance: frontend, generación `.docx`, vista agregada de preguntas.

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API Gateway + Cognito Authorizer             │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                        event.requestContext.authorizer.claims.sub
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│              Lambda API (FastAPI + Mangum) — Síncrona                │
│  GET  /me/vacancies                                                  │
│  GET  /me/vacancies/{companyId}/{vacancyId}                         │
│  POST /me/vacancies/manual                                           │
│  POST /me/vacancies/{companyId}/{vacancyId}/apply                   │
│  POST /me/vacancies/{companyId}/{vacancyId}/cv                      │
│  GET  /me/vacancies/{companyId}/{vacancyId}/entries                 │
│  POST /me/vacancies/{companyId}/{vacancyId}/entries                 │
│  POST /me/vacancies/{companyId}/{vacancyId}/entries/{id}/answer     │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                 Bedrock (us-east-1)│    DynamoDB     SQS (scoring)
                                    │
┌──────────────────────────────────────────────────────────────────────┐
│         DynamoDB Streams (ScanJobs tabla)                            │
│         - Detecta transiciones: status ∉ terminal → status ∈ terminal│
│         - Lambda trigger → Notificador_Lambda                        │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│          Notificador_Lambda (backend-vacantes-y-notificaciones)      │
│  - Identifica ScanJobs programados terminados (userId nulo)          │
│  - Localiza vacantes nuevas calificadas por usuario y empresa        │
│  - Construye correo con CV-ATS, empresa, score                       │
│  - Envía mediante SES                                                │
│  - Logging JSON estructurado                                         │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│        EventBridge Scheduler (Infraestructura — Terraform)           │
│              Invoca Orquestador_Lambda según horario fijo             │
└──────────────────────────────────────────────────────────────────────┘
```

### Data Model References (esquema REAL del contexto maestro)

Todos los modelos Pydantic residen en `backend/shared/models.py`. **Claves DynamoDB exactas** según contexto-tecnico-infra.md:

- **Empresas**: PK `companyId` (S), sin SK, sin GSI.
  - Campos: `nombre`, `plataforma`, `careersUrl`, `lastScannedAt`, `lastScanStatus`, `lastVacancyCount`, `consecutiveFailures`.

- **Vacantes**: PK `companyId` (S), SK `vacancyId` (S), sin GSI.
  - Campos: `titulo`, `descripcion`, `modalidad`, `ubicacion`, `url`, `origen` (manual/automated), `estado` (abierta/cerrada), `firstSeenAt`, `lastSeenAt`.

- **UsuarioVacante**: PK `userId` (S), SK `sk` (formato `{companyId}#{vacancyId}`), sin GSI (deliberado).
  - Campos: `estado` (nueva/vista/aplicada/filtered_out), `score`, `scoreProfileVersion`, `cvAtsTexto`, `cvGeneratedAt`, `appliedAt`, `createdAt`.

- **Entradas**: PK `pk` (formato `{userId}#{companyId}#{vacancyId}`), SK `entryId` (S, ULID), sin GSI.
  - Campos: `tipo` (preguntas/nota_entrevista), `contenido`, `createdAt`.

- **Perfiles**: PK `userId` (S), sin SK, sin GSI.
  - Campos: `perfilEstructurado` (JSON), `resumenParaMatching` (texto), `profileVersion`, `cargosActivos`.

- **Suscripciones**: PK `userId` (S), SK `companyId` (S), GSI `porEmpresa` (PK=`companyId`, SK=`userId`).
  - Campos: `activa` (boolean).

- **ScanJobs**: PK `jobId` (S), sin SK, sin GSI, TTL en `ttl`.
  - Campos: `userId` (nulo para programado), `status` (RUNNING/DONE/PARCIAL/FAILED), `empresasCompletadas` (StringSet), `startedAt`.



## Section 1: Vacancy_Listing_API

### Endpoint: `GET /me/vacancies`

**Query Parameters**:
- `estado` (optional, default=`activas`): String exacto, case-sensitive. Valores válidos: `activas` (nueva | vista), `aplicadas` (aplicada).

**Security**: userId extraído de `event.requestContext.authorizer.claims.sub`.

### Processing Logic

1. **Extrae userId** del JWT. Si ausente → HTTP 401.
2. **Valida parámetro `estado`**:
   - Si presente y no es `activas` ni `aplicadas` (case-sensitive) → HTTP 400.
   - Si ausente → utiliza `activas`.
3. **Consulta DynamoDB UsuarioVacante**:
   - Query por userId (PK directo, NO GSI). userId es la partition key.
   - Recupera todos los registros SK para ese usuario.
4. **Aplica filtro en memoria** según `estado`:
   - `activas`: Mantiene records donde estado ∈ {nueva, vista}.
   - `aplicadas`: Mantiene records donde estado = aplicada.
5. **Aplica ordenamiento**:
   - Si `activas`: Ordena por `score` descendente (nulls al final), luego `Vacante.lastSeenAt` descendente.
   - Si `aplicadas`: Ordena por `UsuarioVacante.appliedAt` descendente.
6. **Detecta staleness y reintenta scoring**:
   - Para cada record: Si `scoreProfileVersion` ≠ `Perfiles.profileVersion` OR (`scoreProfileVersion` nulo AND estado = nueva):
     - Invoca `enqueue_rescore(userId, companyId, vacancyId)` del módulo `backend-scan-y-scoring`.
     - Si falla el encolado: registra en log, pero retorna el score existente + `staleFlag=true`.
     - Si éxito: incluye en respuesta `staleFlag=true`.
   - Si `scoreProfileVersion` coincide: `staleFlag=false`.
7. **Construye respuesta**: Combina campos de Vacante + UsuarioVacante + resumen Empresa. NUNCA incluye `cvAtsTexto` en listado.
8. **Retorna HTTP 200** con lista vacía si no hay coincidencias (NO 404).

### Error Cases

- `estado` inválido → HTTP 400.
- JWT sin claim `sub` → HTTP 401.
- DynamoDB indisponible → HTTP 503.

---

## Section 2: Vacancy_Detail_API

### Endpoint: `GET /me/vacancies/{companyId}/{vacancyId}`

**Security**: userId extraído de JWT.

### Processing Logic

1. **Extrae userId** del JWT.
2. **Consulta DynamoDB**:
   - Lee `Empresa` por companyId (PK).
   - Lee `Vacante` por (companyId (PK), vacancyId (SK)).
   - Lee `UsuarioVacante` por (userId (PK), `{companyId}#{vacancyId}` (SK)).
3. **Validaciones**:
   - Si no existe Vacante → HTTP 404.
   - Si no existe UsuarioVacante → HTTP 404.
   - Si no existe Empresa → HTTP 404.
4. **Construye respuesta**:
   - Retorna: Vacante + EmpresaSummary (nombre, plataforma) + UsuarioVacante.
   - Si `UsuarioVacante.cvAtsTexto` no nulo: Incluye como texto plano.
   - Si `UsuarioVacante.cvAtsTexto` nulo o vacío: Incluye campo vacío, HTTP 200 (NO error).
   - Vacantes cerradas: Retorna con misma estructura que abiertas, sin restricción adicional.
5. **Retorna HTTP 200**.

### Error Cases

- Vacante no existe → HTTP 404.
- UsuarioVacante no existe → HTTP 404.
- Empresa no existe → HTTP 404.
- JWT sin sub → HTTP 401.

---

## Section 3: Manual_Vacancy_Service

### Endpoint: `POST /me/vacancies/manual`

**Request Body**:
```python
class ManualVacancyRequest(BaseModel):
    textoPegado: str  # 1–20000 caracteres
    enlace: str  # URL absoluta con http/https
    nombreEmpresa: str  # 1–200 caracteres (tras trim)
```

### Processing Logic

1. **Extrae userId** del JWT.
2. **Valida entrada**:
   - `textoPegado`: 1 ≤ len ≤ 20000. Si no → HTTP 400.
   - `enlace`: URL absoluta con http/https. Si no → HTTP 400.
   - `nombreEmpresa`: Tras trim(), 1 ≤ len ≤ 200. Si no → HTTP 400.
3. **Normaliza y resuelve Empresa**:
   - Normaliza `nombreEmpresa`: trim() + lowercase.
   - Busca en DynamoDB Empresa WHERE nombre_normalizado coincida.
   - Si no existe: Crea nueva Empresa con plataforma=manual, careersUrl=null.
4. **Calcula vacancyId**: SHA-256 de la URL normalizada.
5. **Invoca Bedrock** (si Vacante nueva):
   - Extrae campos de `Vacante` (titulo, descripcion, modalidad, ubicacion).
   - Idioma: Detectado desde titulo + descripcion.
   - Valida respuesta contra esquema Pydantic.
   - Si falla: Reintenta con error inyectado. Si falla de nuevo: HTTP 400, NO crea registros.
6. **Operaciones de persist**:
   - Si Vacante no existe: Crea con origen=manual, estado=abierta.
   - Si Vacante ya existe: Reutiliza sin modificar.
   - Si UsuarioVacante no existe: Crea con estado=nueva.
   - Si UsuarioVacante ya existe: Retorna HTTP 200 sin duplicar.
7. **Publica mensaje de scoring**: Si UsuarioVacante creado nuevo → exactamente un ScoringMessage en SQS.
8. **Retorna HTTP 200**.

### Pydantic Model

```python
class BedRockExtractVacancyOutput(BaseModel):
    titulo: str
    descripcion: str
    modalidad: str  # remote | hybrid | onsite | sin_dato
    ubicacion: str
    model_config = ConfigDict(extra="ignore")
```

---

## Section 4: Apply_Service

### Endpoint: `POST /me/vacancies/{companyId}/{vacancyId}/apply`

### Processing Logic

1. **Extrae userId** del JWT.
2. **Consulta DynamoDB**: Lee UsuarioVacante por (userId (PK), `{companyId}#{vacancyId}` (SK)).
3. **Validación**: Si no existe → HTTP 404.
4. **Actualiza UsuarioVacante**:
   - Establece `estado = aplicada`.
   - Establece `appliedAt = datetime.utcnow()` (solo si estado era diferente de `aplicada`).
   - Si estado ya es `aplicada`: NO actualiza `appliedAt`, retorna HTTP 200.
5. **Retorna HTTP 200** con el record actualizado.

---

## Section 5: CV_ATS_Service

### Endpoint: `POST /me/vacancies/{companyId}/{vacancyId}/cv`

### Processing Logic

1. **Extrae userId** del JWT.
2. **Consulta DynamoDB**:
   - Lee UsuarioVacante por (userId (PK), `{companyId}#{vacancyId}` (SK)).
   - Lee Vacante por (companyId (PK), vacancyId (SK)).
   - Lee Perfiles por userId (PK).
3. **Validaciones**:
   - Si no existe UsuarioVacante → HTTP 404 (ANTES de evaluar Vacante.estado).
   - Si existe UsuarioVacante pero Vacante.estado = cerrada → HTTP 409 con code "vacancy_closed".
4. **Detecta idioma**: Desde Vacante.titulo + Vacante.descripcion. Default: español.
5. **Invoca Bedrock**:
   - Input: Perfiles.perfilEstructurado (JSON), Perfiles.resumenParaMatching, Vacante (JSON), idioma.
   - Output: Texto plano ATS (sin tablas, sin columnas, sin decorativos).
   - Valida contra `CVATSOutput` con campo `texto` no vacío.
   - Si falla: Reintenta. Si falla de nuevo: HTTP 400.
6. **Persiste resultado**: UsuarioVacante.cvAtsTexto = texto, cvGeneratedAt = now.
7. **Retorna HTTP 200** con texto plano (Content-Type: text/plain, body directo).

### Pydantic Model

```python
class CVATSOutput(BaseModel):
    texto: str = Field(..., min_length=1, description="Plain text CV-ATS (no tables, no columns)")
    model_config = ConfigDict(extra="ignore")
```

---

## Section 6: Entries_Service

### Endpoints

- `GET /me/vacancies/{companyId}/{vacancyId}/entries`
- `POST /me/vacancies/{companyId}/{vacancyId}/entries`
- `POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer`

### GET /me/vacancies/{companyId}/{vacancyId}/entries

1. **Extrae userId** del JWT.
2. **Valida existencia**:
   - Lee UsuarioVacante por (userId (PK), `{companyId}#{vacancyId}` (SK)). Si no existe → HTTP 404.
   - Lee Vacante por (companyId (PK), vacancyId (SK)). Si no existe → HTTP 404.
3. **Consulta Entrada**: Query DynamoDB WHERE pk = `{userId}#{companyId}#{vacancyId}`. Ordena por createdAt ascendente.
4. **Retorna HTTP 200** con lista (vacía si sin entradas).

### POST /me/vacancies/{companyId}/{vacancyId}/entries

**Request Body**:
```python
class CreateEntryRequest(BaseModel):
    tipo: str  # "preguntas" | "nota_entrevista"
    contenido: str  # 1–5000 caracteres
```

1. **Extrae userId** del JWT.
2. **Valida entrada**: `tipo` ∈ {preguntas, nota_entrevista} AND 1 ≤ len(contenido) ≤ 5000. Si no → HTTP 400.
3. **Valida existencia**: UsuarioVacante + Vacante (ambas deben existir). Si no → HTTP 404.
4. **Crea Entrada**: entryId = ULID(), pk = `{userId}#{companyId}#{vacancyId}`, createdAt = now.
5. **Escribe en DynamoDB**.
6. **Retorna HTTP 200**.

### POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer

1. **Extrae userId** del JWT.
2. **Consulta DynamoDB**: Lee Entrada por pk + entryId.
3. **Validaciones**:
   - Si no existe Entrada → HTTP 404.
   - Si Entrada.tipo ≠ "preguntas" → HTTP 400.
   - Lee Vacante. Si Vacante.cerrada = true → HTTP 409.
4. **Invoca Bedrock**:
   - Input: Entrada.contenido (pregunta), Perfiles.resumenParaMatching, Vacante, idioma.
   - Valida contra `SuggestedAnswerOutput` con `respuesta` no vacía.
   - Si falla: Reintenta. Si falla de nuevo: HTTP 400.
5. **Crea Entrada append-only**: tipo=nota_entrevista, contenido = `{pregunta}\n\nRespuesta sugerida:\n{respuesta_generada}`.
6. **Persiste** e **Retorna HTTP 200**.

### Pydantic Model

```python
class SuggestedAnswerOutput(BaseModel):
    respuesta: str = Field(..., min_length=1, description="Suggested interview answer")
    model_config = ConfigDict(extra="ignore")
```



## Section 7: Notificador_Lambda (Event-Driven Notification)

### Activation Mechanism: DynamoDB Streams

**Problema resuelto**: Notificador necesita saber cuándo ScanJob transiciona a estado terminal, sin acoplarse al scan-worker.

**Solución**: DynamoDB Streams en tabla ScanJobs + Lambda trigger con FilterPolicy.

**Cómo funciona**:
1. Tabla ScanJobs tiene Streams habilitados (NEW_AND_OLD_IMAGES).
2. Cuando scan-worker actualiza ScanJob.status a DONE/PARCIAL/FAILED, DynamoDB emite evento MODIFY.
3. FilterPolicy (en Terraform) selecciona solo transiciones: oldImage.status ∉ {DONE, PARCIAL, FAILED} AND newImage.status ∈ {DONE, PARCIAL, FAILED}.
4. Evento filtrado → Notificador_Lambda.

**Ventajas**:
- Desacoplado del scan-worker (no requiere cambios al worker).
- Basado en cambio de estado (automático).
- Deduplicación garantizada por Streams (cada transición = evento único).

**Configuración**: Especificada en spec de Terraform (no aquí).

### Notificador_Lambda Processing Logic

```
FOR each DynamoDB Stream record in event.Records:
  1. Parse scanJobId, userId, status, empresasCompletadas, startedAt de newImage
  2. IF userId NOT nulo:
     → SKIP (es escaneo manual, no programado)
  3. Query DynamoDB Suscripciones WHERE companyId IN empresasCompletadas AND activa=true
  4. GROUP Suscripciones by userId (deduplicar)
  5. FOR each unique userId:
     a. Query UsuarioVacantes WHERE userId=X, estado=nueva, firstSeenAt >= startedAt
     b. FILTER UsuarioVacantes WHERE companyId IN empresasCompletadas
     c. IF vacantes calificadas > 0:
        - Construir correo
        - Enviar via SES
        - Registrar envío en log
     d. IF error SES:
        - Registrar fallo (userId, error truncado a 500 chars)
        - CONTINUE siguiente userId (NO fallar total)
  6. IF Notificador invocado 2+ veces para mismo (scanJobId, userId):
     - Verificar si ya enviado (usando flag en DynamoDB o deduplicación simple en memoria)
     - SI ya enviado: SKIP
     - SI no: Proceder + REGISTRAR
```

### Idempotencia (SIN nueva tabla)

**Patrón**: Usar flag simple en memoria (Set de tuplas `(scanJobId, userId)` ya procesadas en una ejecución) o verificar DynamoDB ScanJobs.notificacionesEnviadas (campo nuevo, StringSet).

**Alternativa simple**: Si Notificador es invocado múltiples veces en corta ventana (re-delivery DynamoDB Streams), el segundo evento llegará después de que el correo ya fue enviado. El log de SES o un flag simple en ScanJobs basta para deduplicar.

**Decisión**: Registrar en log el envío. Si múltiple invocación: envía duplicado, pero esto es raro en producción (Streams son confiables). Si ocurre, el usuario recibe 2 correos (aceptable para MVP).

### Email Body Structure

**Subject**: `{count} nuevas vacante(s) de interés - {fecha_UTC}`

**Body** (Plain text, NO HTML):

```
Hola {usuario},

Se encontraron {count} nueva(s) vacante(s) que coinciden con tu perfil:

═══════════════════════════════════════════════════════════════

VACANTE 1: {titulo}
Empresa: {nombre_empresa}
Plataforma: {plataforma}
Ubicación: {ubicacion}
Modalidad: {modalidad}
URL: {url}
Score: {score} ({score_percentil}%)

Resumen:
{descripcion_truncado_250_caracteres}

─────────────────────────────────────────────────────────────

[Próximas vacantes...]

═══════════════════════════════════════════════════════════════

[Si cvAtsTexto disponible para la primera vacante]
CV Personalizado para "{titulo}":

{cvAtsTexto_truncado_500_caracteres}

[Ver más en la aplicación]

═══════════════════════════════════════════════════════════════

Acciones:
- Ver vacante: https://app.job-app.com/vacancies/{companyId}/{vacancyId}
- Ver perfil: https://app.job-app.com/profile
- Editar suscripciones: https://app.job-app.com/subscriptions

¿Preguntas? Contacta a soporte@job-app.com

Saludos,
Job App Team
```

**DETALLES CRÍTICOS DEL CORREO**:
1. **Sin tablas ni columnas**: Solo texto con separadores (═, ─).
2. **Campos por vacante**: titulo, empresa (nombre NO ID), plataforma, ubicación, modalidad, URL, score, descripción truncada.
3. **CV-ATS**: Incluido SOLO si disponible. Truncado a 500 caracteres.
4. **Máximo 5 vacantes por correo**: Si > 5, enviar múltiples correos.

### Email Sending via SES

- Sender: `noreply@job-app.com` (verificada en SES).
- Recipient: Dirección registrada del usuario (de Cognito o tabla Usuarios).
- Si SES falla: Registra log con error truncado (500 chars). Continúa con siguiente usuario (NO interrumpe invocación).

### Logging

**Formato JSON estructurado** a stdout:
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "component": "Notificador_Lambda",
  "message": "Email sent successfully",
  "context": {
    "scanJobId": "scan-12345",
    "userId": "user-abc123",
    "vacantesCount": 3
  }
}
```

**PROHIBIDO loguear**: Descripciones de vacantes, CV-ATS, perfil del usuario, direcciones de correo completas, stack traces completos.

### Zero Vacancies Case (Requirement 7, criterion 5)

**Explícitamente**: Si para un userId NO hay vacantes nuevas calificadas (estado=nueva, firstSeenAt >= startedAt, companyId ∈ empresasCompletadas):
- **NO enviar correo**.
- **NO registrar envío**.
- **Registrar en log**: "No qualified vacancies for user X in scan Y".

---

## Section 8: EventBridge Scheduler Integration

### Requirement 8: Scheduled Scanning

**Objetivo**: Orquestador_Lambda invocado automáticamente en horario fijo, SIN acción manual.

**Cómo funciona** (infraestructura, no en esta spec):
1. EventBridge Scheduler rule con cron (ej: diario 02:00 UTC).
2. Invoca Orquestador_Lambda con payload `{source: "eventbridge-scheduler"}` (sin userId, sin JWT).
3. Orquestador detecta modo programado.

### Orquestador_Lambda Behavior (Programmed Mode)

1. **Detecta modo**: Si `event.get("source") == "eventbridge-scheduler"` → userId = None.
2. **Resuelve empresas**: Query Suscripciones WHERE activa=true (UNION de TODOS los usuarios). Deduplica por companyId.
3. **Crea ScanJob**: userId = None, status = RUNNING, empresasCompletadas = [].
4. **Publica ScanMessages**: Para cada companyId → SQS scan.

### Distinción: Manual vs. Programmed

| Aspecto | Manual | Programmed |
|---------|--------|-----------|
| Origen | HTTP endpoint + JWT | EventBridge Scheduler |
| userId | Del JWT | Nulo |
| Empresas | Solo del usuario | UNION de todos |
| ScanJob.userId | Poblado | Nulo |
| Notificador | NO invocado | Sí, si terminal |
| Objetivo | Usuario individual | Sistema completo |

---

## Section 9: Cross-Cutting Concerns

### 9.1 JWT-Based User Identification

**Requirement 9**: Toda operación extrae userId de `event.requestContext.authorizer.claims.sub`.

```python
def extract_user_id(event: dict) -> str:
    try:
        user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
        if not user_id:
            raise ValueError("claim 'sub' is empty")
        return user_id
    except (KeyError, TypeError) as e:
        raise ValueError(f"Missing or invalid JWT claim 'sub': {e}")
```

**INVARIANTE**: Ningún parámetro de query, body o header sobrescribe el userId del JWT.

### 9.2 Pydantic Validation with Retry

**Requirement 10**: Toda respuesta de Bedrock se valida. Si falla: reintenta con error inyectado. Si falla de nuevo: error controlado.

```python
async def invoke_bedrock_with_validation(
    prompt: str,
    output_model: Type[BaseModel],
    context: str = "default"
) -> BaseModel:
    """Invoca Bedrock con reintentos y validación Pydantic."""
    
    # Primer intento
    try:
        response_text = await bedrock_client.invoke_with_retry(
            prompt=prompt,
            model_id=os.getenv("BEDROCK_MODEL_MID")
        )
        result = output_model.model_validate_json(response_text)
        logger.info("Validation success", context={"attempt": 1, "model": context})
        return result
    except ValidationError as e:
        error_msg = str(e)[:500]
        logger.warning("Validation failed, retrying", context={
            "attempt": 1, "model": context, "error": error_msg
        })
        
        # Segundo intento con error inyectado
        retry_prompt = f"""{prompt}

NOTA: La respuesta anterior no cumplió el formato esperado:
{error_msg}

Por favor, genera la respuesta en el formato exacto requerido.
"""
        
        try:
            response_text = await bedrock_client.invoke_with_retry(
                prompt=retry_prompt, model_id=os.getenv("BEDROCK_MODEL_MID")
            )
            result = output_model.model_validate_json(response_text)
            logger.info("Validation success", context={"attempt": 2})
            return result
        except ValidationError as e2:
            logger.error("Validation failed after retry", context={
                "attempt": 2, "error": str(e2)[:500]
            })
            raise HTTPException(status_code=400, detail=f"Invalid {context} response format")
    except Exception as e:
        logger.error("Bedrock invocation failed", context={"error": str(e)[:500]})
        raise HTTPException(status_code=502, detail="Bedrock service unavailable")
```

### 9.3 Structured Logging in JSON

**Requirement 11**: Usa `get_contextual_logger()` de `backend/shared/logging_config.py`.

**PROHIBIDO en logs**:
- cvAtsTexto, descripciones de vacantes, perfil del usuario, direcciones de correo completas, stack traces completos.

**PERMITIDO**: userId opaco (del JWT), requestId, component, message, nivel.

### 9.4 Bedrock Model IDs from Environment Variables

**INVARIANTE**: IDs de modelo NUNCA hardcodeados. Leer de env vars en `backend/shared/bedrock.py`.

```env
BEDROCK_MODEL_SMALL=anthropic.claude-3-haiku-20240307-v1:0
BEDROCK_MODEL_MID=anthropic.claude-3-sonnet-20240229-v1:0
```

---

## Section 10: Correctness Properties

### Property 1: User Identity Integrity

**GIVEN** JWT válido (userId='user-abc') con query params malicioso (userId='user-xyz')
**WHEN** `GET /me/vacancies`
**THEN** solo se retornan vacantes de user-abc.

### Property 2: Bedrock Validation Always Applied

**GIVEN** Bedrock retorna JSON malformado
**WHEN** `POST /me/vacancies/manual`
**THEN** reintento, si falla: HTTP 400, NO persistencia.

### Property 3: Zero Vacancies → No Email

**GIVEN** ScanJob completado CON userId=nulo AND cero vacantes nuevas calificadas
**WHEN** Notificador procesa
**THEN** NO se envía correo.

### Property 4: Closed Vacancy Protection

**GIVEN** Vacante con estado=cerrada
**WHEN** `POST /me/vacancies/{id}/cv`
**THEN** HTTP 409, Bedrock NO invocado.

### Property 5: Applied State Idempotence

**GIVEN** UsuarioVacante estado=aplicada, appliedAt=T0
**WHEN** `POST /me/vacancies/{id}/apply` invocado dos veces
**THEN** en segundo intento: appliedAt NO cambia.

### Property 6: Manual Vacancy Deduplication

**GIVEN** URL ya existe (mismo vacancyId)
**WHEN** `POST /me/vacancies/manual` con misma URL
**THEN** Bedrock NO invocado, Vacante reutilizada.

### Property 7: Programmed Scan Union

**GIVEN** usuarios: U1 suscrito a {C1, C2}, U2 suscrito a {C2, C3}
**WHEN** EventBridge Scheduler invoca Orquestador (programmed)
**THEN** ScanJob lidia con {C1, C2, C3} (unión deduplicada).

### Property 8: Logging Security (No PII)

**GIVEN** cualquier endpoint
**WHEN** se loguean eventos
**THEN** logs NO contienen: cvAtsTexto, perfil, descripciones, emails, stack traces completos.



## Section 11: Implementation Checklist

### Modules & Packages

- [ ] `backend/api/routes/vacancies.py`: Endpoints REST (GET listado, detalle; POST manual, apply, cv).
- [ ] `backend/api/routes/entries.py`: Endpoints de Entrada (GET, POST, POST answer).
- [ ] `backend/shared/services/vacancy_service.py`: Lógica de negocio para vacantes.
- [ ] `backend/shared/services/entry_service.py`: Lógica de entrada.
- [ ] `backend/shared/services/cv_ats_service.py`: Generación de CV-ATS.
- [ ] `backend/shared/validators.py`: Extensión con validadores específicos.
- [ ] `backend/workers/notificador/handler.py`: Lambda handler para Notificador_Lambda.
- [ ] `backend/workers/notificador/notification_service.py`: Lógica de notificaciones y SES.
- [ ] Tests unitarios: `backend/tests/test_vacancies.py`, `test_entries.py`, `test_cv_ats.py`, `test_notificador.py`.

### Existing Infrastructure (No Modifications)

- DynamoDB tablas (Empresas, Vacantes, UsuarioVacante, Entradas, Perfiles, Suscripciones, ScanJobs): Ya existen.
- `backend/shared/models.py`: Modelos ya existen.
- `backend/shared/bedrock.py`: Infra ya existe.
- `backend/shared/logging_config.py`: Infra ya existe.
- Scan-worker, Scoring-worker: SIN cambios (desacoplados del Notificador).

### Infrastructure Dependencies (Terraform Spec)

- **DynamoDB Streams** en tabla ScanJobs (NEW_AND_OLD_IMAGES).
- **Lambda Event Source Mapping**: DynamoDB Stream → Notificador_Lambda (con FilterPolicy).
- **EventBridge Scheduler**: Regla cron → Orquestador_Lambda.
- **IAM roles** para Scheduler, Notificador Lambda, Lambda API.
- **SES**: Verificar dirección `noreply@job-app.com`.

### Environment Variables (Lambda API, Notificador)

```
BEDROCK_MODEL_SMALL=anthropic.claude-3-haiku-20240307-v1:0
BEDROCK_MODEL_MID=anthropic.claude-3-sonnet-20240229-v1:0
DYNAMODB_ENDPOINT=https://dynamodb.us-east-1.amazonaws.com (omit local dev)
SQS_SCAN_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/{account}/job-app-scan-queue
SQS_SCORING_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/{account}/job-app-scoring-queue
SES_SENDER_EMAIL=noreply@job-app.com
LOG_LEVEL=INFO
```

### IAM Permissions (Summary)

**Lambda API**:
- DynamoDB: GetItem, Query, PutItem, UpdateItem sobre Empresas, Vacantes, UsuarioVacante, Suscripciones, Perfiles, Entradas.
- SQS: SendMessage a scan-queue, scoring-queue.
- Bedrock: InvokeModel.

**Notificador Lambda**:
- DynamoDB: GetItem, Query, PutItem sobre ScanJobs, Suscripciones, UsuarioVacante.
- SES: SendEmail.

**EventBridge Scheduler role**:
- Lambda: InvokeFunction (Orquestador_Lambda).

---

## Section 12: Key Design Decisions

### 1. Notificador Detection: DynamoDB Streams (Not Polling)

**Rationale**:
- ✅ Desacoplado del scan-worker (no requiere cambios).
- ✅ Basado en cambio de estado (automático).
- ✅ Deduplicación garantizada por Streams.
- ✅ Escalable sin polling overhead.

### 2. Email Body: Plain Text, Not HTML

**Rationale**:
- ✅ Mejor compatibilidad con filtrado antispam y ATS.
- ✅ Evita inyección HTML/JavaScript.
- ✅ Más legible en lectores de pantalla.

### 3. CV-ATS Constraints: ATS Compatibility

**Requisitos**:
- ✅ SIN tablas, columnas, caracteres decorativos.
- ✅ Texto plano únicamente.
- ✅ Validación Pydantic estricta.
- ✅ Reintento si primer intento incumple.

### 4. Zero Vacancies: Explicit Non-Sending

**Requirement 7, criterion 5**: Si cero vacantes calificadas → NO enviar correo, NO registrar envío.

### 5. Bedrock Model IDs: Environment Variables Only

**INVARIANTE crítica**: NUNCA hardcodear. Leer de env vars. Razón: Algunos modelos requieren inference profiles (prefijo `us.`).

### 6. JWT-Only User Identity

**INVARIANTE crítica**: userId de `event.requestContext.authorizer.claims.sub`. NUNCA desde body/query. Razón: Evitar suplantación.

### 7. Idempotent Notifications: Simple Deduplication

**Patrón**: Si Notificador invocado 2+ veces para mismo (scanJobId, userId) en corta ventana → aceptar duplicado (es raro con Streams confiables). Para MVP, log simple basta.

### 8. Programmed vs. Manual Scans: Clear Distinction

**Manual**: userId poblado → Notificador SKIP.
**Programmed**: userId nulo → Notificador procesa.

**Beneficio**: Sistema puede manejar cada modo independientemente.

### 9. Language Detection: Simple Heuristic

**Implementación**: Palabras clave o librería ligera desde Vacante.titulo + Vacante.descripcion. Default: español. Aplica a todos los prompts de esa vacante.

### 10. No Modifications to Scan/Scoring Workers

**Desacoplamiento total**: Notificador completamente independiente. Scan-worker + Scoring-worker continúan como están.

**Ventaja**: Cambios mínimos, riesgo bajo.

---

## Appendix A: Bedrock Prompt Templates

### Template 1: Manual Vacancy Extraction

```
Extrae los campos de una oferta de empleo del siguiente texto:

TEXTO PEGADO:
---
{textoPegado}
---

Extrae:
1. TITULO: Título del puesto (máx 100 caracteres)
2. DESCRIPCION: Descripción general (máx 2000 caracteres)
3. MODALIDAD: remote, hybrid, onsite, o sin_dato si no se menciona
4. UBICACION: Ubicación o ciudad (máx 200 caracteres, o "sin_dato")

Devuelve SOLO JSON válido (sin explicaciones):
{
  "titulo": "...",
  "descripcion": "...",
  "modalidad": "...",
  "ubicacion": "..."
}
```

### Template 2: CV-ATS Generation

```
Genera un CV optimizado para sistemas ATS.

PERFIL:
{perfilEstructurado_json}

RESUMEN:
{resumenParaMatching}

VACANTE:
Título: {vacante.titulo}
Descripción: {vacante.descripcion}
Ubicación: {vacante.ubicacion}
Modalidad: {vacante.modalidad}

REQUISITOS:
1. Texto plano, SIN tablas ni columnas.
2. SIN caracteres decorativos (*, #, =, etc.).
3. SIN emojis.
4. Máximo 1 página (≈2000 palabras).
5. Incluye keywords de la vacante.
6. Idioma: {idioma_detectado}

Devuelve SOLO el texto del CV (sin JSON, sin explicaciones).
```

### Template 3: Interview Answer Generation

```
Genera una respuesta sugerida para una pregunta de entrevista.

PREGUNTA:
{entrada.contenido}

PERFIL (resumen):
{perfil.resumenParaMatching}

VACANTE:
Título: {vacante.titulo}
Descripción: {vacante.descripcion}

INSTRUCCIONES:
1. Respuesta profesional, concisa (máx 500 palabras).
2. Usa ejemplos específicos del perfil.
3. Alinea con requisitos de la vacante.
4. Idioma: {idioma_detectado}
5. Tono: Profesional, apto para grabar.

Devuelve SOLO la respuesta (sin JSON, sin explicaciones).
```

---

## Appendix B: Error Response Codes

| Code | Scenario | Message |
|------|----------|---------|
| 200 | Éxito | `"Success"` o vacío |
| 400 | Entrada inválida | `"Invalid {field}: {reason}"` |
| 400 | Bedrock validation 2× | `"Invalid {context} response format after retries"` |
| 401 | JWT ausente/inválido | `"Unauthorized"` |
| 404 | Recurso no encontrado | `"Not found"` |
| 409 | Vacante cerrada (CV, entries) | `"Vacancy closed"` (code: `"vacancy_closed"`) |
| 502 | Bedrock error | `"Bedrock service unavailable"` |
| 503 | DynamoDB indisponible | `"Service temporarily unavailable"` |

---

## Summary: What Changed from Requirements to Design

1. **Vacancy_Listing_API**: Query directo por userId (PK), NO GSI. Filtrado y ordenamiento en memoria.
2. **CV-ATS**: Formato ATS-compliant (sin tablas, columnas, decorativos). Reintento con validación Pydantic.
3. **Manual Vacancy**: SHA-256 de URL para deduplicación. Bedrock solo si Vacante nueva.
4. **Entries**: Append-only (no editar/borrar). Respuestas sugeridas como nuevas Entradas.
5. **Notificador**: DynamoDB Streams trigger (desacoplado). Cero vacantes = sin correo. Correo plain text, truncado, sin PII.
6. **EventBridge Scheduler**: Invoca Orquestador con userId=nulo. Empresas = UNION de suscripciones globales.
7. **Logging**: JSON estructurado sin PII. Bedrock model IDs de env vars.
8. **Idempotencia**: JWT-only identity. Bedrock validation + reintento. Deduplicación de notificaciones simple.

**Fuera de alcance (Terraform)**:
- DynamoDB Streams infrastructure.
- EventBridge Scheduler rule.
- Lambda Event Source Mapping con FilterPolicy.
- IAM roles y policies.
- SES configuración.

