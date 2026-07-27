# Requirements Document

## Introduction

Esta spec cubre el listado y gestión de vacantes desde la perspectiva del usuario (listado, detalle,
carga manual, marcar aplicada, generación de CV-ATS, banco de preguntas y notas) y el ciclo de
notificación por correo tras un escaneo programado. Se apoya en los modelos de dominio y contratos
ya definidos en `backend-core` y `backend-scan-y-scoring` (Empresa, Vacante, UsuarioVacante, ScanJob,
Perfiles, Suscripciones, Entradas) sin redefinirlos: esta spec únicamente añade endpoints y
comportamiento sobre esos modelos.

Fuera de alcance de esta spec: Terraform, frontend, generación de archivos `.docx`, y vista agregada
de preguntas por empresa.

## Glossary

- **Vacancy_Listing_API**: Componente (rutas dentro de la Lambda API síncrona) que atiende
  `GET /me/vacancies` y aplica el filtrado/orden en memoria sobre los resultados de `UsuarioVacante`
  consultados por `userId`.
- **Vacancy_Detail_API**: Componente que atiende `GET /me/vacancies/{companyId}/{vacancyId}`.
- **Manual_Vacancy_Service**: Componente que atiende `POST /me/vacancies/manual`.
- **Apply_Service**: Componente que atiende `POST /me/vacancies/{companyId}/{vacancyId}/apply`.
- **CV_ATS_Service**: Componente que atiende `POST /me/vacancies/{companyId}/{vacancyId}/cv`.
- **Entries_Service**: Componente que atiende `GET/POST /me/vacancies/{companyId}/{vacancyId}/entries`
  y `POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer`.
- **Notificador_Lambda**: Lambda asíncrona que se dispara al cerrar un ScanJob de escaneo programado
  y envía notificaciones por correo mediante SES.
- **EventBridge_Scheduler**: Regla de EventBridge Scheduler que dispara el escaneo programado
  invocando a Orquestador_Lambda.
- **Orquestador_Lambda**: Lambda ya definida en `backend-scan-y-scoring` que resuelve empresas a
  escanear y crea un `ScanJob`. Esta spec añade su modo de invocación programada.
- **Bedrock_Client**: Módulo compartido (`backend/shared/bedrock.py`, ya definido en `backend-core`)
  usado para invocar Amazon Bedrock; nunca hardcodea IDs de modelo.
- **JWT_Claims**: Reclamaciones del token de Cognito propagadas por el authorizer de API Gateway
  (`event.requestContext.authorizer.claims`).
- **Empresa, Vacante, UsuarioVacante, ScanJob, Perfiles, Suscripciones, Entradas**: Modelos de
  dominio ya definidos en `backend/shared/models.py` (ver `backend-core` y `backend-scan-y-scoring`).
  Esta spec no redefine sus campos.

## Requirements

### Requirement 1: Listado de Vacantes del Usuario

**User Story:** Como usuario autenticado, quiero ver la lista de mis vacantes activas o aplicadas,
para dar seguimiento a mi búsqueda de empleo.

#### Acceptance Criteria

1. WHEN un cliente invoca `GET /me/vacancies` con el parámetro `estado` cuyo valor coincide de
   forma exacta y sensible a mayúsculas/minúsculas con `activas`, THE Vacancy_Listing_API SHALL
   retornar los registros `UsuarioVacante` del `userId` extraído del JWT cuyo campo `estado` sea
   `nueva` o `vista`.
2. WHEN un cliente invoca `GET /me/vacancies` con el parámetro `estado` cuyo valor coincide de
   forma exacta y sensible a mayúsculas/minúsculas con `aplicadas`, THE Vacancy_Listing_API SHALL
   retornar los registros `UsuarioVacante` del `userId` extraído del JWT cuyo campo `estado` sea
   `aplicada`.
3. IF el parámetro `estado` está ausente, THEN THE Vacancy_Listing_API SHALL aplicar el valor
   `activas` por defecto.
4. IF el parámetro `estado` tiene un valor que no coincide de forma exacta y sensible a
   mayúsculas/minúsculas con `activas` ni con `aplicadas` (incluyendo variantes con capitalización
   distinta, espacios en blanco adicionales, o cualquier otro valor), THEN THE Vacancy_Listing_API
   SHALL retornar HTTP 400 con un mensaje de error descriptivo.
