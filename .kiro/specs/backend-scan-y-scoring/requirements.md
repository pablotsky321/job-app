# Requirements Document

## Introduction

Esta spec (`backend-scan-y-scoring`) es la continuación de `backend-core` (ya implementado). Cubre el
descubrimiento asíncrono de vacantes por cascada (board API → JSON-LD → HTML+LLM), el ciclo de vida
de un `ScanJob` (creación, fan-out, progreso, detección de jobs zombis), el escaneo por empresa
(`Scan_Worker`), el scoring de match por usuario (`Scoring_Worker`), el contrato de polling
`GET /scans/{jobId}`, y la interfaz de detección de rescoring cuando el perfil del usuario cambia.

Los modelos de dominio compartidos (`Empresa`, `Vacante`, `Suscripcion`, `ScanJob`, `Perfiles`) y los
helpers de `backend/shared/` (`models.py`, `db.py`, `bedrock.py`, `validators.py`, `normalization.py`,
`errors.py`, `logging_config.py`) ya existen y son la fuente de verdad. Esta spec los consume y
extiende con los campos y modelos nuevos que sus workers necesitan; no los redefine.

Fuera de esta spec: listado y detalle de vacantes (`GET /me/vacancies*`), vacante manual, CV-ATS,
banco de preguntas y notas, notificaciones por correo (SES), Terraform/infraestructura, frontend.

## Glossary

- **Orquestador**: función Lambda que atiende `POST /scans` y la invocación programada global;
  resuelve las Empresas a escanear, aplica la Ventana_Frescura, crea el registro ScanJob y publica
  mensajes en SQS_Scan.
- **Scan_Worker**: función Lambda (concurrencia reservada 5) disparada por SQS_Scan, un mensaje por
  Empresa; ejecuta la Cascada_Descubrimiento, clasifica el resultado, hace upsert de Vacantes, encola
  mensajes en SQS_Scoring y actualiza `ScanJob.empresasCompletadas`.
- **Scoring_Worker**: función Lambda (concurrencia reservada 3) disparada por SQS_Scoring, un mensaje
  por par (userId, Vacante); aplica el Prefiltro_Cargos, invoca Bedrock_Client cuando corresponde y
  persiste el resultado en UsuarioVacante.
- **Cascada_Descubrimiento**: secuencia ordenada de métodos de extracción (Board_API_Client, luego
  JsonLd_Extractor, luego Html_Llm_Extractor) ejecutada por Scan_Worker para una Empresa, que se
  detiene en el primer método que devuelve una o más vacantes.
- **Board_API_Client**: método de extracción que consulta la API JSON pública de Greenhouse o Lever.
- **JsonLd_Extractor**: método de extracción que parsea el bloque `application/ld+json` de tipo
  `JobPosting` en el HTML de la página de carreras de una Empresa.
- **Html_Llm_Extractor**: método de extracción que limpia el HTML de la página de carreras de una
  Empresa y lo somete a Bedrock_Client para extraer vacantes.
- **Bedrock_Client**: módulo existente `backend/shared/bedrock.py` usado para invocar modelos de
  Amazon Bedrock. Único módulo que lee `BEDROCK_MODEL_SMALL` / `BEDROCK_MODEL_MID`.
- **Empresa**: registro de empresa en el catálogo compartido (definido en `backend-core`).
- **Vacante**: registro de vacante en el catálogo compartido (definido en `backend-core`, extendido
  por esta spec).
- **Suscripcion**: relación usuario-empresa (definida en `backend-core`).
- **UsuarioVacante**: registro por usuario que guarda el estado y el score de una Vacante para un
  usuario (modelo nuevo introducido por esta spec).
- **Perfil**: registro de perfil de usuario, incluye `profileVersion` y `cargosActivos` (definido en
  `backend-core`).
- **ScanJob**: registro que rastrea el progreso de un ciclo de escaneo (definido en `backend-core`,
  extendido por esta spec).
- **Ventana_Frescura**: tiempo mínimo transcurrido desde el último escaneo de una Empresa antes de
  que vuelva a ser elegible para re-escaneo; 1 hora para `board_api`/`json_ld`, 12 horas para
  `html_llm`.
- **Prefiltro_Cargos**: función pura que determina si el título de una Vacante comparte al menos una
  cantidad configurable de tokens significativos con los `cargosActivos` del usuario.
- **Scans_API**: interfaz HTTP que expone `POST /scans` (atendido por Orquestador) y
  `GET /scans/{jobId}` (consulta de progreso).
- **SQS_Scan**: cola SQS con un mensaje por Empresa a escanear.
- **SQS_Scoring**: cola SQS con un mensaje por par (userId, Vacante) a puntuar.
- **Rescoring_Detector**: función pura, invocable por cualquier consumidor que lea registros
  UsuarioVacante, que determina si un score almacenado está desfasado respecto al `profileVersion`
  vigente del usuario y lo encola para reprocesamiento asíncrono.

## Requirements

### Requirement 1: Extensión de los modelos de dominio compartidos

**User Story:** Como desarrollador backend, quiero que los modelos compartidos incluyan los campos
que necesitan Scan_Worker y Scoring_Worker, para que ningún worker redefina o duplique un modelo por
su cuenta.

#### Acceptance Criteria

1. THE Vacante model SHALL include a vacancyId field, represented as a lowercase 64-character
   hexadecimal string equal to the SHA-256 hash of the vacancy's normalized URL.
2. THE Vacante model SHALL include an estado field restricted to the values abierta or cerrada.
3. THE Vacante model SHALL include a missCount field used to track consecutive OK-classified scans
   in which the Vacante was not found.
4. THE Vacante model SHALL include an origen field restricted to the values board_api, json_ld,
   html_llm, or manual.
