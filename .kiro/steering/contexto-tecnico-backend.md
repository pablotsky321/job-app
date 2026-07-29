---
inclusion: manual
---

# Contexto técnico — Backend

> Recorte autosuficiente de contexto_maestro_job_search.md para las specs de backend.
> No requiere leer contexto-tecnico-frontend.md ni contexto-tecnico-infra.md.

## Alcance (qué construye el backend)

1. Auth con Cognito (usuarios pre-creados, Hosted UI) — validación de JWT, extracción de userId
2. Perfil: endpoint de parseo de CV con IA → estructurado y editable
3. Sugerencia de cargos objetivo
4. Descubrimiento en cascada (board API → JSON-LD → HTML+LLM)
5. **Scoring de match con explicación** ← diferenciador
6. Escaneo asíncrono con seguimiento de progreso (SQS + workers)
7. Ciclo de vida de vacantes con detección robusta de cierres
8. Vacante manual por texto pegado + link
9. CV-ATS en texto plano (el backend genera el texto; la descarga es responsabilidad del frontend)
10. Banco de preguntas y notas por vacante
11. Escaneo programado (EventBridge Scheduler) + correo (SES)

Fuera de alcance: ver `fuera-de-alcance.md`.

## Modelo de datos (DynamoDB) — seis tablas separadas

### `Empresas` (global, compartida)

| Campo | Tipo | Notas |
|---|---|---|
| `companyId` (**PK**) | S | slug, ej. `bancolombia` |
| `nombre` | S | |
| `careersUrl` | S | null si origen manual |
| `plataforma` | S | `greenhouse` \| `lever` \| `jsonld` \| `html` \| `manual` |
| `boardToken` | S | identificador del board, si aplica |
| `lastScannedAt` | S | ISO 8601 |
| `lastScanStatus` | S | `OK` \| `FAILED` \| `EMPTY_SOSPECHOSO` \| `EMPTY_LEGITIMO` |
| `lastVacancyCount` | N | conteo del último escaneo exitoso |
| `consecutiveFailures` | N | |
| `createdAt` | S | |

La empresa **nunca se elimina**. Quitar ≠ borrar.

### `Vacantes` (global, compartida)

| Campo | Tipo | Notas |
|---|---|---|
| `companyId` (**PK**) | S | |
| `vacancyId` (**SK**) | S | SHA-256 de la URL normalizada. Sin URL: hash de `companyId+titulo+ubicacion` |
| `titulo` | S | |
| `descripcion` | S | texto completo |
| `ubicacion` | S | |
| `modalidad` | S | `remoto` \| `presencial` \| `hibrido` \| `sin_dato` — nunca adivinar |
| `url` | S | link oficial, siempre se guarda |
| `publishedAt` | S | si la fuente lo da |
| `origen` | S | `board_api` \| `json_ld` \| `html_llm` \| `manual` |
| `firstSeenAt` / `lastSeenAt` | S | |
| `missCount` | N | ver clasificación de escaneo abajo |
| `estado` | S | `abierta` \| `cerrada` |
| `ttl` | N | epoch; solo se fija al cerrar y si nadie la aplicó |

La clave es la URL, no empresa+cargo+ubicación (título/ubicación los produce un LLM, no son deterministas).

### `UsuarioVacante` (por usuario)

| Campo | Tipo | Notas |
|---|---|---|
| `userId` (**PK**) | S | `sub` de Cognito |
| `sk` (**SK**) | S | `{companyId}#{vacancyId}` |
| `estado` | S | `nueva` \| `vista` \| `aplicada` \| `archivada` |
| `score` | N | 0–100 |
| `scoreDetalle` | M | ver formato de salida del scoring abajo |
| `scoreProfileVersion` | N | versión del perfil con la que se calculó |
| `appliedAt` | S | |
| `cvAtsTexto` | S | texto plano del CV generado |
| `cvGeneratedAt` | S | |
| `updatedAt` | S | |

> **Nota (desactualizado):** el valor `archivada` listado arriba fue una intención de diseño original que nunca se materializó en el código real. El backend implementado (`backend-vacantes-y-notificaciones/tasks.md`, tarea 1.1, y su `requirements.md`) persiste `estado` con exactamente estos cuatro valores: `nueva` \| `vista` \| `aplicada` \| `filtered_out`. `filtered_out` se asigna cuando el Scoring_Worker descarta una vacante por el Prefiltro_Cargos. Ver también `.kiro/specs/frontend-spa/design.md` (tipo `VacancyListItem`), que ya usa los valores reales.