5. THE Vacancy_Listing_API SHALL consultar `UsuarioVacante` únicamente por `userId` (sin índice
   secundario) y SHALL aplicar el filtrado por `estado` y el ordenamiento dentro de la Lambda.
6. WHERE el filtro aplicado es `activas`, THE Vacancy_Listing_API SHALL ordenar los resultados por
   `score` descendente, ubicando al final los registros con `score` nulo o pendiente, y usando
   `Vacante.lastSeenAt` descendente como criterio de desempate.
7. WHERE el filtro aplicado es `aplicadas`, THE Vacancy_Listing_API SHALL ordenar los resultados por
   `UsuarioVacante.appliedAt` descendente.
8. WHEN un registro `UsuarioVacante` retornado tiene `scoreProfileVersion` distinto de
   `Perfiles.profileVersion` del usuario, o `scoreProfileVersion` nulo con `estado` igual a
   `nueva`, THE Vacancy_Listing_API SHALL encolar exactamente un mensaje de reprocesamiento
   mediante la función `enqueue_rescore` (definida en `backend-scan-y-scoring`) para ese
   `(userId, vacancyId)` y SHALL incluir en la respuesta el `score` existente junto con un indicador
   `staleFlag=true`, sin esperar el nuevo cálculo.
9. IF el encolado de reprocesamiento mediante `enqueue_rescore` falla, THEN THE Vacancy_Listing_API
   SHALL responder de todas formas con el `score` existente y `staleFlag=true`, y SHALL registrar la
   falla en el log.
10. THE Vacancy_Listing_API SHALL incluir, para cada registro retornado, los mismos campos de
    `Vacante` y el mismo resumen de `Empresa` (`nombre`, `plataforma`) que retorna Vacancy_Detail_API
    para esa vacante, y SHALL NOT incluir el campo `cvAtsTexto` de `UsuarioVacante` en la respuesta
    del listado.
11. WHEN una consulta a `GET /me/vacancies` no produce ningún registro `UsuarioVacante` que
    coincida con el `userId` y el filtro `estado` aplicado, THE Vacancy_Listing_API SHALL retornar
    HTTP 200 con una lista vacía, y SHALL NOT retornar HTTP 404 en ese caso.

### Requirement 2: Detalle de una Vacante del Usuario

**User Story:** Como usuario autenticado, quiero ver el detalle completo de una vacante puntual,
para decidir si aplicar y preparar mi candidatura.

#### Acceptance Criteria

1. WHEN un cliente invoca `GET /me/vacancies/{companyId}/{vacancyId}`, THE Vacancy_Detail_API SHALL
   retornar los datos de `Vacante`, un resumen de `Empresa` compuesto únicamente por `nombre` y
   `plataforma`, y el registro `UsuarioVacante` correspondientes a `(userId del JWT, companyId,
   vacancyId)`.
2. IF no existe un registro `UsuarioVacante` para `(userId, companyId, vacancyId)`, THEN THE
   Vacancy_Detail_API SHALL retornar HTTP 404.
3. IF no existe un registro `Vacante` para `(companyId, vacancyId)`, THEN THE Vacancy_Detail_API
   SHALL retornar HTTP 404.
4. WHEN `UsuarioVacante.cvAtsTexto` tiene contenido, THE Vacancy_Detail_API SHALL incluirlo en la
   respuesta como texto plano, y SHALL NOT incluir ninguna referencia a un archivo o a una URL de
   almacenamiento de objetos.
5. IF `UsuarioVacante.cvAtsTexto` es null o una cadena vacía, THEN THE Vacancy_Detail_API SHALL
   tratar dicho estado como válido y SHALL retornar HTTP 200 con el campo correspondiente vacío,
   sin retornar HTTP 404 ni ningún código de error.
6. WHILE `Vacante.estado` es igual a `cerrada`, THE Vacancy_Detail_API SHALL retornar el detalle de
   la vacante con la misma estructura de respuesta que una vacante abierta, incluyendo cualquier
   `cvAtsTexto` generado previamente.

### Requirement 3: Registro Manual de Vacante

**User Story:** Como usuario autenticado, quiero registrar manualmente una vacante que encontré por
fuera del escaneo automático, para darle seguimiento junto con las demás.

#### Acceptance Criteria