5. THE Vacante model SHALL include firstSeenAt and lastSeenAt timestamp fields.
6. THE Empresa model SHALL include an ultimoOrigenExitoso field restricted to the values board_api,
   json_ld, or html_llm, recording which Cascada_Descubrimiento method produced the Empresa's most
   recent OK or EMPTY_LEGITIMO scan result. THE Empresa model SHALL leave ultimoOrigenExitoso absent
   for any Empresa that has not yet completed an OK or EMPTY_LEGITIMO scan.
7. THE ScanJob model SHALL include a status field restricted to the values RUNNING, DONE, PARCIAL,
   or FAILED.
8. THE ScanJob model SHALL include empresasTotal, empresasCompletadas, empresasOmitidas, and
   empresasFallidas fields, where empresasCompletadas and empresasFallidas are each represented as a
   string set updated via ADD operations, and empresasOmitidas is represented as a collection of
   companyId values populated once when the ScanJob is created.
9. THE shared domain models SHALL include a new UsuarioVacante model keyed by userId and vacancyId,
   with score, scoreDetalle, scoreProfileVersion, estado, and updatedAt fields, where score is
   constrained to a numeric range of 0 to 100 inclusive.
10. THE shared domain models SHALL include a new ScoringResult model with score, veredicto,
    coincidencias, faltantes, and resumen fields, where score is constrained to a numeric range of 0
    to 100 inclusive, veredicto is restricted to the values excelente, buen_encaje, parcial, or bajo,
    and coincidencias and faltantes are each represented as a list of strings.

### Requirement 2: Orden y criterio de parada de la cascada de descubrimiento

**User Story:** Como Scan_Worker, quiero una cadena de métodos de extracción con prioridad fija, para intentar siempre el método más económico antes de gastar tokens de Bedrock.

#### Acceptance Criteria

1. WHEN Scan_Worker begins processing an Empresa whose plataforma is greenhouse or lever, THE
   Cascada_Descubrimiento SHALL attempt the Board_API_Client method first.
2. WHEN the Board_API_Client method returns one or more vacancies, THE Cascada_Descubrimiento SHALL
   stop and SHALL treat the Board_API_Client result as the outcome of the scan.
3. WHEN the Board_API_Client method returns zero vacancies or raises an error, THE
   Cascada_Descubrimiento SHALL attempt the JsonLd_Extractor method next.
4. WHEN Scan_Worker begins processing an Empresa whose plataforma is html or jsonld, THE
   Cascada_Descubrimiento SHALL attempt the JsonLd_Extractor method first.
5. WHEN the JsonLd_Extractor method returns one or more vacancies, THE Cascada_Descubrimiento SHALL
   stop and SHALL treat the JsonLd_Extractor result as the outcome of the scan.
6. WHEN the JsonLd_Extractor method returns zero vacancies or raises an error, THE
   Cascada_Descubrimiento SHALL attempt the Html_Llm_Extractor method next.
7. THE Cascada_Descubrimiento SHALL treat the Html_Llm_Extractor result as the final outcome of the
   scan, regardless of the number of vacancies returned or any error raised.
8. THE Scan_Worker SHALL map each Cascada_Descubrimiento method to an origen value as follows: the
   Board_API_Client method maps to board_api, the JsonLd_Extractor method maps to json_ld, and the
   Html_Llm_Extractor method maps to html_llm.
9. WHEN a scan of an Empresa produces a result via a given Cascada_Descubrimiento method, THE
   Scan_Worker SHALL record the origen value mapped from that method under Requirement 2.8 as the
   value of origen for every Vacante upserted from that scan.
10. WHEN the classification of a scan is OK or EMPTY_LEGITIMO, THE Scan_Worker SHALL update the
    Empresa's ultimoOrigenExitoso field with the origen value mapped, under Requirement 2.8, from the
    Cascada_Descubrimiento method that produced that scan's result.
11. WHEN Scan_Worker begins processing an Empresa whose plataforma is manual, THE Cascada_Descubrimiento SHALL skip the Board_API_Client, JsonLd_Extractor, and Html_Llm_Extractor methods entirely and SHALL treat that Empresa as not eligible for any extraction attempt within that scan invocation.
12. WHEN an Empresa's plataforma equals manual, THE Empresa record SHALL have its boardToken and careersUrl fields undefined or unused for extraction purposes, since no board API or web fetch applies to manually-posted companies.
13. WHEN Scan_Worker classifies a scan result for an Empresa with plataforma = manual (where no extraction methods were attempted), THE Scan_Worker SHALL classify the result as EMPTY_LEGITIMO, since the lack of extraction is intentional, not a failure.

### Requirement 3: Extracción vía Board API (Greenhouse/Lever)

**User Story:** Como Scan_Worker, quiero consultar la API JSON pública de Greenhouse o Lever, para
obtener vacantes sin gastar tokens de Bedrock cuando la empresa publica en uno de esos boards.

#### Acceptance Criteria

1. WHEN the Board_API_Client method runs for an Empresa with plataforma greenhouse, THE
   Board_API_Client SHALL query the public Greenhouse job board JSON endpoint using the Empresa's
   boardToken.
2. WHEN the Board_API_Client method runs for an Empresa with plataforma lever, THE Board_API_Client
   SHALL query the public Lever job board JSON endpoint using the Empresa's boardToken.
3. IF the Board_API_Client request times out or receives an HTTP status code in the 4xx or 5xx
   range, THEN THE Board_API_Client SHALL raise an error that the Cascada_Descubrimiento classifies
   as a failed attempt for that method.
4. IF the Board_API_Client receives a response body it cannot parse as valid JSON, THEN THE
   Board_API_Client SHALL raise an error that the Cascada_Descubrimiento classifies as a failed
   attempt for that method.