Sin GSI intencionalmente: se consulta por `userId` y se filtra/ordena en la Lambda.

### `Entradas` (banco de preguntas y notas)

| Campo | Tipo | Notas |
|---|---|---|
| `pk` (**PK**) | S | `{userId}#{companyId}#{vacancyId}` |
| `entryId` (**SK**) | S | ULID |
| `tipo` | S | `preguntas` \| `nota_entrevista` |
| `contenido` | S / L | texto libre, o lista de `{pregunta, respuesta}` |
| `ronda` | N | opcional |
| `createdAt` | S | |

Append-only: soporta rondas sucesivas sin rediseño.

### `Perfiles` (por usuario)

| Campo | Tipo | Notas |
|---|---|---|
| `userId` (**PK**) | S | |
| `cvOriginalTexto` | S | lo que el usuario pegó |
| `perfilEstructurado` | M | ver abajo |
| `resumenParaMatching` | S | resumen ≤500 palabras, generado una vez |
| `resumenGenerating` | BOOL | `true` mientras la generación asíncrona está en curso; el frontend hace polling de `GET /me/profile` esperando `false` |
| `cargosSugeridos` | L | |
| `cargosActivos` | L | |
| `profileVersion` | N | se incrementa en cada guardado de perfil o cargos |
| `updatedAt` | S | |

`perfilEstructurado`: `experienciaLaboral[]` (con `proyectos[]` anidados), `proyectosPersonales[]`,
`formacionAcademica[]` (separada de cursos/certificaciones), `cursosCertificaciones[]`.

`resumenParaMatching` evita meter el perfil completo en cada prompt de scoring; se regenera solo
cuando cambia `profileVersion`.

### Generación asíncrona de `resumenParaMatching`

`PUT /me/profile` guarda el perfil, incrementa `profileVersion`, pone `resumenGenerating=true` y
responde de inmediato. Antes de responder, invoca **de forma asíncrona** (`InvocationType=Event`)
la propia Lambda `"api"` para que genere `resumenParaMatching` vía Bedrock (modelo pequeño) y, al
terminar, ponga `resumenGenerating=false`.

Sin cola ni Lambda nueva — reutiliza la Lambda `"api"` existente con un segundo modo de invocación,
evitando infraestructura desproporcionada para un flujo que corre en segundos (ver
`decisiones-invertidas.md`: cola SQS dedicada descartada por este mismo motivo).

`POST /me/profile/roles/suggest` debe devolver **HTTP 424** si `resumenGenerating == true` en el
momento de la petición (contrato ya asumido por `frontend-spa`, que hace polling de 3s / tope 30s
sobre `GET /me/profile` ante ese 424).

### `Suscripciones` (usuario ↔ empresa)

| Campo | Tipo | Notas |
|---|---|---|
| `userId` (**PK**) | S | |
| `companyId` (**SK**) | S | |
| `activa` | BOOL | quitar ≠ borrar |
| `addedAt` | S | |

GSI `porEmpresa`: PK `companyId`, SK `userId`. Para que el worker de scoring sepa a qué usuarios
puntuar cuando aparece una vacante nueva.

### `ScanJobs`

| Campo | Tipo | Notas |
|---|---|---|
| `jobId` (**PK**) | S | UUID |
| `userId` | S | null si es escaneo programado global |
| `status` | S | `RUNNING` \| `DONE` \| `PARCIAL` \| `FAILED` |
| `empresasTotal` | N | |
| `empresasCompletadas` | SS | String Set |
| `empresasOmitidas` | L | dentro de la ventana de frescura |
| `empresasFallidas` | L | |
| `startedAt` | S | |
| `ttl` | N | 7 días |

## Arquitectura de cómputo

API Gateway (Cognito Authorizer)
└──> Lambda "api" (FastAPI + Mangum, monolítica)
├──> DynamoDB
├──> Bedrock (llamadas cortas y síncronas)
└──> SQS scan ──┐
│
EventBridge Scheduler ──> Lambda "orquestador" ──> SQS scan
│
┌───────────────────────┘
▼
Lambda "scan-worker" (concurrencia reservada: 5)
│
├──> DynamoDB (upsert vacantes)
└──> SQS scoring
│
▼
Lambda "scoring-worker" (concurrencia reservada: 3)
│
├──> Bedrock
└──> DynamoDB