1. WHEN un cliente invoca `POST /me/vacancies/manual` con un texto pegado de 1 a 20000 caracteres,
   un enlace que es una URL absoluta con esquema `http` o `https`, y un nombre de empresa que, tras
   eliminar espacios en blanco al inicio y al final, tiene entre 1 y 200 caracteres, THE
   Manual_Vacancy_Service SHALL invocar a Bedrock_Client para extraer del texto pegado los campos de
   `Vacante` (`titulo`, `descripcion`, `modalidad`, `ubicacion`), validando la salida
   contra el esquema Pydantic de `Vacante`.
2. THE Manual_Vacancy_Service SHALL NOT realizar ninguna solicitud HTTP hacia el enlace recibido; el
   enlace SHALL persistirse únicamente en el campo `Vacante.url`.
3. IF el nombre de empresa recibido, tras eliminar espacios en blanco al inicio y al final y
   convertir a minúsculas, no es idéntico al nombre de ninguna `Empresa` existente en el catálogo
   sometido a la misma normalización, THEN THE Manual_Vacancy_Service SHALL crear un nuevo registro
   `Empresa` con `plataforma = manual` y `careersUrl` nulo.
4. WHEN el Manual_Vacancy_Service registra una vacante manual, THE Manual_Vacancy_Service SHALL NOT
   crear ni modificar ningún registro `Suscripcion`, independientemente de si la `Empresa` asociada
   es una recién creada según el criterio 3 o una `Empresa` ya existente en el catálogo.
5. THE Manual_Vacancy_Service SHALL calcular el `vacancyId` como el hash SHA-256 de la URL
   normalizada del enlace recibido, reutilizando la función de normalización y hash ya definida en
   `backend-scan-y-scoring`.
6. IF no existe ya un registro `Vacante` cuyo `vacancyId` sea igual al hash SHA-256 de la URL
   normalizada del enlace recibido, THEN THE Manual_Vacancy_Service SHALL crear el registro
   `Vacante` con `origen = manual` y `estado = abierta`.
7. WHEN un registro `Vacante` identificado por el `vacancyId` calculado a partir del enlace recibido
   está disponible, ya sea por haberse creado como parte de esta solicitud o por existir
   previamente, IF no existe ya un registro `UsuarioVacante` para `(userId, vacancyId)`, THEN THE
   Manual_Vacancy_Service SHALL crear un registro `UsuarioVacante` para `(userId, vacancyId)` con
   `estado = nueva`.
8. WHEN el registro `UsuarioVacante` se crea exitosamente, THE Manual_Vacancy_Service SHALL publicar
   exactamente un mensaje `ScoringMessage` en la cola SQS de scoring para `(userId, vacancyId)`.
9. IF la salida de Bedrock_Client no pasa la validación Pydantic tras un reintento, THEN THE
   Manual_Vacancy_Service SHALL retornar HTTP 400 con un mensaje de error descriptivo y SHALL NOT
   crear ningún registro de `Empresa`, `Vacante` ni `UsuarioVacante`.
10. IF el texto pegado está vacío o excede 20000 caracteres, el enlace no es una URL absoluta con
    esquema `http` o `https`, o el nombre de empresa está vacío tras eliminar espacios en blanco al
    inicio y al final o excede 200 caracteres, THEN THE Manual_Vacancy_Service SHALL retornar HTTP
    400 con un mensaje de error descriptivo y SHALL NOT invocar a Bedrock_Client ni crear ningún
    registro de `Empresa`, `Vacante` ni `UsuarioVacante`.
11. IF ya existe un registro `Vacante` cuyo `vacancyId` es igual al hash SHA-256 de la URL
    normalizada del enlace recibido, THEN THE Manual_Vacancy_Service SHALL NOT invocar a
    Bedrock_Client, SHALL NOT crear un nuevo registro `Vacante`, y SHALL reutilizar sin modificar el
    registro `Vacante` existente para continuar procesando la solicitud.
12. IF ya existe un registro `UsuarioVacante` para `(userId, vacancyId)` al momento de procesar la
    solicitud, THEN THE Manual_Vacancy_Service SHALL retornar HTTP 200 sin crear un registro
    `UsuarioVacante` duplicado y sin publicar un mensaje `ScoringMessage` adicional en la cola SQS de
    scoring.

### Requirement 4: Marcar Vacante como Aplicada