5. WHEN the Board_API_Client parses a valid response, THE Board_API_Client SHALL map each job entry
   to a Vacante with modalidad set to sin_dato whenever the source response does not specify a work
   modality.
6. IF a job entry in an otherwise valid Board_API_Client response has no URL, THEN THE
   Board_API_Client SHALL exclude that entry from the mapped Vacantes without raising an error and
   without affecting the mapping of any other entry in that response.

### Requirement 4: Extracción vía JSON-LD

**User Story:** Como Scan_Worker, quiero extraer vacantes desde el bloque `JobPosting` de
JSON-LD de la página de carreras, para obtener datos estructurados sin invocar un LLM.

#### Acceptance Criteria

1. WHEN the JsonLd_Extractor method runs for an Empresa, THE JsonLd_Extractor SHALL fetch the
   Empresa's careersUrl and SHALL use the existing extract_json_ld helper to locate
   application/ld+json JobPosting blocks, whether each block appears as a standalone JSON object,
   as an element of a JSON array, or nested inside an `@graph` array.
2. IF the fetch of careersUrl does not complete within 10 seconds, or returns a connection error, or
   returns an HTTP status code in the 4xx or 5xx range, THEN THE JsonLd_Extractor SHALL raise an
   error that the Cascada_Descubrimiento classifies as a failed attempt for that method.
3. IF no application/ld+json JobPosting block is found in the fetched HTML, THEN THE JsonLd_Extractor
   SHALL return zero vacancies.
4. WHEN one or more JobPosting blocks are found, THE JsonLd_Extractor SHALL map each block to a
   Vacante with modalidad set to sin_dato whenever the JobPosting does not specify a work modality.
5. IF a JobPosting block does not contain a URL or does not contain a title, THEN THE
   JsonLd_Extractor SHALL exclude that block from the mapped Vacante output without raising an
   error.

### Requirement 5: Extracción vía HTML limpio + LLM

**User Story:** Como Scan_Worker, quiero usar un modelo pequeño de Bedrock sobre HTML limpio como
último recurso, para cubrir empresas sin board API ni JSON-LD.

#### Acceptance Criteria

1. WHEN the Html_Llm_Extractor method runs for an Empresa, THE Html_Llm_Extractor SHALL fetch the
   Empresa's careersUrl, SHALL clean the fetched HTML using the existing html_to_clean_text helper,
   and SHALL submit the cleaned text to Bedrock_Client using the model configured in
   BEDROCK_MODEL_SMALL.
2. IF the fetch of careersUrl times out or returns an HTTP status code in the 4xx or 5xx range, THEN
   THE Html_Llm_Extractor SHALL raise an error that the Cascada_Descubrimiento classifies as a
   failed attempt for that method.
3. THE Html_Llm_Extractor SHALL validate the Bedrock_Client response against a Pydantic model before
   using it as extraction output.
4. IF the Bedrock_Client response fails Pydantic validation, THEN THE Html_Llm_Extractor SHALL retry
   exactly once with the validation error injected into the prompt.
5. IF the retried Bedrock_Client response also fails Pydantic validation, THEN THE Html_Llm_Extractor
   SHALL raise an error that the Cascada_Descubrimiento classifies as a failed attempt for that
   method.
6. WHEN the Bedrock_Client response passes Pydantic validation, THE Html_Llm_Extractor SHALL map
   each extracted job entry to a Vacante with modalidad set to sin_dato whenever the extracted data
   does not specify a work modality.

### Requirement 6: Clasificación del resultado de un escaneo por empresa

**User Story:** Como sistema, necesito una clasificación única y sin ambigüedad del resultado de
escanear una empresa, para que los cierres de vacantes y los contadores de fallo nunca se apliquen
incorrectamente.

#### Acceptance Criteria

1. THE Scan_Worker SHALL treat a response from the Cascada_Descubrimiento as valid when that
   response completes without a timeout, without an HTTP 4xx/5xx error, without an invalid-JSON or
   validation error, and without an unhandled exception, regardless of the number of vacancies
   contained in that response.
2. IF the Cascada_Descubrimiento returns a valid response with more than zero vacancies, THEN THE
   Scan_Worker SHALL classify the scan as OK.
3. IF every method attempted by the Cascada_Descubrimiento for an Empresa raises a timeout, an HTTP
   4xx/5xx error, an invalid-JSON/validation error, or an unhandled exception, THEN THE Scan_Worker
   SHALL classify the scan as FAILED.
4. IF the Cascada_Descubrimiento returns a valid response with zero vacancies while the Empresa's
   stored lastVacancyCount is greater than zero, THEN THE Scan_Worker SHALL classify the scan as
   EMPTY_SOSPECHOSO.
5. IF the Cascada_Descubrimiento returns a valid response with zero vacancies while the Empresa's
   stored lastVacancyCount equals zero, THEN THE Scan_Worker SHALL classify the scan as
   EMPTY_LEGITIMO.
6. THE Scan_Worker SHALL classify every completed scan attempt of an Empresa as exactly one of OK,
   FAILED, EMPTY_SOSPECHOSO, or EMPTY_LEGITIMO, and SHALL NOT assign more than one of these
   classifications to the same scan attempt.
7. WHEN a scan is classified as FAILED or EMPTY_SOSPECHOSO, THE Scan_Worker SHALL leave every
   existing Vacante of that Empresa unchanged and SHALL increment the Empresa's consecutiveFailures
   field by 1.
8. WHEN a scan is classified as EMPTY_SOSPECHOSO, THE Scan_Worker SHALL leave the Empresa's
   lastVacancyCount field unchanged.
9. WHEN a scan is classified as OK or EMPTY_LEGITIMO, THE Scan_Worker SHALL set the Empresa's
   consecutiveFailures field to 0 and SHALL set lastVacancyCount to the number of vacancies returned
   by that scan.