Lambda "notificador" (al cerrar un job programado) ──> SES


Una sola Lambda para toda la API síncrona (menos funciones en Terraform, FastAPI genera OpenAPI gratis).
Workers asíncronos van separados por tener perfiles de concurrencia y timeout distintos. Dos colas
(scan, scoring) porque tienen dominios de falla distintos: si el scoring falla, no se reintenta la
descarga de la página. Cada cola con su DLQ (`maxReceiveCount: 3`).

## Flujo de descubrimiento

### Cascada de extracción (por empresa), en orden, se para en la primera que funcione

1. **API de board pública** — si `plataforma` es `greenhouse` o `lever`, endpoint JSON sin auth. Cero tokens.
2. **JSON-LD `JobPosting`** — bloque `application/ld+json` en el HTML. Parseo directo, cero tokens.
3. **HTML → LLM** — descargar, limpiar por código (quitar `<script>`, `<style>`, atributos de estilo,
   etiquetas vacías) una sola vez por página, pasar a un modelo pequeño de Bedrock. Deduplicar después.

Semilla: 8–10 empresas verificadas a mano antes de comprometerse.

### Escaneo asíncrono

POST /scans
Lambda orquestador:
1. resuelve empresas activas del usuario (Suscripciones)
2. filtra por ventana de frescura
3. crea ScanJob { empresasTotal: N, empresasCompletadas: {} }
4. publica N mensajes en SQS scan
5. responde { jobId } de inmediato

SQS scan → Lambda scan-worker (UNA empresa por mensaje):
1. ejecuta la cascada
2. clasifica el resultado
3. upsert de vacantes en DynamoDB
4. encola vacantes nuevas en SQS scoring
5. ADD empresasCompletadas :companyId

GET /scans/{jobId} ← polling del frontend; se detiene en DONE/PARCIAL/FAILED


Asíncrono porque API Gateway corta la integración a los ~29 segundos.

### Clasificación del resultado y cierre de vacantes

| Resultado | Condición | Acción |
|---|---|---|
| `OK` | respuesta válida, N > 0 vacantes | evaluar cierres normalmente |
| `FAILED` | timeout, HTTP 4xx/5xx, JSON inválido, excepción | no tocar nada, `consecutiveFailures += 1` |
| `EMPTY_SOSPECHOSO` | 0 vacantes pero `lastVacancyCount > 0` | no tocar nada, tratar como fallo |
| `EMPTY_LEGITIMO` | 0 vacantes y `lastVacancyCount == 0` | OK, la empresa no tiene vacantes |

Cierre con margen (solo tras un escaneo `OK`): no aparece → `missCount += 1`; reaparece → `missCount = 0`;
`missCount >= 2` → `estado = cerrada` (ttl 30 días si nunca se aplicó). Vacantes `origen = manual` nunca
se auto-cierran.

Con `consecutiveFailures >= 3`, exponer el estado en la respuesta de `/me/companies` para que el
frontend muestre el aviso (contrato: ver contexto-tecnico-frontend.md si necesitas el detalle de UI).

### Ventana de frescura

| Tipo de fuente | Ventana |
|---|---|
| `board_api` / `json_ld` (cero tokens) | 1 hora |
| `html_llm` (caro) | 12 horas |

Un escaneo dentro de la ventana no es un fallo: la respuesta debe distinguir "sin cambios" de "error".

### Vacante manual

Usuario pega texto de la descripción + link por separado. El link nunca se descarga ni se escanea.
Si la empresa no existe en el catálogo, se crea con lo mínimo pero el usuario no queda suscrito
(no hay `careersUrl` escaneable).

## Scoring de match (diferenciador principal)

**Prefiltro por código** antes de gastar tokens: comparación normalizada del título de la vacante
contra cargos activos (minúsculas, sin tildes, solapamiento de tokens). Solo lo que pasa va a scoring.

**Cuándo se calcula:** una vez por par (usuario, vacante), guardado en `UsuarioVacante`. Nunca al
cargar una pantalla. Siempre desde la cola `scoring`, nunca dentro de una petición HTTP.