**User Story:** Como usuario autenticado, quiero marcar una vacante como aplicada, para llevar
registro de a qué vacantes ya postulé.

#### Acceptance Criteria

1. WHEN un cliente invoca `POST /me/vacancies/{companyId}/{vacancyId}/apply` para un registro
   `UsuarioVacante` existente de `(userId del JWT, companyId, vacancyId)`, THE Apply_Service SHALL
   establecer `UsuarioVacante.estado = aplicada` y `UsuarioVacante.appliedAt` con la marca de tiempo
   actual, y SHALL retornar HTTP 200, independientemente de si `Vacante.estado` es `abierta` o
   `cerrada`.
2. IF no existe un registro `UsuarioVacante` para `(userId, companyId, vacancyId)`, THEN THE
   Apply_Service SHALL retornar HTTP 404.
3. WHILE `UsuarioVacante.estado` ya es `aplicada`, WHEN se invoca nuevamente
   `POST /me/vacancies/{companyId}/{vacancyId}/apply` para el mismo `(userId, companyId, vacancyId)`,
   THE Apply_Service SHALL retornar HTTP 200 sin modificar `UsuarioVacante.appliedAt`.

### Requirement 5: Generación de CV-ATS

**User Story:** Como usuario autenticado, quiero generar una versión de mi CV optimizada para
sistemas ATS específica de una vacante, para aumentar mis probabilidades de pasar el filtro
automático.

#### Acceptance Criteria

1. IF no existe un registro `UsuarioVacante` para `(userId, companyId, vacancyId)`, THEN THE
   CV_ATS_Service SHALL retornar HTTP 404 antes de evaluar el estado de la `Vacante` o invocar a
   Bedrock_Client.
2. IF existe el registro `UsuarioVacante` y `Vacante.estado` es `cerrada`, THEN THE CV_ATS_Service
   SHALL rechazar la solicitud con HTTP 409 y un código de error que indique que la vacante está
   cerrada, independientemente de si ya existe un `cvAtsTexto` generado previamente.
3. WHEN un cliente invoca `POST /me/vacancies/{companyId}/{vacancyId}/cv` para una vacante con
   `estado = abierta` y un registro `UsuarioVacante` existente, THE CV_ATS_Service SHALL invocar a
   Bedrock_Client con el `Perfiles` del usuario y el contenido de la `Vacante`, en el idioma
   detectado a partir de `Vacante.titulo` y `Vacante.descripcion` (el modelo de datos no incluye un
   campo `idioma`), para generar texto plano en formato ATS.
4. THE CV_ATS_Service SHALL validar la respuesta de Bedrock_Client contra un modelo Pydantic que
   exige texto no vacío, aplicando un reintento con el error de validación inyectado en el prompt
   antes de retornar un error controlado.
5. IF ambos intentos de validación Pydantic fallan, THEN THE CV_ATS_Service SHALL retornar un error
   controlado (HTTP 400 si la causa es una entrada inválida, o HTTP 502 si la causa es una respuesta
   no válida de Bedrock_Client) y SHALL NOT persistir ninguna salida parcial o no validada.
6. WHEN la validación es exitosa, THE CV_ATS_Service SHALL persistir el texto generado en
   `UsuarioVacante.cvAtsTexto`, SHALL establecer `UsuarioVacante.cvGeneratedAt` con la marca de
   tiempo actual, y SHALL retornar HTTP 200 con el texto generado directamente en el cuerpo de la
   respuesta como texto plano, sin subir el texto a ningún servicio de almacenamiento de objetos ni
   retornar un archivo o una URL de almacenamiento.
7. WHEN un cliente invoca `POST /me/vacancies/{companyId}/{vacancyId}/cv` para un registro
   `UsuarioVacante` que ya tiene un `cvAtsTexto` generado previamente y `Vacante.estado` es
   `abierta`, THE CV_ATS_Service SHALL regenerar el texto sobrescribiendo
   `UsuarioVacante.cvAtsTexto` y actualizando `UsuarioVacante.cvGeneratedAt` con la nueva marca de
   tiempo actual, descartando el valor anterior.

### Requirement 6: Banco de Preguntas y Notas por Vacante

**User Story:** Como usuario autenticado, quiero registrar preguntas de entrevista y notas por
vacante, y recibir apoyo de IA para redactar respuestas, para prepararme mejor en cada proceso.

#### Acceptance Criteria