10. WHEN a scan is classified as OK, THE Scan_Worker SHALL evaluate vacancy closures as specified in
    Requirement 7.

**Tabla de clasificación (referencia completa, cuatro casos):**

| Clasificación | Condición exacta | Acción sobre Vacantes existentes | Acción sobre contadores de Empresa |
|---|---|---|---|
| `OK` | Respuesta válida de la Cascada_Descubrimiento con N > 0 vacantes | Se evalúan cierres normalmente (Requirement 7: missCount, estado) | `consecutiveFailures = 0`, `lastVacancyCount = N` |
| `FAILED` | Timeout, HTTP 4xx/5xx, JSON inválido o excepción no controlada en el método final intentado de la Cascada_Descubrimiento | Ninguna Vacante existente se modifica | `consecutiveFailures += 1`; `lastVacancyCount` no se modifica |
| `EMPTY_SOSPECHOSO` | Respuesta válida con 0 vacantes **y** `Empresa.lastVacancyCount > 0` | Ninguna Vacante existente se modifica | `consecutiveFailures += 1`; `lastVacancyCount` no se modifica |
| `EMPTY_LEGITIMO` | Respuesta válida con 0 vacantes **y** `Empresa.lastVacancyCount == 0` | Ninguna Vacante existente se modifica (no hay vacantes que evaluar) | `consecutiveFailures = 0`, `lastVacancyCount = 0` |

### Requirement 7: Cierre de vacantes con margen (missCount)

**User Story:** Como usuario suscrito a una empresa, quiero que una vacante solo se marque como
cerrada tras confirmarlo en más de un escaneo válido, para no perder vacantes por un fallo pasajero
de la fuente.

#### Acceptance Criteria

1. WHEN a scan of an Empresa is classified as OK, THE Scan_Worker SHALL increment missCount by 1 for
   every existing Vacante of that Empresa with estado abierta whose vacancyId does not match the
   vacancyId of any vacancy in that scan's result.
2. WHEN a scan of an Empresa is classified as OK, THE Scan_Worker SHALL reset missCount to 0 for
   every existing Vacante of that Empresa whose vacancyId matches the vacancyId of a vacancy in that
   scan's result.
3. WHEN a scan of an Empresa is classified as OK, THE Scan_Worker SHALL set estado to abierta for
   every existing Vacante of that Empresa whose estado is cerrada and whose vacancyId matches the
   vacancyId of a vacancy in that scan's result.
4. IF a Vacante's missCount reaches or exceeds 2 immediately after an OK-classified scan, AND that
   Vacante's origen is not manual, THEN THE Scan_Worker SHALL set that Vacante's estado to cerrada.
5. WHILE a Vacante's origen equals manual, THE Scan_Worker SHALL keep that Vacante's estado
   unaffected by missCount evaluation, regardless of the missCount value reached.
6. WHEN Scan_Worker upserts a vacancy from a scan's result whose vacancyId does not match any
   existing Vacante record of that Empresa, THE Scan_Worker SHALL create that Vacante with vacancyId
   set to the SHA-256 hash of the vacancy's normalized URL, missCount to 0, estado to abierta, and
   firstSeenAt to the current timestamp.
7. WHEN Scan_Worker upserts a vacancy from a scan's result whose vacancyId matches an existing
   Vacante record of that Empresa, THE Scan_Worker SHALL update that Vacante's lastSeenAt to the
   current timestamp without modifying vacancyId or firstSeenAt.

Nota: el cierre (missCount >= 2 → estado cerrada, criterio 4) y la reapertura (criterio 3) SOLO
pueden ocurrir tras un escaneo clasificado OK, nunca tras FAILED o EMPTY_SOSPECHOSO.

### Requirement 8: Ventana de frescura por tipo de fuente

**User Story:** Como sistema, quiero re-escanear una empresa solo cuando ha pasado suficiente tiempo
desde su último escaneo, con una ventana distinta según el costo del método usado, para no gastar
tokens de Bedrock innecesariamente ni saturar boards públicos.

#### Acceptance Criteria

1. IF an Empresa's ultimoOrigenExitoso field equals board_api or json_ld, THEN THE Orquestador SHALL
   treat that Empresa as eligible for re-scan when the elapsed time between the current ScanJob's
   startedAt and that Empresa's lastScannedAt is greater than or equal to 3600 seconds.
2. IF an Empresa's ultimoOrigenExitoso field equals html_llm, THEN THE Orquestador SHALL treat that
   Empresa as eligible for re-scan when the elapsed time between the current ScanJob's startedAt and
   that Empresa's lastScannedAt is greater than or equal to 43200 seconds.
3. IF an Empresa has no recorded lastScannedAt value, THEN THE Orquestador SHALL treat that Empresa
   as eligible for re-scan.
4. IF an Empresa has a recorded lastScannedAt value but no recorded ultimoOrigenExitoso value, THEN
   THE Orquestador SHALL treat that Empresa as eligible for re-scan only when the elapsed time
   between the current ScanJob's startedAt and that Empresa's lastScannedAt is greater than or equal
   to 43200 seconds.
5. IF an Empresa is not eligible for re-scan under Requirement 8.1, 8.2, or 8.4, THEN THE
   Orquestador SHALL add that Empresa's companyId to the ScanJob's empresasOmitidas field instead of
   publishing a message to SQS_Scan for it.
6. THE Orquestador SHALL report every Empresa placed in empresasOmitidas separately from
   empresasFallidas in the ScanJob record.

### Requirement 9: POST /scans — autenticación, creación y fan-out del ScanJob