**Formato de salida:**
```json
{
  "score": 78,
  "veredicto": "buen_encaje",
  "coincidencias": ["Python", "AWS Lambda", "DynamoDB"],
  "faltantes": ["Kubernetes", "3 años de experiencia (tienes 1)"],
  "resumen": "Encaja con tu stack de backend serverless; el requisito de K8s es el vacío principal."
}
```
`veredicto` ∈ `{ excelente, buen_encaje, parcial, bajo }`.

**Rescoring cuando cambia el perfil (híbrido):** al guardar perfil o cargos, `profileVersion += 1`
sin recalcular nada en el momento. Al cargar el listado, el backend detecta scores con
`scoreProfileVersion` desfasado, los encola en `scoring`, y responde de inmediato con los scores
viejos (el frontend los marca como "actualizando…").

## Contratos de API que implementa esta Lambda

Todo detrás del Cognito Authorizer. `userId` sale siempre del JWT, nunca del body.

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/me/profile/parse` | pega CV → perfil estructurado (no guarda) |
| `GET` | `/me/profile` | |
| `PUT` | `/me/profile` | guarda perfil, incrementa `profileVersion` |
| `POST` | `/me/profile/roles/suggest` | sugiere cargos desde el perfil |
| `PUT` | `/me/profile/roles` | fija `cargosActivos`, incrementa `profileVersion` |
| `GET` | `/companies` | catálogo compartido |
| `POST` | `/companies` | agrega empresa por URL de carreras; detecta plataforma |
| `GET` | `/me/companies` | suscripciones con estado y `lastScanStatus` |
| `POST` | `/me/companies/{companyId}` | **crea** la Suscripción (idempotente: no-op si ya activa, la activa si existía inactiva) |
| `PUT` | `/me/companies/{companyId}` | activar/desactivar una Suscripción **ya existente**; 404 si nunca se creó (usar `POST` para el alta) |
| `POST` | `/scans` | → `{ jobId }` |
| `GET` | `/scans/{jobId}` | progreso |
| `GET` | `/me/vacancies?estado=activas\|aplicadas` | listado |
| `GET` | `/me/vacancies/{companyId}/{vacancyId}` | detalle |
| `POST` | `/me/vacancies/manual` | texto pegado + link |
| `POST` | `/me/vacancies/{companyId}/{vacancyId}/apply` | marca como aplicada |
| `POST` | `/me/vacancies/{companyId}/{vacancyId}/cv` | genera CV-ATS |
| `GET` | `/me/vacancies/{companyId}/{vacancyId}/entries` | preguntas y notas |
| `POST` | `/me/vacancies/{companyId}/{vacancyId}/entries` | agrega entrada |
| `POST` | `/me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer` | la IA ayuda a redactar respuesta |

Modelos Pydantic compartidos en `backend/shared/models.py`. FastAPI genera OpenAPI automáticamente
(el frontend consume ese archivo para generar sus tipos TS — no lo dupliques).

## Tareas de Bedrock

Región `us-east-1`. Todas las salidas se validan con Pydantic, con un reintento si el parseo falla.

| Tarea | Tamaño de modelo | Entrada | Salida |
|---|---|---|---|
| Parsear CV pegado | pequeño | texto del CV | `PerfilEstructurado` |
| Generar `resumenParaMatching` | pequeño | perfil estructurado | texto ≤500 palabras |
| Sugerir cargos | pequeño | `resumenParaMatching` | `string[]` |
| Extraer vacantes de HTML limpio | pequeño | HTML limpio | `Vacante[]` |
| Extraer vacante de texto pegado | pequeño | texto | `Vacante` |
| Scoring de match | pequeño/intermedio | `resumenParaMatching` + vacante + cargos activos | objeto de scoring |
| Redactar CV-ATS | intermedio | perfil completo + vacante | texto plano |
| Apoyo para responder preguntas | intermedio | pregunta + `resumenParaMatching` + vacante | texto |

CV-ATS y respuestas de entrevista se generan en el idioma de la vacante, no siempre en español.

## Notificaciones (SES)

Correo solo en escaneos automáticos/programados, nunca en manuales. SES opera en sandbox: solo
destinatarios verificados, 200 correos/día, 1 msg/seg.

## Tests

Solo funciones puras: normalización de URL y hash de dedup, limpieza de HTML, detección de
plataforma desde URL, prefiltro de cargos, lógica de `missCount` y clasificación de resultado de escaneo.