1. WHEN un cliente invoca `GET /me/vacancies/{companyId}/{vacancyId}/entries`, THE Entries_Service
   SHALL retornar todos los registros `Entrada` de `(userId del JWT, companyId, vacancyId)` ordenados
   por `createdAt` ascendente.
2. IF no existe un registro `UsuarioVacante` para `(userId, companyId, vacancyId)`, o no existe un
   registro `Vacante` para `(companyId, vacancyId)`, al invocar
   `GET /me/vacancies/{companyId}/{vacancyId}/entries`, THEN THE Entries_Service SHALL retornar HTTP
   404 en lugar de una lista vacía.
3. WHEN un cliente invoca `POST /me/vacancies/{companyId}/{vacancyId}/entries` con `tipo` igual a
   `preguntas` o `nota_entrevista`, y `contenido` como texto no vacío de máximo 5000 caracteres, THE
   Entries_Service SHALL crear un nuevo registro `Entrada` con `entryId` generado como ULID y
   `createdAt` establecido a la marca de tiempo actual.
4. IF el `tipo` recibido en `POST /me/vacancies/{companyId}/{vacancyId}/entries` no es `preguntas` ni
   `nota_entrevista`, o el `contenido` recibido está vacío o excede 5000 caracteres, THEN THE
   Entries_Service SHALL retornar HTTP 400 con un mensaje de error descriptivo y SHALL NOT crear
   ningún registro `Entrada`.
5. IF no existe un registro `UsuarioVacante` para `(userId, companyId, vacancyId)`, o no existe un
   registro `Vacante` para `(companyId, vacancyId)`, al invocar
   `POST /me/vacancies/{companyId}/{vacancyId}/entries`, THEN THE Entries_Service SHALL retornar HTTP
   404 y SHALL NOT crear ningún registro `Entrada`.
6. THE Entries_Service SHALL NOT exponer ninguna operación de actualización ni de eliminación sobre
   un registro `Entrada` existente.
7. WHEN un cliente invoca `POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer`, THE
   Entries_Service SHALL invocar a Bedrock_Client con la pregunta del `Entrada` referenciado, el
   `resumenParaMatching` del usuario, y el contenido de la `Vacante`, en el idioma de la vacante,
   para generar una respuesta sugerida, validando la salida contra un modelo Pydantic con un
   reintento antes de un error controlado.
8. WHEN la respuesta sugerida se genera y valida exitosamente, THE Entries_Service SHALL crear un
   nuevo registro `Entrada` (append-only) con `tipo = nota_entrevista` que incluya la pregunta original y
   la respuesta sugerida, en lugar de modificar el registro `Entrada` referenciado.
9. IF el `entryId` referenciado en `POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer`
   no pertenece a `(userId, companyId, vacancyId)`, THEN THE Entries_Service SHALL retornar HTTP 404.
10. IF el `entryId` referenciado en
    `POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer` pertenece a
    `(userId, companyId, vacancyId)` pero su `tipo` no es `preguntas`, THEN THE Entries_Service SHALL
    retornar HTTP 400 con un mensaje de error descriptivo indicando que solo se puede generar una
    respuesta sugerida para un `Entrada` de `tipo = preguntas`, y SHALL NOT invocar a Bedrock_Client.
11. IF `Vacante.estado` es `cerrada`, THEN THE Entries_Service SHALL rechazar
    `POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer` con HTTP 409, permitiendo
    sin restricción `GET .../entries` y `POST .../entries` para esa misma vacante.

### Requirement 7: Notificación por Correo tras Escaneo Programado

**User Story:** Como usuario suscrito a empresas, quiero recibir un correo cuando el escaneo
programado encuentra vacantes nuevas, para no tener que revisar la aplicación manualmente cada día.

#### Acceptance Criteria

1. WHEN un `ScanJob` transiciona a un estado terminal (`DONE`, `PARCIAL`, o `FAILED`) Y
   `ScanJob.userId` es nulo, THE Notificador_Lambda SHALL evaluar, para cada `userId` con al menos
   una `Suscripcion` activa hacia una `Empresa` cuyo `companyId` esté en
   `ScanJob.empresasCompletadas`, si corresponde enviar una notificación según los criterios 3 y 4.
2. IF `ScanJob.userId` no es nulo, THEN THE Notificador_Lambda SHALL NOT enviar ningún correo para
   ese `ScanJob`.