**User Story:** Como usuario, quiero disparar un escaneo de mis empresas suscritas con una sola
llamada, para no esperar el resultado de forma síncrona.

#### Acceptance Criteria

1. WHEN Scans_API receives a POST /scans request, THE Scans_API SHALL extract userId from
   event.requestContext.authorizer.claims.sub and SHALL ignore any userId supplied in the request
   body or query parameters.
2. WHEN Scans_API receives a POST /scans request, THE Orquestador SHALL resolve the set of Empresas
   linked to the requesting user's active Suscripciones (activa = true).
3. WHEN the scheduled global trigger invokes Orquestador, THE Orquestador SHALL resolve the set of
   Empresas linked to every user's active Suscripciones instead of a single user's.
4. WHEN the Orquestador resolves a set of Empresas in which more than one active Suscripcion
   references the same companyId, THE Orquestador SHALL deduplicate that set so each distinct
   companyId is counted, published to SQS_Scan, and reflected in empresasTotal, empresasCompletadas,
   empresasOmitidas, and empresasFallidas at most once per ScanJob.
5. WHEN Orquestador is invoked either by a POST /scans request or by the scheduled global trigger,
   THE Orquestador SHALL create one ScanJob record for that invocation with status RUNNING,
   startedAt set to the current timestamp, and empresasTotal set to the deduplicated count of
   resolved Empresas before applying the Ventana_Frescura.
6. WHEN the Orquestador creates a ScanJob in response to a POST /scans request, THE Orquestador
   SHALL set that ScanJob's userId field to the requesting user's userId extracted per
   Requirement 9.1.
7. WHEN the Orquestador creates a ScanJob in response to the scheduled global trigger, THE
   Orquestador SHALL leave that ScanJob's userId field unset, since that ScanJob spans every user's
   active Suscripciones rather than a single user's.
8. WHEN the Orquestador finishes applying the Ventana_Frescura, THE Orquestador SHALL publish
   exactly one message to SQS_Scan for each deduplicated resolved Empresa not placed in
   empresasOmitidas.
9. IF the Orquestador's attempt to publish a message to SQS_Scan for a given Empresa raises an
   error while at least one other resolved Empresa's publish attempt succeeds, THEN THE Orquestador
   SHALL add that Empresa's companyId to the ScanJob's empresasFallidas field instead of leaving that
   Empresa unrepresented in the job's progress, and SHALL continue attempting to publish messages
   for the remaining resolved Empresas.
10. WHEN Scans_API receives a POST /scans request, THE Scans_API SHALL respond with the jobId field
    of the created ScanJob — a unique identifier distinct from userId, assigned by the Orquestador
    and usable to poll GET /scans/{jobId} — without waiting for any Empresa to finish scanning.

### Requirement 10: Caso sin empresas para escanear (resultado exitoso)

**User Story:** Como usuario sin empresas activas o con todas dentro de su ventana de frescura,
quiero que el escaneo se reporte como exitoso, para no confundir "nada que hacer" con un error.

#### Acceptance Criteria

1. IF the Orquestador resolves zero Empresas for a scan invocation, THEN THE Orquestador SHALL
   create the ScanJob per Requirement 9.5 with empresasTotal set to 0, and SHALL transition that
   ScanJob's status from RUNNING to DONE within the same invocation, before publishing any message
   to SQS_Scan.
2. IF the Orquestador resolves one or more Empresas for a scan invocation and every resolved Empresa
   is placed in empresasOmitidas by the Ventana_Frescura, THEN THE Orquestador SHALL transition that
   ScanJob's status from RUNNING to DONE within the same invocation, without publishing any message
   to SQS_Scan.
3. THE Orquestador SHALL treat both transitions described in 10.1 and 10.2 as successful outcomes,
   represented exclusively by the DONE status.
4. IF the Orquestador resolves zero Empresas for a scan invocation, or every resolved Empresa is
   placed in empresasOmitidas, THEN THE Orquestador SHALL NOT set that ScanJob's status to FAILED,
   regardless of zero messages having been published to SQS_Scan.

### Requirement 11: Fallo total o parcial de fan-out

**User Story:** Como sistema, quiero distinguir un job que nunca pudo arrancar de uno que arrancó de
forma incompleta y de uno que sigue en curso, para que el frontend no quede esperando un progreso
que nunca llegará y para que ninguna Empresa cuyo mensaje de fan-out falló quede sin registrar.

#### Acceptance Criteria

1. WHEN the Orquestador publishes messages to SQS_Scan for the Empresas resolved for a ScanJob, THE
   Orquestador SHALL attempt to publish each Empresa's message to SQS_Scan exactly once, without
   retrying a publish attempt that raised an error for that Empresa.
2. IF the Orquestador resolves one or more Empresas pending scan and every attempt to publish a
   message to SQS_Scan for those Empresas raises an error, THEN THE Orquestador SHALL set that
   ScanJob's status to FAILED and SHALL add every one of those Empresas' companyId to the ScanJob's
   empresasFallidas field.
3. IF the Orquestador resolves two or more Empresas pending scan and the attempt to publish a
   message to SQS_Scan raises an error for at least one Empresa while succeeding for at least one
   other Empresa, THEN THE Orquestador SHALL set that ScanJob's status to PARCIAL and SHALL add
   every Empresa whose publish attempt raised an error to the ScanJob's empresasFallidas field.
4. THE Orquestador SHALL treat empresasOmitidas and empresasFallidas as mutually exclusive fields
   for a given ScanJob, so that an Empresa excluded under Requirement 8.5 for not meeting the
   Ventana_Frescura is never also added to empresasFallidas, and an Empresa whose SQS_Scan publish
   attempt raised an error under this Requirement is never also added to empresasOmitidas.

### Requirement 12: Scan-worker — procesamiento de un mensaje SQS por empresa