3. THE Notificador_Lambda SHALL considerar como "vacante nueva calificada" para un `userId`, en el
   contexto de un `ScanJob` programado, a todo registro `UsuarioVacante` de ese `userId` cuyo
   `estado` sea `nueva` (excluyendo explícitamente `filtered_out` y cualquier otro estado), cuya
   `Vacante.firstSeenAt` sea mayor o igual a `ScanJob.startedAt`, y cuyo `companyId` esté en
   `ScanJob.empresasCompletadas`, independientemente de si el cálculo de `score` de esa vacante ya
   ha finalizado.
4. WHEN el Notificador_Lambda procesa un `ScanJob` programado y determina, según el criterio 3, que
   existe al menos una vacante nueva calificada para un `userId`, THE Notificador_Lambda SHALL
   enviar, mediante SES, un correo a la dirección de correo registrada de ese `userId`.
5. IF, según el criterio 3, ningún `userId` tiene una vacante nueva calificada para ese `ScanJob`
   programado, THEN THE Notificador_Lambda SHALL NOT enviar ningún correo.
6. IF el envío de un correo mediante SES para un `userId` falla por cualquier motivo (incluyendo,
   sin limitarse a, dirección no verificada en modo sandbox, dirección ausente, o error de SES),
   THEN THE Notificador_Lambda SHALL registrar en el log el `userId` y el motivo del fallo sin
   incluir contenido sensible, y SHALL continuar procesando los demás destinatarios sin interrumpir
   la invocación.
7. IF el Notificador_Lambda es invocado más de una vez para el mismo `ScanJob.scanJobId` (por
   reentrega de SQS o del evento de cierre), THEN THE Notificador_Lambda SHALL enviar como máximo un
   correo por cada par `(ScanJob.scanJobId, userId)`.
8. THE Notificador_Lambda SHALL registrar sus eventos en formato JSON estructurado, y SHALL NOT
   incluir en el log el contenido de las descripciones de vacantes ni el contenido del perfil del
   usuario.

### Requirement 8: Escaneo Programado vía EventBridge Scheduler

**User Story:** Como operador del sistema, quiero que el escaneo de empresas se ejecute
automáticamente en un horario fijo, para descubrir vacantes nuevas sin depender de que el usuario
inicie el escaneo manualmente.

#### Acceptance Criteria

1. THE EventBridge_Scheduler SHALL invocar a Orquestador_Lambda según una programación recurrente
   fija definida en la configuración de infraestructura, sin que ninguna solicitud HTTP ni acción de
   un usuario sea necesaria para disparar esa invocación.
2. WHEN Orquestador_Lambda es invocado por EventBridge_Scheduler (en lugar de por una solicitud HTTP
   autenticada a través de API Gateway), THE Orquestador_Lambda SHALL crear un `ScanJob` con el campo
   `userId` sin establecer (nulo).
3. WHEN Orquestador_Lambda es invocado por EventBridge_Scheduler, THE Orquestador_Lambda SHALL
   resolver el conjunto de empresas a escanear como la unión, deduplicada por `companyId`, de los
   `companyId` de todas las `Suscripciones` con `activa = true` de todos los usuarios del sistema, en
   lugar de las suscripciones de un solo usuario.
4. THE EventBridge_Scheduler SHALL NOT incluir el campo `userId`, el claim `sub` del JWT, ni ningún
   otro valor que identifique a un usuario específico (por ejemplo, correo electrónico o nombre de
   usuario) en el payload de invocación hacia Orquestador_Lambda.

### Requirement 9: Extracción de userId desde el JWT

**User Story:** Como responsable de seguridad del sistema, quiero que la identidad del usuario se
determine exclusivamente desde el token verificado, para evitar que un cliente suplante a otro
usuario.

#### Acceptance Criteria

1. THE Vacancy_Listing_API, Vacancy_Detail_API, Manual_Vacancy_Service, Apply_Service,
   CV_ATS_Service, y Entries_Service SHALL extraer el `userId` exclusivamente desde
   `event.requestContext.authorizer.claims.sub` en cada solicitud.