**User Story:** Como Scan_Worker, quiero procesar una empresa por mensaje SQS y reportar el progreso
del job de forma segura frente a reintentos, para mantener consistente el estado del ScanJob.

#### Acceptance Criteria

1. WHEN Scan_Worker receives a message from SQS_Scan whose body contains both a jobId and a
   companyId, THE Scan_Worker SHALL process exactly one Empresa, identified by that companyId, per
   message.
2. WHEN Scan_Worker finishes processing an Empresa, regardless of the scan's classification, THE
   Scan_Worker SHALL add that Empresa's companyId to the ScanJob's empresasCompletadas string set
   using an ADD operation.
3. WHEN Scan_Worker classifies a scan as FAILED or EMPTY_SOSPECHOSO, THE Scan_Worker SHALL also add
   that Empresa's companyId to the ScanJob's empresasFallidas field, in addition to the ADD described
   in 12.2.
4. WHEN Scan_Worker classifies a scan as OK, THE Scan_Worker SHALL enqueue one SQS_Scoring message
   for each (userId, vacancyId) pair such that vacancyId identifies a Vacante that was created for
   the first time during that scan, and userId identifies a user holding a Suscripcion to that
   Empresa with activa=true.
5. IF Scan_Worker fails to enqueue an SQS_Scoring message for any (userId, vacancyId) pair required
   by criterion 12.4, THEN THE Scan_Worker SHALL abort processing that Empresa without performing
   the ADD operation on empresasCompletadas or empresasFallidas described in 12.2 and 12.3, so that
   the redelivered SQS_Scan message can retry the SQS_Scoring enqueue.

### Requirement 13: Idempotencia ante reprocesamiento de mensajes SQS

**User Story:** Como sistema que usa colas con entrega al menos una vez, quiero que reprocesar el
mismo mensaje nunca duplique datos ni cambie el resultado final, para tolerar reintentos por
vencimiento de visibility timeout o redelivery sin efectos secundarios.

#### Acceptance Criteria

1. WHEN Scan_Worker upserts a Vacante record, whether while processing a first delivery or a
   redelivered SQS_Scan message for the same Empresa, THE Scan_Worker SHALL use vacancyId as the
   sole idempotency key for that upsert, so that redelivery of an SQS_Scan message never creates a
   second Vacante record for the same normalized URL.
2. WHEN Scan_Worker finishes processing an SQS_Scan message for an Empresa, THE Scan_Worker SHALL
   add that Empresa's companyId to the ScanJob's empresasCompletadas string set using a String Set
   ADD operation on every processing attempt, including redelivered attempts, such that
   empresasCompletadas SHALL contain that companyId exactly once regardless of how many ADD
   operations are performed for it.
3. WHEN Scan_Worker adds an Empresa's companyId to the ScanJob's empresasFallidas field under the
   conditions of Requirement 12.3, THE Scan_Worker SHALL perform that addition so that
   empresasFallidas contains that companyId exactly once, regardless of how many times an SQS_Scan
   message for that Empresa is delivered and classified as FAILED or EMPTY_SOSPECHOSO.
4. WHEN Scan_Worker processes a redelivered SQS_Scan message for an Empresa whose scan was already
   classified as OK by an earlier delivery of that same message, THE Scan_Worker SHALL apply the
   missCount increment and reset rules of Requirement 7 using each Vacante's missCount and estado as
   currently stored at the time of that redelivered attempt, so that a redelivered message never
   increments a Vacante's missCount by more than 1 for that scan nor closes a Vacante that a single
   delivery of that scan would not have closed.
5. WHEN Scan_Worker enqueues SQS_Scoring messages after classifying a scan as OK, THE Scan_Worker
   SHALL enqueue one SQS_Scoring message per new-or-reopened Vacante and active-Suscripcion user
   pair on every delivery of the SQS_Scan message that produced that classification, including
   redelivered deliveries, without checking whether an earlier delivery already enqueued an
   SQS_Scoring message for the same (userId, vacancyId) pair, deferring deduplication of those
   messages entirely to Scoring_Worker.
6. WHEN Scoring_Worker receives an SQS_Scoring message for a (userId, vacancyId) pair for which a
   stored UsuarioVacante record exists with scoreProfileVersion equal to the user's current
   profileVersion, THE Scoring_Worker SHALL skip the Bedrock_Client call and SHALL leave the stored
   score, scoreDetalle, and scoreProfileVersion unchanged.
7. WHEN Scoring_Worker receives an SQS_Scoring message for a (userId, vacancyId) pair for which no
   UsuarioVacante record yet exists, THE Scoring_Worker SHALL invoke Bedrock_Client to compute the
   score instead of skipping, regardless of how many prior SQS_Scoring messages for that same pair
   have been delivered without yet producing a stored record.
8. WHILE a UsuarioVacante record for a (userId, vacancyId) pair has scoreProfileVersion equal to the
   user's current profileVersion, WHEN Scoring_Worker receives any subsequent redelivered
   SQS_Scoring message for that same pair, THE Scoring_Worker SHALL leave that record's score,
   scoreDetalle, and scoreProfileVersion fields unchanged, regardless of how many such redelivered
   messages arrive, until the user's profileVersion changes.

### Requirement 14: Detección de jobs zombis

**User Story:** Como usuario haciendo polling de un escaneo, quiero ver que el job avanzó a un
estado final aunque algún worker nunca haya reportado su empresa, para no quedar esperando un
progreso que se congeló.

#### Acceptance Criteria

1. WHEN Scans_API receives a GET /scans/{jobId} request for a ScanJob whose status is RUNNING and
   at least 600 seconds have elapsed since startedAt, THE Scans_API SHALL update that ScanJob's
   status to PARCIAL, SHALL persist that status change to the ScanJob record, and SHALL include in
   the response body the list of Empresas not yet present in empresasCompletadas nor
   empresasOmitidas.