2. IF el cuerpo, los parámetros de consulta, o los encabezados de una solicitud incluyen un campo
   `userId` o equivalente, THEN el endpoint que atiende esa solicitud SHALL ignorar ese valor y
   SHALL usar únicamente el `userId` derivado del JWT para toda la solicitud, incluyendo todas las
   operaciones de lectura y escritura ejecutadas durante su procesamiento.
3. THE Vacancy_Listing_API, Vacancy_Detail_API, Manual_Vacancy_Service, Apply_Service,
   CV_ATS_Service, y Entries_Service SHALL usar el `userId` derivado del JWT como componente de
   clave en toda operación de lectura y de escritura sobre las tablas UsuarioVacante,
   Suscripciones, y Entradas, y SHALL prohibir el uso de cualquier otro valor, origen, o fuente de
   `userId` como componente de clave en dichas operaciones.
4. IF el claim `sub` está ausente o vacío en `event.requestContext.authorizer.claims`, THEN el
   endpoint que atiende esa solicitud SHALL responder con estado HTTP 401 y SHALL no ejecutar
   ninguna operación de lectura ni de escritura sobre UsuarioVacante, Suscripciones, o Entradas.

### Requirement 10: Validación de Salidas de IA con Pydantic y Reintento

**User Story:** Como responsable de calidad del sistema, quiero que ninguna salida de IA se use sin
validar, para evitar persistir datos malformados o inconsistentes.

#### Acceptance Criteria

1. THE Manual_Vacancy_Service, CV_ATS_Service, y Entries_Service SHALL validar toda respuesta
   recibida de Bedrock_Client contra el modelo Pydantic específico de la operación correspondiente
   (definido en los Requirements 3, 5 y 6 de esta spec) antes de utilizar cualquier campo de esa
   respuesta para construir una respuesta HTTP o para persistir un registro.
2. IF el primer intento de validación Pydantic falla, THEN el servicio invocador SHALL reintentar
   exactamente una vez, reinvocando a Bedrock_Client con el mensaje de error de validación inyectado
   en el prompt.
3. IF el segundo intento de validación Pydantic también falla, THEN el servicio invocador SHALL
   retornar HTTP 400 indicando que la salida de la IA no cumplió el formato esperado, y SHALL NOT
   persistir ningún registro derivado de esa salida no validada, ni incluir en el cuerpo de la
   respuesta HTTP ningún campo proveniente de ella.
4. IF, en el primer intento o en el reintento definido en el criterio 2, la invocación a
   Bedrock_Client no retorna ninguna respuesta (por una excepción o por agotamiento del tiempo de
   espera) en lugar de una respuesta que falle la validación Pydantic, THEN el servicio invocador
   SHALL retornar HTTP 502 indicando una falla de la invocación a Bedrock, y SHALL NOT persistir
   ningún registro derivado de esa invocación.

### Requirement 11: Logging Estructurado sin Contenido Sensible

**User Story:** Como responsable de operaciones del sistema, quiero que los logs sean estructurados
y no expongan contenido sensible, para poder diagnosticar problemas sin filtrar datos personales.

#### Acceptance Criteria

1. THE Vacancy_Listing_API, Vacancy_Detail_API, Manual_Vacancy_Service, Apply_Service,
   CV_ATS_Service, Entries_Service, y Notificador_Lambda SHALL emitir entradas de log en formato JSON
   estructurado hacia stdout, incluyendo como mínimo los campos `timestamp` (formato ISO 8601),
   `level` (uno de `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`), `component` (coincidiendo
   exactamente con uno de los nombres de componente definidos en el Glossary), y `message`.
2. THE componentes listados en el criterio 1 SHALL NOT incluir en ninguna entrada de log el texto
   del CV, el contenido del perfil (`perfilEstructurado`, `resumenParaMatching`), la descripción de
   una vacante, el texto de un `cvAtsTexto` generado, la dirección de correo electrónico del usuario,
   el nombre completo del usuario, ni el stack trace o traceback completo de una excepción, con la
   excepción del `userId` opaco permitido por el criterio 3.
3. THE componentes listados en el criterio 1 SHALL aceptar el `userId` opaco extraído del JWT
   (según Requirement 9) como el único identificador de usuario permitido en una entrada de log.
4. WHEN una invocación a Bedrock_Client falla la validación Pydantic, THE servicio invocador SHALL
   registrar el mensaje de error de validación truncado a un máximo de 500 caracteres, sin incluir
   el cuerpo completo de la respuesta cruda de Bedrock_Client.