2. WHEN a ScanJob's status has been persisted as PARCIAL, THE Scans_API SHALL continue to allow
   late-arriving Scan_Worker updates to add companyIds to empresasCompletadas or empresasFallidas
   after that persistence.
3. IF a ScanJob's status has been persisted as PARCIAL, THEN THE Scans_API SHALL never change that
   ScanJob's status to DONE, regardless of any later Scan_Worker update that completes
   empresasCompletadas and empresasOmitidas for every resolved Empresa of that ScanJob.

### Requirement 15: GET /scans/{jobId} — autenticación, autorización y contrato de polling

**User Story:** Como usuario, quiero consultar el progreso de mi escaneo con un identificador de
job, para saber cuándo terminó y con qué resultado.

#### Acceptance Criteria

1. WHEN Scans_API receives a GET /scans/{jobId} request, THE Scans_API SHALL extract userId from
   event.requestContext.authorizer.claims.sub and SHALL ignore any userId supplied in query
   parameters.
2. IF the requested jobId does not correspond to an existing ScanJob, THEN THE Scans_API SHALL
   respond with HTTP 404.
3. IF the requested ScanJob's userId field is set and differs from the requesting user's userId,
   THEN THE Scans_API SHALL respond with HTTP 404 instead of returning that ScanJob's data.
4. IF the requested ScanJob's userId field is not set, THEN THE Scans_API SHALL treat every
   authenticated caller as authorized to view that ScanJob's data.
5. WHEN Scans_API responds to a GET /scans/{jobId} request for an authorized caller, THE Scans_API
   SHALL include in the response body: the status value, the empresasTotal value, the integer
   count of companyIds present in empresasCompletadas, the integer count of companyIds present in
   empresasOmitidas, the integer count of companyIds present in empresasFallidas, and the startedAt
   timestamp.
6. WHEN Scans_API responds to a GET /scans/{jobId} request for an authorized caller whose ScanJob's
   status is PARCIAL, THE Scans_API SHALL additionally include in the response body the list of
   companyIds not present in empresasCompletadas nor in empresasOmitidas, consistent with
   Requirement 14.1.
7. WHEN a ScanJob's reported status is DONE, PARCIAL, or FAILED, THE Scans_API SHALL include a
   boolean value in the response body, distinct from the status value, set to true to indicate to
   the caller that polling can stop.
8. WHEN a ScanJob's reported status is RUNNING, THE Scans_API SHALL include a boolean value in the
   response body, distinct from the status value, set to false to indicate to the caller that
   polling should continue.

### Requirement 16: Prefiltro de cargos previo al scoring

**User Story:** Como Scoring_Worker, quiero descartar vacantes claramente ajenas a los cargos
activos del usuario antes de invocar Bedrock, para no gastar tokens en pares irrelevantes.

#### Acceptance Criteria

1. WHEN Scoring_Worker receives a message from SQS_Scoring, THE Scoring_Worker SHALL apply the
   Prefiltro_Cargos to the Vacante's titulo against the user's cargosActivos before invoking
   Bedrock_Client.
2. THE Prefiltro_Cargos SHALL derive significant tokens from the Vacante's titulo and from each
   cargo activo by converting to lowercase, removing diacritics, splitting the text into tokens on
   whitespace and punctuation, and discarding any token that appears in a defined stopword list,
   using only the remaining tokens for the comparison.
3. THE Prefiltro_Cargos SHALL read its minimum required significant token overlap from an
   environment variable rather than from a hardcoded value.
4. IF that environment variable is unset, empty, or does not hold a positive integer, THEN THE
   Prefiltro_Cargos SHALL use 1 as the minimum required significant token overlap.
5. IF the user's cargosActivos is empty, THEN THE Scoring_Worker SHALL bypass the Prefiltro_Cargos
   and SHALL proceed to invoke Bedrock_Client for scoring, since no active cargo exists against
   which to measure relevance.
6. IF the Prefiltro_Cargos finds fewer significant tokens in common between the Vacante's titulo and
   every cargo activo than the configured minimum, THEN THE Scoring_Worker SHALL skip the
   Bedrock_Client scoring call for that (userId, Vacante) pair and SHALL set the estado field of the
   corresponding UsuarioVacante record to a value that indicates the pair was filtered out without
   being scored, distinct from any estado value used for a completed scoring result.
7. WHEN the Prefiltro_Cargos finds at least the configured minimum number of significant tokens in
   common with at least one cargo activo, THE Scoring_Worker SHALL proceed to invoke Bedrock_Client
   for scoring.

### Requirement 17: Cálculo y persistencia del score

**User Story:** Como usuario, quiero ver un score de match con explicación para cada vacante
relevante, calculado una sola vez, para decidir a qué vacantes aplicar sin recalcular en cada
consulta.

#### Acceptance Criteria

1. WHEN Bedrock_Client returns a response for a scoring invocation of a (userId, Vacante) pair,
   THE Scoring_Worker SHALL validate that response against the ScoringResult Pydantic model before
   persisting it.
2. IF the Bedrock_Client response fails ScoringResult validation, THEN THE Scoring_Worker SHALL
   retry exactly once with the validation error injected into the prompt.
3. IF the retried Bedrock_Client response also fails ScoringResult validation, THEN THE
   Scoring_Worker SHALL leave the existing UsuarioVacante record (if any) unchanged, neither
   creating a new record nor modifying score, veredicto, coincidencias, faltantes, resumen, or
   scoreProfileVersion for that (userId, vacancyId) pair.
4. IF the retried Bedrock_Client response also fails ScoringResult validation, THEN THE
   Scoring_Worker SHALL log the failure with the (userId, vacancyId) pair identifiers and the
   validation error, and SHALL NOT log the CV text, profile content, or the raw Bedrock_Client
   response body.
5. WHEN the Bedrock_Client response passes ScoringResult validation, THE Scoring_Worker SHALL
   persist score, veredicto, coincidencias, faltantes, resumen, and updatedAt into the
   UsuarioVacante record for that (userId, vacancyId) pair, together with scoreProfileVersion set
   to the user's current profileVersion.
6. THE Scoring_Worker SHALL be the only component that invokes Bedrock_Client for scoring, and SHALL
   perform that invocation only when triggered by an SQS_Scoring message, never synchronously within
   an HTTP request.

### Requirement 18: Rescoring híbrido — interfaz de detección de desfase

**User Story:** Como usuario que actualiza su perfil o sus cargos activos, quiero que mis scores desfasados se recalculen en segundo plano la próxima vez que se consulten, para ver información actualizada sin pagar el costo de recalcular todo de inmediato.

#### Acceptance Criteria

1. THE Rescoring_Detector SHALL expose a pure staleness-detection function that, given a UsuarioVacante record's scoreProfileVersion and the user's current Perfil.profileVersion, returns true when the two values are not equal and returns false when they are equal.
2. THE staleness-detection function defined in Criterion 1 SHALL NOT perform any network I/O, SHALL NOT publish any SQS_Scoring message, and SHALL NOT mutate the UsuarioVacante record or any other stored data.
3. WHERE a consumer outside this spec's scope (e.g., the vacancy listing endpoint) determines via the staleness-detection function that a UsuarioVacante record is stale, THE Rescoring_Detector SHALL provide a separate enqueue function that publishes exactly one SQS_Scoring message for that (userId, vacancyId) pair without blocking the caller's response.
4. IF the enqueue function defined in Criterion 3 fails to publish the SQS_Scoring message, THEN THE Rescoring_Detector SHALL return an error indication to the calling consumer without raising an unhandled exception, and SHALL NOT retry the publish within the same invocation.
5. THE Rescoring_Detector SHALL limit its own action, regardless of whether the enqueue in Criterion 3 succeeds or fails as described in Criterion 4, to returning the existing stored score to the calling consumer unchanged, and SHALL NOT recompute or alter the stored score synchronously.
6. THE Rescoring_Detector SHALL be implemented as two importable functions within `backend/shared/`: the pure staleness-detection function from Criterion 1 and the enqueue function from Criterion 3, so this spec's workers and consumers defined in other specs reuse the same staleness rule and enqueue logic instead of duplicating them.

### Requirement 19: Concurrencia reservada de los workers

**User Story:** Como sistema que depende de una cuota compartida de Bedrock, quiero limitar cuántas
invocaciones concurrentes de cada worker pueden ejecutarse, para no agotar la cuota de tokens por
minuto en cuentas nuevas.

#### Acceptance Criteria

1. THE Scan_Worker Lambda function SHALL be deployed with its reserved concurrency setting equal to
   exactly 5.
2. THE Scoring_Worker Lambda function SHALL be deployed with its reserved concurrency setting equal
   to exactly 3.

### Requirement 20: Visibility timeout de las colas SQS

**User Story:** Como sistema, quiero que el visibility timeout de cada cola sea proporcional al
timeout de su Lambda consumidora, para evitar que un mensaje en procesamiento se re-entregue antes
de que el worker termine.

#### Acceptance Criteria

1. THE visibility timeout configured for SQS_Scan SHALL be set, in seconds, to exactly 6 times the
   value, in seconds, of the timeout configuration setting of the Scan_Worker Lambda function.
2. THE visibility timeout configured for SQS_Scoring SHALL be set, in seconds, to exactly 6 times
   the value, in seconds, of the timeout configuration setting of the Scoring_Worker Lambda
   function.
3. THE SQS_Scan queue SHALL be configured with a MaxReceiveCount attribute set to exactly 3 in its associated dead-letter queue (DLQ), so that a message re-delivered 3 times and still failing is sent to the DLQ instead of continuing to cycle.
4. THE SQS_Scoring queue SHALL be configured with a MaxReceiveCount attribute set to exactly 3 in its associated dead-letter queue (DLQ), for the same purpose as SQS_Scan.

### Requirement 21: Logging estructurado sin contenido sensible

**User Story:** Como responsable de operar el sistema, quiero logs estructurados en JSON que
permitan diagnosticar fallos sin exponer contenido sensible del usuario, para cumplir con la
política de logging del proyecto.

#### Acceptance Criteria

1. WHEN Scan_Worker or Scoring_Worker completes processing of a message that includes a
   Bedrock_Client invocation, THE Scan_Worker or Scoring_Worker SHALL emit a structured JSON log
   record to stdout for that message.
2. WHEN Prefiltro_Cargos causes Scoring_Worker to skip the Bedrock_Client call for a (userId,
   Vacante) pair, THE Scoring_Worker SHALL emit a structured JSON log record to stdout for that
   pair.
3. THE Scan_Worker SHALL restrict logged Vacante fields to companyId, vacancyId, and origen,
   excluding descripcion from every log record.
4. THE Scoring_Worker SHALL restrict logged UsuarioVacante fields to userId, vacancyId, score, and
   scoreDetalle.veredicto, excluding scoreDetalle.resumen, scoreDetalle.coincidencias, and
   scoreDetalle.faltantes, and excluding any Perfil content, from every log record.
5. IF Scan_Worker or Scoring_Worker fails to process a message, THEN THE Scan_Worker or
   Scoring_Worker SHALL emit a structured JSON log record to stdout indicating the failure, subject
   to the same field restrictions as Criteria 3 and 4.
