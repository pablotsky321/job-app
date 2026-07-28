# Requirements Document

## Introduction

Esta spec (`frontend-spa`) cubre la SPA de `job-search-assistant`: React + Vite + TypeScript con Tailwind
CSS, que consume la API REST ya especificada en `backend-core`, `backend-scan-y-scoring`, y
`backend-vacantes-y-notificaciones`, detrás de un authorizer de Cognito. Cubre las seis pantallas
descritas en `contexto-tecnico-frontend.md` §7 (Onboarding de 4 pasos, Listado principal, Detalle de
vacante, Postulaciones hechas, Fuentes, Descarga de CV-ATS), más lo transversal: autenticación con
Cognito Hosted UI (Authorization Code + PKCE), la capa de acceso a la API con tipos generados por
`openapi-typescript`, y el sistema visual (paleta azul pastel + Inter) ya definido en ese documento.

Esta spec no redefine ningún modelo de dominio ni contrato de API ya especificado en las specs de
backend: los consume tal como están descritos, y documenta explícitamente los huecos de contrato
encontrados en la sección "Dependencias externas pendientes" al final de este documento.

Fuera de alcance de esta spec: ver la sección "Fuera de alcance" al final de este documento.

## Glossary

- **SPA**: la aplicación React + Vite + TypeScript descrita en esta spec.
- **Cognito_Hosted_UI**: la interfaz de login gestionada por Amazon Cognito, alcanzada vía el flujo
  Authorization Code + PKCE. La SPA no construye una pantalla de login propia.
- **Ruta_De_Callback**: la redirect URI configurada en Cognito que recibe, en la URL, el parámetro de
  código de autorización (o de error) devuelto por Cognito_Hosted_UI al finalizar el flujo de login.
- **Auth_Module**: componente de la SPA responsable del flujo de autenticación, el almacenamiento del
  token de sesión, y adjuntar el header `Authorization` en cada llamada a la API.
- **Token_Store**: `sessionStorage` del navegador, usado exclusivamente para persistir `access_token` e
  `id_token` durante la sesión de la pestaña actual.
- **API_Client**: módulo centralizado de la SPA que construye toda llamada HTTP hacia la API, tipado con
  los tipos generados por `openapi-typescript` a partir de `frontend/openapi/openapi.json`.
- **Onboarding_Wizard**: flujo guiado de 4 pasos que recorre un usuario nuevo tras su primer login.
- **Perfil_Estructurado**: objeto con `experiencia`, `educacion`, `proyectos`, `certificaciones`,
  `skills`, `lenguajes`, tal como lo define `backend/shared/models.py` (spec `backend-core`).
- **Cargos_Activos**: lista de puestos objetivo del usuario (`cargosActivos` en `Perfiles`).
- **Empresa**: registro del catálogo compartido de empresas (definido en `backend-core`).
- **Suscripcion**: relación usuario-empresa que habilita el escaneo (definida en `backend-core`).
- **ScanJob**: registro de progreso de un escaneo asíncrono, con `status` restringido a `RUNNING`,
  `DONE`, `PARCIAL`, o `FAILED` (definido en `backend-scan-y-scoring`).
- **Vacante / UsuarioVacante**: modelos de dominio ya definidos en `backend-core` /
  `backend-scan-y-scoring`.
- **Score**: objeto `{ score, veredicto, coincidencias, faltantes, resumen }` que el backend adjunta a
  una vacante puntuada.
- **Veredicto**: campo de `Score` restringido a `excelente | buen_encaje | parcial | bajo`.
- **staleFlag**: indicador booleano que `GET /me/vacancies` adjunta a un elemento cuyo score está
  desactualizado respecto al `profileVersion` vigente del usuario (rescoring híbrido).
- **Listado_Vacantes_View**: pantalla que renderiza `GET /me/vacancies`.
- **Detalle_Vacante_View**: pantalla que renderiza `GET /me/vacancies/{companyId}/{vacancyId}` y el
  flujo de "Presentarse".
- **Postulaciones_View**: pantalla que renderiza `GET /me/vacancies?estado=aplicadas`.
- **Postulacion_Detalle_View**: vista de detalle de una vacante aplicada, con entradas y CV-ATS.
- **CV_ATS_Panel**: componente que muestra el texto de `cvAtsTexto` y expone copiar/descargar.
- **Fuentes_View**: pantalla que muestra el catálogo de empresas y las suscripciones del usuario.
- **Entrada**: registro append-only de pregunta o nota por vacante (definido en
  `backend-vacantes-y-notificaciones`).
- **Score_Color_Mapper**: función pura que traduce un `Veredicto` a un token de color de la paleta
  (`contexto-tecnico-frontend.md` §4.2).
- **Scan_Polling_Hook**: hook basado en TanStack Query que consulta `GET /scans/{jobId}` en intervalos
  regulares hasta alcanzar un `status` terminal (`DONE`, `PARCIAL`, o `FAILED`).
- **Rescoring_Freeze_Logic**: función pura que determina si el orden de `Listado_Vacantes_View` debe
  permanecer congelado mientras existan elementos con `staleFlag=true` pendientes de actualizar.

## Requirements

### Requirement 1: Autenticación vía Cognito Hosted UI

**User Story:** Como usuario, quiero iniciar sesión a través de Cognito Hosted UI y permanecer
autenticado durante mi sesión de navegador, para acceder a mis datos sin que la aplicación construya una
pantalla de login propia.

#### Acceptance Criteria

1. WHEN un usuario no autenticado intenta acceder a cualquier ruta de la SPA distinta de
   Ruta_De_Callback, THE Auth_Module SHALL redirigir al usuario a Cognito_Hosted_UI usando el flujo
   Authorization Code con PKCE.
2. THE SPA SHALL NOT renderizar ningún formulario de login propio (campos de usuario/contraseña) en
   ninguna ruta.
3. WHEN Cognito_Hosted_UI redirige de vuelta a la SPA hacia Ruta_De_Callback con un parámetro de código
   de autorización presente en la URL, THE Auth_Module SHALL intercambiar ese código por `access_token`
   e `id_token` usando el flujo PKCE, sin exponer un client secret, dado que la SPA es un cliente
   público.
4. WHEN el intercambio del código de autorización se completa exitosamente, THE Auth_Module SHALL
   persistir `access_token` e `id_token` exclusivamente en Token_Store.
5. THE Auth_Module SHALL NOT persistir `access_token`, `id_token`, ni `refresh_token` en `localStorage`,
   en una cookie, ni en ningún almacenamiento que sobreviva al cierre de la pestaña del navegador.
6. WHEN el usuario cierra la pestaña del navegador, THE Auth_Module SHALL depender de que Token_Store se
   limpie automáticamente por el navegador, sin implementar ningún mecanismo adicional de persistencia
   de sesión entre pestañas.
7. WHEN el usuario abre una nueva pestaña hacia la SPA, THE Auth_Module SHALL tratar esa pestaña como no
   autenticada y SHALL redirigir a Cognito_Hosted_UI, independientemente de que otra pestaña del mismo
   navegador tenga una sesión activa.
8. THE API_Client SHALL adjuntar el header `Authorization: Bearer <access_token>` leído desde
   Token_Store en toda solicitud hacia la API, con la excepción de las solicitudes que la propia
   Cognito_Hosted_UI realiza como parte del flujo de login.
9. IF una respuesta de la API tiene código HTTP 401, THEN THE Auth_Module SHALL limpiar Token_Store y
   SHALL redirigir al usuario a Cognito_Hosted_UI.
10. THE SPA SHALL NOT leer ni enviar manualmente el claim `sub` del JWT como parámetro en ninguna llamada
    a la API; el backend lo extrae del token en cada solicitud.
11. IF Ruta_De_Callback recibe un parámetro de error en vez de un parámetro de código de autorización
    (por ejemplo, el usuario cancela el login en Cognito_Hosted_UI), THEN THE Auth_Module SHALL mostrar
    un mensaje indicando que el login no se completó, y SHALL ofrecer un botón para reintentar la
    redirección a Cognito_Hosted_UI.
12. IF el intercambio del código de autorización por tokens descrito en el criterio 3 falla por un error
    de red o una respuesta de error de Cognito, THEN THE Auth_Module SHALL NOT persistir ningún token
    parcial en Token_Store, y SHALL mostrar un mensaje de error con un botón para reintentar el login
    desde el inicio.
13. WHEN el intercambio de código por tokens descrito en el criterio 3 se completa exitosamente, THE
    Auth_Module SHALL navegar a la ruta que el usuario intentaba visitar originalmente antes de ser
    redirigido a Cognito_Hosted_UI, o a la ruta raíz de la SPA si no había una ruta original registrada.

### Requirement 2: Capa de acceso a la API con tipos generados

**User Story:** Como desarrollador, quiero un único cliente HTTP tipado con los contratos reales del
backend, para no duplicar tipos de respuesta a mano ni desincronizarme del backend.

#### Acceptance Criteria

1. WHEN se ejecuta el build de la SPA, THE SPA SHALL generar sus tipos de petición y respuesta
   ejecutando `openapi-typescript` sobre `frontend/openapi/openapi.json`.
2. THE SPA SHALL NOT redefinir manualmente los campos de un esquema ya expuesto por
   `frontend/openapi/openapi.json` (derivar tipos con `Pick`, `Omit`, o `Partial` sobre un tipo generado
   SÍ está permitido).
3. THE API_Client SHALL ser el único módulo de la SPA que construye URLs de la API, adjunta el header
   `Authorization`, y parsea el cuerpo de la respuesta HTTP.
4. THE SPA SHALL NOT realizar ninguna llamada HTTP hacia la API fuera de API_Client.
5. IF un endpoint que la SPA necesita consumir no tiene un esquema correspondiente en
   `frontend/openapi/openapi.json`, THEN THE SPA SHALL tratar esa ausencia como una dependencia externa
   pendiente de coordinación con el backend (ver "Dependencias externas pendientes"), y SHALL NOT
   declarar un tipo local ad-hoc como sustituto permanente de ese esquema.
6. THE API_Client SHALL usar TanStack Query para toda operación de lectura que alimente el estado de un
   componente; las operaciones de escritura (`POST`, `PUT`, `DELETE`) no están obligadas a usar TanStack
   Query, aunque pueden implementarse mediante sus mutations, y THE SPA SHALL NOT introducir ninguna
   librería de gestión de estado global (Redux, Zustand, Jotai, Recoil, u otra) para ese propósito.
7. IF una respuesta de la API indica que la sesión ya no es válida, THEN THE API_Client SHALL delegar el
   manejo de esa condición al Auth_Module descrito en Requirement 1 criterio 9, en vez de que cada
   llamador individual maneje ese caso por su cuenta.

### Requirement 3: Sistema visual y restricciones de componentes

**User Story:** Como usuario, quiero una interfaz visualmente coherente con la identidad de marca ya
definida, para que la aplicación no se vea como una plantilla genérica generada por IA.

#### Acceptance Criteria

1. THE SPA SHALL definir los tokens de color `primary`, `gray`, `success`, `error`, `warning`, y
   `cancel` en la configuración de Tailwind exactamente con los valores hexadecimales especificados en
   `contexto-tecnico-frontend.md` §4.2, sin introducir una paleta alternativa.
2. THE SPA SHALL usar Inter, instalada vía el paquete npm `@fontsource/inter`, como única familia
   tipográfica para toda la interfaz, con la excepción del CV-ATS en texto plano (ver Requirement 11),
   que SHALL usar la pila `font-mono` por defecto de Tailwind.
3. THE SPA SHALL NOT establecer texto con las clases `text-xs`, `text-sm`, o `text-base` (o cualquier
   tamaño menor a 16px), en color blanco, cuando el mismo elemento o su contenedor directo inmediato
   tiene un fondo `primary-500`.
4. WHERE un componente de interacción compleja (select, combobox, tabs, toast, progress, dialog/sheet)
   es necesario, THE SPA SHALL copiarlo mediante el CLI de shadcn/ui y SHALL re-tematizarlo dentro del
   mismo commit o PR en que se copia el componente, y antes de usarlo en cualquier ruta de la
   aplicación, sustituyendo cualquier variable `zinc` o `slate` que el componente traiga por defecto.
5. THE SPA SHALL NOT instalar como dependencia npm ninguna librería de componentes UI completa,
   incluyendo, sin limitarse a, Aceternity UI, Magic UI, Material UI, Chakra UI, o Ant Design.
6. THE SPA SHALL NOT instalar GSAP ni Three.js como dependencia, bajo ninguna circunstancia.
7. WHERE se usa Framer Motion para una transición, THE SPA SHALL limitar su uso a una transición que
   ocurre en respuesta a: una operación asíncrona en curso, el resultado directo de una acción del
   usuario, o una revelación secuencial ya definida explícitamente en otro Requirement; THE SPA SHALL
   NOT animar la aparición de tarjetas de una lista de forma decorativa al cargar la página, y THE SPA
   SHALL NOT animar ningún otro componente únicamente por haberse montado o cargado por primera vez.
8. THE SPA SHALL usar un borde de 1px con el token `primary-100` o `gray-200` en las tarjetas de lista,
   y SHALL NOT aplicar ninguna utilidad `shadow-*` de Tailwind sin re-tematizar.
9. THE SPA SHALL NOT instalar Redux, Zustand, Jotai, Recoil, ni ninguna otra librería de gestión de
   estado global como dependencia; el único estado de aplicación fuera de TanStack Query SHALL ser el
   token de sesión gestionado por Auth_Module mediante un Context de React.

### Requirement 4: Onboarding — Paso 1: transformación de CV a Perfil Estructurado (★ momento firma)

**User Story:** Como usuario nuevo, quiero pegar mi CV y ver cómo se transforma en un perfil
estructurado editable, para confiar en que el sistema entendió correctamente mi experiencia antes de
continuar.

#### Acceptance Criteria

1. WHEN un usuario pega texto en el campo de CV del paso 1 y confirma el envío, THE Onboarding_Wizard
   SHALL invocar `POST /me/profile/parse` con ese texto y SHALL mostrar un estado de carga mientras la
   respuesta está pendiente.
2. WHILE la respuesta de `POST /me/profile/parse` está pendiente, THE Onboarding_Wizard SHALL mostrar
   una vista dividida con el texto crudo pegado por el usuario en la mitad izquierda, y SHALL mostrar la
   mitad derecha vacía, sin renderizar ninguna sección del Perfil_Estructurado hasta que la respuesta
   esté disponible.
3. WHEN `POST /me/profile/parse` responde con HTTP 200 y un Perfil_Estructurado, THE Onboarding_Wizard
   SHALL revelar cada sección del Perfil_Estructurado (experiencia, educación, proyectos,
   certificaciones, skills, lenguajes) en la mitad derecha de la vista dividida de forma secuencial,
   campo por campo, en ese orden, en vez de renderizar el perfil completo de una sola vez; THE
   Onboarding_Wizard SHALL omitir la revelación de una sección sin elementos en el Perfil_Estructurado
   recibido, y SHALL revelar los elementos dentro de cada sección en el mismo orden en que aparecen en
   la respuesta de la API.
4. THE Onboarding_Wizard SHALL usar Framer Motion para la revelación secuencial descrita en el criterio
   3, dado que comunica la extracción ocurriendo en tiempo real.
5. WHEN la revelación secuencial del criterio 3 termina, THE Onboarding_Wizard SHALL permitir editar
   cada campo del Perfil_Estructurado mediante un formulario controlado con React Hook Form, validado
   con un esquema Zod equivalente al modelo Perfil_Estructurado, y SHALL deshabilitar la confirmación
   del perfil descrita en el criterio 8 mientras existan errores de validación de ese esquema sin
   resolver.
6. IF `POST /me/profile/parse` responde con HTTP 413, THEN THE Onboarding_Wizard SHALL mostrar un
   mensaje indicando que el texto pegado excede el límite de tamaño permitido (50KB), y SHALL volver a
   la vista de entrada de texto de un solo panel del paso 1, sin la vista dividida de revelación,
   permitiendo al usuario editar el texto ya pegado antes de reenviarlo.
7. IF `POST /me/profile/parse` responde con HTTP 400 o HTTP 502, THEN THE Onboarding_Wizard SHALL
   mostrar un mensaje de error descriptivo distinto del mensaje de tamaño excedido, y SHALL ofrecer un
   botón para reintentar el envío del mismo texto.
8. WHEN el usuario confirma el Perfil_Estructurado editado o sin editar, THE Onboarding_Wizard SHALL
   invocar `PUT /me/profile` con ese Perfil_Estructurado y SHALL avanzar al paso 2 únicamente tras
   recibir HTTP 200.
9. THE Onboarding_Wizard SHALL renderizar el texto crudo pegado por el usuario como texto plano de
   React, y SHALL NOT usar `dangerouslySetInnerHTML` para mostrarlo.
10. IF `PUT /me/profile` responde con un código de error HTTP, THEN THE Onboarding_Wizard SHALL mostrar
    un mensaje de error indicando que el perfil no pudo guardarse, SHALL conservar el
    Perfil_Estructurado editado por el usuario sin descartar los cambios ingresados, y SHALL ofrecer un
    botón para reintentar el envío sin avanzar al paso 2.

### Requirement 5: Onboarding — Paso 2: cargos sugeridos y activos

**User Story:** Como usuario, quiero recibir sugerencias de cargos basadas en mi perfil y elegir cuáles
seguir activamente, para que el sistema filtre y puntúe solo las vacantes relevantes para mí.

#### Acceptance Criteria

1. WHEN el Onboarding_Wizard entra al paso 2 tras guardar el Perfil_Estructurado del paso 1, THE
   Onboarding_Wizard SHALL invocar `POST /me/profile/roles/suggest`.
2. IF `POST /me/profile/roles/suggest` responde con HTTP 424, THEN THE Onboarding_Wizard SHALL iniciar
   un polling de `GET /me/profile` cada 3 segundos, verificando el campo `resumenGenerating` en cada
   respuesta.
3. WHILE el polling descrito en el criterio 2 está en curso y han transcurrido menos de 30 segundos
   desde su inicio, WHEN una respuesta de `GET /me/profile` tiene `resumenGenerating = false`, THE
   Onboarding_Wizard SHALL detener el polling y SHALL reintentar `POST /me/profile/roles/suggest`
   inmediatamente.
4. IF han transcurrido 30 segundos desde el inicio del polling descrito en el criterio 2 sin que
   `resumenGenerating` pase a `false`, THEN THE Onboarding_Wizard SHALL detener el polling y SHALL
   mostrar un mensaje de error con un botón de reintento manual, en vez de continuar el polling
   indefinidamente.
5. WHEN `POST /me/profile/roles/suggest` responde con HTTP 200, THE Onboarding_Wizard SHALL mostrar la
   lista de `suggestions` como opciones seleccionables.
6. WHEN `POST /me/profile/roles/suggest` responde con HTTP 200, THE Onboarding_Wizard SHALL permitir al
   usuario agregar cargos propios mediante texto libre, respetando el límite de 50 caracteres por
   cargo.
7. IF el usuario intenta agregar un cargo propio vacío (tras aplicar trim) o de más de 50 caracteres,
   THEN THE Onboarding_Wizard SHALL NOT agregar ese cargo a la selección, y SHALL mostrar un mensaje de
   validación.
8. WHILE la cantidad combinada de cargos sugeridos elegidos y cargos propios agregados es igual a 10,
   THE Onboarding_Wizard SHALL deshabilitar la posibilidad de agregar un cargo adicional sin
   deseleccionar uno primero, consistente con el límite de 10 cargos del contrato de
   `PUT /me/profile/roles`.
9. WHEN el usuario confirma su selección de cargos (sugeridos elegidos más los propios agregados), THE
   Onboarding_Wizard SHALL invocar `PUT /me/profile/roles` con la lista resultante como
   `cargosActivos`, y SHALL avanzar al paso 3 únicamente tras recibir HTTP 200.
10. IF el usuario confirma una selección vacía de cargos, THEN THE Onboarding_Wizard SHALL enviar
    `cargosActivos` como lista vacía a `PUT /me/profile/roles` sin bloquear el avance al paso 3, dado
    que el backend acepta esa lista vacía.
11. IF `PUT /me/profile/roles` responde con HTTP 400, THEN THE Onboarding_Wizard SHALL mostrar los
    errores de validación devueltos por el backend junto al campo correspondiente, sin avanzar al paso
    3.
12. IF `POST /me/profile/roles/suggest` responde con un código HTTP distinto de 200 y de 424, THEN THE
    Onboarding_Wizard SHALL mostrar un mensaje de error genérico con un botón de reintento.
13. IF `PUT /me/profile/roles` responde con un código HTTP distinto de 200 y de 400 (error de red o
    error 5xx), THEN THE Onboarding_Wizard SHALL mostrar un mensaje de error genérico con un botón de
    reintento, sin avanzar al paso 3.

### Requirement 6: Onboarding — Paso 3: selección de empresas del catálogo

**User Story:** Como usuario, quiero elegir empresas del catálogo compartido para monitorear sus
vacantes, para que el primer escaneo tenga empresas sobre las cuales trabajar.

#### Acceptance Criteria

1. WHEN el Onboarding_Wizard entra al paso 3, THE Onboarding_Wizard SHALL invocar `GET /companies` y
   SHALL mostrar el catálogo mediante un componente Command/Combobox de shadcn re-tematizado,
   permitiendo buscar por nombre.
2. IF `GET /companies` falla con un código de error HTTP, THEN THE Onboarding_Wizard SHALL mostrar un
   mensaje de error indicando que el catálogo no pudo cargarse, SHALL ofrecer un botón para reintentar
   la invocación de `GET /companies`, y SHALL NOT permitir avanzar al paso 4 mientras el catálogo no se
   haya cargado exitosamente al menos una vez.
3. WHEN el usuario selecciona una Empresa del catálogo, THE Onboarding_Wizard SHALL invocar
   `POST /me/companies/{companyId}` para activar la Suscripcion (idempotente, ver "Dependencias
   externas pendientes", punto 1), sin necesidad de distinguir si esa Empresa ya fue seleccionada y
   deselecccionada previamente durante este mismo paso.
4. WHEN el usuario deselecciona una Empresa previamente seleccionada en el mismo paso 3, THE
   Onboarding_Wizard SHALL invocar `PUT /me/companies/{companyId}` con `activa=false`.
5. IF la invocación descrita en el criterio 4 falla con un código de error HTTP, THEN THE
   Onboarding_Wizard SHALL mostrar un mensaje de error para esa Empresa específica, SHALL mantener esa
   Empresa marcada como seleccionada en la interfaz, y SHALL permitir reintentar la deselección sin
   afectar el estado de selección de las demás Empresas.
6. THE Onboarding_Wizard SHALL considerar una Empresa como seleccionada, a efectos de habilitar el
   avance al paso 4, únicamente cuando la invocación descrita en el criterio 3 haya respondido con HTTP
   200 o HTTP 201, y SHALL requerir al menos una Empresa en ese estado antes de permitir avanzar al
   paso 4.
7. IF la invocación descrita en el criterio 3 falla con un código de error HTTP, THEN THE
   Onboarding_Wizard SHALL mostrar un mensaje de error para esa Empresa específica y SHALL permitir
   reintentar la selección sin perder las Empresas ya confirmadas exitosamente.
8. WHEN el usuario confirma su selección de empresas y avanza, THE Onboarding_Wizard SHALL navegar al
   paso 4 sin requerir una llamada adicional de confirmación, dado que cada selección ya se persistió
   individualmente según los criterios 3 y 4.

### Requirement 7: Onboarding — Paso 4: primer escaneo con progreso agregado

**User Story:** Como usuario, quiero ver el progreso de mi primer escaneo de empresas, para saber
cuándo terminó y si encontró vacantes.

#### Acceptance Criteria

1. WHEN el Onboarding_Wizard entra al paso 4, THE Onboarding_Wizard SHALL invocar `POST /scans` y SHALL
   almacenar el `jobId` devuelto.
2. IF la invocación de `POST /scans` descrita en el criterio 1 responde con un código HTTP de error,
   THEN THE Onboarding_Wizard SHALL mostrar un mensaje de error indicando que el escaneo no pudo
   iniciarse, SHALL ofrecer un botón para reintentar esa invocación, y SHALL NOT iniciar el
   Scan_Polling_Hook hasta obtener un `jobId` válido.
3. WHEN el `jobId` está disponible, THE Scan_Polling_Hook SHALL invocar `GET /scans/{jobId}` cada 2
   segundos mediante `refetchInterval` de TanStack Query.
4. WHEN una respuesta de `GET /scans/{jobId}` tiene `status` igual a `DONE`, `PARCIAL`, o `FAILED`, THE
   Scan_Polling_Hook SHALL detener el polling.
5. IF una invocación individual de `GET /scans/{jobId}` realizada por el Scan_Polling_Hook falla por un
   error de red o un código HTTP 5xx (sin llegar a obtener un `status` de negocio en el cuerpo de la
   respuesta), THEN THE Scan_Polling_Hook SHALL continuar el polling en el siguiente intervalo sin
   detenerse, y THE Onboarding_Wizard SHALL seguir mostrando el último contador de progreso agregado
   conocido en vez de un estado de error, hasta que se cumpla el límite del criterio 7 o se reciba una
   respuesta con `status` `DONE`, `PARCIAL`, o `FAILED`.
6. WHILE el polling está en curso y la respuesta más reciente tiene `status` igual a `RUNNING`, THE
   Onboarding_Wizard SHALL mostrar un contador de progreso agregado con el formato "{completadas} de
   {empresasTotal} empresas revisadas", derivado únicamente de los conteos agregados devueltos por
   `GET /scans/{jobId}` (contrato descrito en `backend-scan-y-scoring` Requirement 15), sin mostrar el
   nombre de ninguna Empresa individual completada.
7. IF han transcurrido 600 segundos desde el momento en que el Onboarding_Wizard recibió el `jobId` del
   criterio 1 y el Scan_Polling_Hook realizó su primera invocación de `GET /scans/{jobId}`, sin que el
   `status` devuelto en ninguna respuesta recibida hasta ese momento sea `DONE`, `PARCIAL`, o `FAILED`,
   THEN THE Scan_Polling_Hook SHALL detener el polling de forma independiente al backend, y THE
   Onboarding_Wizard SHALL mostrar un estado de "esto está tardando más de lo esperado" con la opción de
   continuar a la aplicación sin esperar más.
8. WHEN el `status` devuelto es `DONE` o `PARCIAL`, THE Onboarding_Wizard SHALL mostrar un resumen de
   finalización que indica que el escaneo terminó junto con el conteo agregado descrito en el criterio
   6, sin incluir un conteo de vacantes nuevas encontradas, dado que `GET /scans/{jobId}` no expone ese
   dato agregado; a diferencia de Requirement 12 (Fuentes), que sí deriva un conteo de vacantes nuevas
   del lado del cliente mediante `GET /me/vacancies` (ver Requirement 12 criterio 11), este paso del
   Onboarding no muestra ese conteo, y SHALL habilitar el botón para completar el Onboarding_Wizard y
   navegar al Listado_Vacantes_View, donde el usuario puede ver las vacantes resultantes del escaneo.
9. IF el `status` devuelto es `FAILED`, THEN THE Onboarding_Wizard SHALL mostrar un mensaje indicando
   que el escaneo no pudo completarse, visualmente distinto del mensaje de finalización exitosa, y
   SHALL permitir de igual forma completar el Onboarding_Wizard y navegar al Listado_Vacantes_View.
10. THE Onboarding_Wizard SHALL usar un componente Progress de shadcn re-tematizado únicamente si se
    muestra una barra de progreso; en caso contrario SHALL representar el conteo agregado del criterio
    6 mediante texto y/o un indicador numérico, sin implementar un checklist nombrado por Empresa (ver
    "Dependencias externas pendientes", punto 2).

### Requirement 8: Listado principal de vacantes con score y rescoring híbrido

**User Story:** Como usuario, quiero ver mis vacantes activas o aplicadas ordenadas y con su score
visible, para decidir rápidamente a cuáles prestar atención.

#### Acceptance Criteria

1. WHEN el Listado_Vacantes_View se monta, o cuando el usuario vuelve a seleccionar la pestaña
   "activas" tras haber seleccionado la pestaña "aplicadas", THE Listado_Vacantes_View SHALL invocar
   `GET /me/vacancies?estado=activas`, y SHALL invocar `GET /me/vacancies?estado=aplicadas` cuando el
   usuario selecciona la pestaña "aplicadas", mediante un componente Tabs de shadcn re-tematizado.
2. THE Listado_Vacantes_View SHALL renderizar cada vacante como una tarjeta de una sola columna, en este
   orden: fecha de publicación con un check si ya se aplicó, badge de score con color, cargo, empresa,
   lugar/modalidad.
3. THE Listado_Vacantes_View SHALL usar un borde de 1px con `primary-100`/`gray-200` en cada tarjeta, y
   SHALL NOT usar un layout de grid de 3 columnas ni una sombra gris por defecto.
4. THE Score_Color_Mapper SHALL mapear el campo `veredicto` de una vacante a un color de badge según la
   siguiente tabla determinista, y SHALL definir ese mapeo en un único lugar reutilizado por todo
   componente que renderice un badge de score: `excelente` → `success`, `buen_encaje` → `primary`,
   `parcial` → `warning`, `bajo` → `gray`.
5. WHEN un elemento de la respuesta de `GET /me/vacancies` tiene `staleFlag=true`, THE
   Listado_Vacantes_View SHALL mostrar un badge "actualizando…" sobre el score existente de ese
   elemento, en vez de ocultar el score o mostrar un estado de carga en blanco; IF ese elemento no
   tiene aún un score previo (`score` es `null`), THEN THE Listado_Vacantes_View SHALL mostrar el badge
   "actualizando…" solo, sin superponerlo a ningún valor de score.
6. WHILE al menos un elemento de la respuesta más reciente de `GET /me/vacancies` tiene
   `staleFlag=true`, THE Rescoring_Freeze_Logic SHALL congelar el orden de renderizado de la lista
   completa en el orden recibido en esa respuesta, sin reordenar la lista aunque una respuesta de
   refetch posterior devuelva un orden distinto; IF la membresía de la lista cambia durante el
   congelamiento (aparecen o desaparecen elementos respecto a la respuesta congelada), THEN THE
   Rescoring_Freeze_Logic SHALL conservar el orden relativo de los elementos que siguen presentes según
   el orden congelado, y SHALL insertar los elementos nuevos al final de la lista renderizada.
7. WHILE al menos un elemento tiene `staleFlag=true`, THE Listado_Vacantes_View SHALL refrescar la
   consulta `GET /me/vacancies` mediante un `refetchInterval` de 5 segundos, hasta un máximo de 24
   intentos (equivalente a 2 minutos).
8. WHEN, tras el máximo de intentos descrito en el criterio 7, la respuesta más reciente todavía
   contiene al menos un elemento con `staleFlag=true`, THE Listado_Vacantes_View SHALL detener el
   refetch automático, SHALL dejar de congelar el orden de la lista, y SHALL mostrar un botón de
   "actualizar" para que el usuario dispare un refetch manual.
9. WHEN la respuesta de `GET /me/vacancies` deja de contener elementos con `staleFlag=true`, THE
   Rescoring_Freeze_Logic SHALL descongelar el orden de la lista y THE Listado_Vacantes_View SHALL
   renderizar el orden recibido en esa respuesta.
10. THE Listado_Vacantes_View SHALL renderizar la descripción de cada vacante y cualquier texto
    generado por IA (resumen del score) como texto plano de React, y SHALL NOT usar
    `dangerouslySetInnerHTML` para ninguno de esos campos.
11. WHEN una consulta a `GET /me/vacancies` devuelve una lista vacía, THE Listado_Vacantes_View SHALL
    mostrar un estado vacío con un mensaje descriptivo, distinto del componente usado para un error de
    red.
12. WHEN el usuario presiona el botón de "actualizar" manual descrito en el criterio 8, THE
    Listado_Vacantes_View SHALL disparar un único refetch inmediato de `GET /me/vacancies`, sin
    reiniciar el ciclo automático de `refetchInterval`.
13. IF, tras el refetch manual descrito en el criterio 12, la respuesta todavía contiene al menos un
    elemento con `staleFlag=true`, THEN THE Listado_Vacantes_View SHALL mantener visible el botón de
    "actualizar" y SHALL NOT reanudar el `refetchInterval` automático.
14. WHILE existe un congelamiento de orden activo para la pestaña actual, THE Rescoring_Freeze_Logic
    SHALL aplicarse de forma independiente por pestaña ("activas" y "aplicadas"), de modo que, al
    cambiar de pestaña, el congelamiento de una pestaña no afecte el orden mostrado en la otra.

### Requirement 9: Detalle de vacante y flujo de "Presentarse" (★ momento firma)

**User Story:** Como usuario, quiero ver el desglose completo de por qué una vacante calza con mi
perfil, y presentarme con un solo flujo guiado, para decidir informadamente y actuar sin salir de la
pantalla.

#### Acceptance Criteria

1. WHEN el Detalle_Vacante_View se monta con un `companyId` y `vacancyId`, THE Detalle_Vacante_View
   SHALL invocar `GET /me/vacancies/{companyId}/{vacancyId}` y SHALL mostrar la descripción completa, el
   link a la publicación oficial, y el desglose del score.
2. WHILE `score` es un valor numérico, THE Detalle_Vacante_View SHALL renderizar el desglose del score
   en dos columnas lado a lado (coincidencias en una columna, faltantes en la otra), con el valor
   numérico de `score` como número grande en la parte superior, y SHALL NOT renderizar un gráfico de
   dona ni una barra de progreso de porcentaje para representar el score.
3. IF `score` es `null` al montar Detalle_Vacante_View, THEN THE Detalle_Vacante_View SHALL mostrar un
   estado indicando que el score todavía se está calculando, en vez de un desglose de dos columnas
   vacío.
4. THE Detalle_Vacante_View SHALL renderizar la descripción de la vacante y el campo `resumen` del
   score como texto plano de React, y SHALL NOT usar `dangerouslySetInnerHTML` para ninguno de los dos.
5. WHEN Detalle_Vacante_View se monta y la vacante ya tiene `cvAtsTexto` no vacío en la respuesta de
   `GET /me/vacancies/{companyId}/{vacancyId}`, THE Detalle_Vacante_View SHALL mostrar el CV-ATS
   existente de inmediato, sin requerir que el usuario repita el flujo de "Presentarse".
6. WHEN el usuario presiona el botón "Presentarse", THE Detalle_Vacante_View SHALL revelar, en la misma
   vista y sin navegar a otra ruta, el link de la publicación junto con un botón de copiar explícito
   para ese link, y tres acciones ("Generar hoja de vida", "Guardar preguntas", "Guardar"), sin invocar
   ningún endpoint de la API en ese momento.
7. THE Detalle_Vacante_View SHALL usar una transición de Framer Motion para la revelación descrita en
   el criterio 6, dado que comunica la aparición de contenido nuevo.
8. WHEN el usuario presiona "Generar hoja de vida", THE Detalle_Vacante_View SHALL invocar
   `POST /me/vacancies/{companyId}/{vacancyId}/apply` seguido de
   `POST /me/vacancies/{companyId}/{vacancyId}/cv`, y SHALL mostrar el texto de CV-ATS generado una vez
   ambas llamadas se completan exitosamente.
9. WHEN el usuario presiona "Guardar preguntas", THE Detalle_Vacante_View SHALL invocar
   `POST /me/vacancies/{companyId}/{vacancyId}/apply` y SHALL abrir el formulario de banco de preguntas
   y notas (ver Requirement 10) sin requerir una navegación adicional.
10. WHEN el usuario presiona "Guardar", THE Detalle_Vacante_View SHALL invocar
    `POST /me/vacancies/{companyId}/{vacancyId}/apply` únicamente, sin invocar `POST .../cv` ni abrir el
    formulario de entradas.
11. IF cualquiera de las tres acciones descritas en los criterios 8 a 10 falla con un código de error
    HTTP al invocar `POST .../apply`, THEN THE Detalle_Vacante_View SHALL mostrar un mensaje de error
    mediante un componente Toast de shadcn re-tematizado, y SHALL NOT proceder con la llamada
    subsecuente de esa acción (`POST .../cv` o apertura del formulario de entradas).
12. IF `POST /me/vacancies/{companyId}/{vacancyId}/apply` se completa exitosamente pero la invocación
    subsecuente de `POST /me/vacancies/{companyId}/{vacancyId}/cv` falla con un código de error HTTP,
    THEN THE Detalle_Vacante_View SHALL mostrar un mensaje de error mediante un Toast de shadcn
    re-tematizado indicando que la generación del CV-ATS falló, y SHALL permitir reintentar únicamente
    la invocación de `.../cv` sin repetir `.../apply`.
13. WHEN `GET /me/vacancies/{companyId}/{vacancyId}` responde con HTTP 404, THE Detalle_Vacante_View
    SHALL mostrar un estado de "vacante no encontrada" en vez de un desglose de score vacío.
14. IF la invocación de `GET /me/vacancies/{companyId}/{vacancyId}` falla con un código de error HTTP
    distinto de 404, o por un error de red, THEN THE Detalle_Vacante_View SHALL mostrar un mensaje de
    error genérico con un botón de reintento, distinto del estado de "vacante no encontrada".
15. WHILE el campo `estado` de la Vacante subyacente es `cerrada`, THE Detalle_Vacante_View SHALL
    mostrar el mismo desglose de score y descripción que para una vacante abierta, y SHALL deshabilitar
    únicamente la generación de un nuevo CV-ATS, mostrando un mensaje indicando que la vacante está
    cerrada, consistente con el HTTP 409 que devuelve el backend para esa combinación.

### Requirement 10: Postulaciones hechas — listado, detalle, entradas y continuar proceso

**User Story:** Como usuario que ya se presentó a vacantes, quiero ver el historial de mis postulaciones
y agregar nuevas rondas de preguntas o notas, para prepararme para cada etapa del proceso.

#### Acceptance Criteria

1. THE Postulaciones_View SHALL reutilizar el mismo componente de tarjeta que Listado_Vacantes_View
   para renderizar cada vacante aplicada, omitiendo el check de "ya aplicada" descrito en Requirement 8,
   dado que en este contexto es redundante.
2. WHEN el usuario entra al detalle de una postulación, THE Postulacion_Detalle_View SHALL mostrar, en
   este orden: la descripción de la vacante con su link oficial; las entradas guardadas obtenidas de
   `GET /me/vacancies/{companyId}/{vacancyId}/entries` ordenadas cronológicamente; y el CV_ATS_Panel con
   el texto de `cvAtsTexto` si existe.
3. IF `GET /me/vacancies/{companyId}/{vacancyId}/entries` responde con HTTP 404, THEN THE
   Postulacion_Detalle_View SHALL mostrar un estado de "postulación no encontrada" en vez de un
   timeline vacío o un CV_ATS_Panel vacío.
4. THE Postulacion_Detalle_View SHALL renderizar la lista de entradas como un timeline vertical,
   asignando a cada Entrada un marcador propio en el orden cronológico recibido, y SHALL etiquetar
   únicamente los marcadores correspondientes a una Entrada de tipo `nota_entrevista` con su número de
   ronda, calculado como la posición secuencial de esa Entrada entre todas las Entradas de tipo
   `nota_entrevista` de la vacante, empezando en 1; los marcadores de Entradas de tipo `preguntas` SHALL
   NOT mostrar un número de ronda.
5. WHEN el usuario abre el formulario para agregar una entrada, THE Postulacion_Detalle_View SHALL
   requerir la selección de un tipo (`preguntas` o `nota_entrevista`) y un contenido de texto no vacío
   de máximo 5000 caracteres antes de habilitar el envío.
6. WHEN el usuario confirma el formulario descrito en el criterio 5, THE Postulacion_Detalle_View SHALL
   invocar `POST /me/vacancies/{companyId}/{vacancyId}/entries` con el tipo y contenido ingresados, y,
   tras recibir HTTP 201, SHALL cerrar el formulario, vaciar el campo de contenido, y mostrar la Entrada
   creada como el elemento más reciente del timeline sin requerir una recarga manual de la página.
7. WHEN el usuario presiona "Continuar proceso", THE Postulacion_Detalle_View SHALL abrir el mismo
   formulario descrito en el criterio 5, con el campo de contenido pre-rellenado indicando el número de
   ronda calculado como la cantidad de entradas existentes de tipo `nota_entrevista` más uno, en vez de
   dejar ese campo vacío.
8. IF `POST /me/vacancies/{companyId}/{vacancyId}/entries` responde con HTTP 400, THEN THE
   Postulacion_Detalle_View SHALL mostrar los errores de validación sin cerrar el formulario ni
   descartar el contenido ingresado por el usuario.
9. IF `POST /me/vacancies/{companyId}/{vacancyId}/entries` responde con HTTP 404, THEN THE
   Postulacion_Detalle_View SHALL cerrar el formulario, mostrar un mensaje indicando que la postulación
   ya no existe, y SHALL NOT reintentar la invocación automáticamente.
10. THE Postulacion_Detalle_View SHALL NOT exponer ningún control de edición ni de eliminación sobre una
    entrada existente, consistente con que Entradas es append-only.
11. WHEN el usuario presiona una acción de "ayuda de IA para responder" sobre una entrada de tipo
    `preguntas`, THE Postulacion_Detalle_View SHALL invocar
    `POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer`, SHALL mostrar un estado de
    carga asociado a esa entrada mientras la respuesta está pendiente, y SHALL mostrar la respuesta
    sugerida como una nueva entrada en el timeline una vez la llamada se completa exitosamente.
12. IF `POST /me/vacancies/{companyId}/{vacancyId}/entries/{entryId}/answer` falla con un código de
    error HTTP, THEN THE Postulacion_Detalle_View SHALL detener el estado de carga descrito en el
    criterio 11, SHALL mostrar un mensaje de error indicando que no se pudo generar la respuesta
    sugerida, y SHALL NOT crear ninguna Entrada nueva en el timeline.
13. THE Postulacion_Detalle_View SHALL renderizar el contenido de cada Entrada como texto plano de
    React, y SHALL NOT usar `dangerouslySetInnerHTML` para ninguna entrada.

### Requirement 11: Descarga y copia del CV-ATS en el navegador

**User Story:** Como usuario, quiero copiar o descargar el CV-ATS generado para una vacante, para
pegarlo directamente en un formulario de un sistema ATS.

#### Acceptance Criteria

1. THE CV_ATS_Panel SHALL renderizar el texto de `cvAtsTexto` usando la pila `font-mono` por defecto de
   Tailwind, sin colores, iconos decorativos, ni tarjetas adicionales alrededor del texto.
2. WHEN el usuario presiona el botón "copiar", THE CV_ATS_Panel SHALL copiar el texto completo de
   `cvAtsTexto` al portapapeles del navegador mediante la API Clipboard, sin realizar ninguna llamada a
   la API, y SHALL mostrar una confirmación visual observable (por ejemplo, un cambio de texto o de
   ícono en el botón) de que la copia fue exitosa.
3. IF la invocación a la API Clipboard falla (permisos denegados o contexto no seguro), THEN THE
   CV_ATS_Panel SHALL mostrar un mensaje de error indicando que no se pudo copiar al portapapeles, sin
   mostrar la confirmación visual de éxito.
4. WHEN el usuario presiona el botón "descargar", THE CV_ATS_Panel SHALL construir un objeto `Blob` en
   el navegador con el contenido de `cvAtsTexto` y SHALL disparar la descarga mediante un elemento
   `<a download>` con extensión `.txt`, sin invocar ningún endpoint adicional de la API ni solicitar una
   URL prefirmada.
5. THE CV_ATS_Panel SHALL nombrar el archivo descargado incluyendo tanto (el `companyId` o el nombre de
   la empresa) como (el `vacancyId` o el identificador de la vacante), de forma que dos descargas de
   vacantes distintas siempre produzcan nombres de archivo distintos.
6. IF `cvAtsTexto` está vacío o no existe para la vacante consultada, THEN THE CV_ATS_Panel SHALL
   mostrar un estado indicando que el CV-ATS aún no se ha generado, en vez de mostrar botones de
   copiar/descargar deshabilitados sin explicación.

### Requirement 12: Fuentes — catálogo, suscripciones, escaneo manual y avisos de fuentes fallando

**User Story:** Como usuario, quiero ver la salud de cada empresa que sigo y disparar un escaneo manual
cuando lo necesite, para tener control y transparencia sobre qué se está monitoreando.

#### Acceptance Criteria

1. WHEN el Fuentes_View se monta, THE Fuentes_View SHALL invocar `GET /me/companies` y SHALL mostrar
   cada Suscripcion con un indicador de estado como elemento principal de la fila, junto con
   `lastScannedAt` visible sin requerir un clic adicional, coloreando ese indicador en gris cuando
   `lastScannedAt` es `null`, en rojo cuando `consecutiveFailures >= 3`, y en verde en cualquier otro
   caso.
2. WHEN una Suscripcion mostrada tiene `consecutiveFailures >= 3`, THE Fuentes_View SHALL mostrar el
   mensaje "No hemos podido revisar {nombre de la empresa} desde el {lastScannedAt}" junto con botones
   de reintentar y desactivar, visible sin clic adicional.
3. WHEN el usuario presiona "reintentar" sobre una Empresa con `consecutiveFailures >= 3`, THE
   Fuentes_View SHALL invocar `POST /scans` (que reescanea todas las Suscripciones activas del usuario,
   no solo la Empresa señalada, según el contrato de Orquestador_Lambda de `backend-scan-y-scoring`) y
   SHALL iniciar el mismo Scan_Polling_Hook usado en el Onboarding_Wizard paso 4 (ver Requirement 7).
4. WHEN el usuario presiona "desactivar" sobre una Empresa, THE Fuentes_View SHALL invocar
   `PUT /me/companies/{companyId}` con `activa=false`.
5. WHEN el usuario dispara un escaneo manual desde el Fuentes_View, THE Fuentes_View SHALL capturar la
   marca de tiempo en la que invoca `POST /scans` (`scanStartedAt`), y WHEN el resultado del polling
   indica `status DONE`, THE Fuentes_View SHALL invocar `GET /me/vacancies?estado=activas` y SHALL
   contar los registros cuyo campo `firstSeenAt` sea posterior o igual a `scanStartedAt`; IF ese conteo
   es igual a 0, THEN THE Fuentes_View SHALL mostrar el mensaje "Tus {N} empresas están al día — última
   revisión hace {tiempo}" con la lista de empresas y sus `lastScannedAt`, usando un componente
   visualmente distinto del componente usado para un escaneo `FAILED`.
6. THE Fuentes_View SHALL NOT reutilizar el mismo componente ni el mismo color usado para representar
   un escaneo `FAILED` al representar un escaneo `DONE` sin vacantes nuevas, consistente con que ambos
   casos son semánticamente distintos.
7. WHEN el usuario agrega una empresa nueva mediante una URL que no existe en el catálogo, THE
   Fuentes_View SHALL invocar `POST /companies` con esa URL y, tras recibir HTTP 201, SHALL invocar
   `POST /me/companies/{companyId}` para crear la Suscripcion correspondiente del usuario hacia esa
   Empresa recién creada (ver "Dependencias externas pendientes", punto 1).
8. IF `POST /companies` responde con HTTP 409 (empresa ya existe), THEN THE Fuentes_View SHALL usar el
   `companyId` devuelto en el cuerpo del error para invocar `POST /me/companies/{companyId}` en vez de
   mostrar únicamente un mensaje de error, de forma que el usuario pueda suscribirse a una empresa ya
   presente en el catálogo sin un paso adicional.
9. THE Fuentes_View SHALL usar un componente Command/Combobox de shadcn re-tematizado para la búsqueda
   de empresas del catálogo, consistente con el componente usado en el Onboarding paso 3.
10. WHEN el usuario selecciona una Empresa del catálogo obtenido de `GET /companies` que no está en su
    lista de Suscripciones, THE Fuentes_View SHALL invocar `POST /me/companies/{companyId}` para crear
    la Suscripcion, de la misma forma que en el Onboarding paso 3 (ver Requirement 6).
11. IF el conteo de registros con `firstSeenAt` posterior o igual a `scanStartedAt` descrito en el
    criterio 5 es mayor a 0, THEN THE Fuentes_View SHALL mostrar un resumen indicando esa cantidad de
    vacantes nuevas encontradas, en vez del mensaje descrito en el criterio 5.
12. IF el resultado del polling de un escaneo manual disparado desde el Fuentes_View indica `status
    FAILED` o `status PARCIAL`, THEN THE Fuentes_View SHALL mostrar un mensaje indicando que el escaneo
    no se completó para todas las Empresas del usuario, usando un componente visualmente distinto del
    usado en los criterios 5 y 11.
13. IF `POST /companies` responde con un código de error HTTP distinto de 409, o si una invocación
    subsecuente de `POST /me/companies/{companyId}` descrita en los criterios 7, 8, o 10 falla con un
    código de error HTTP, THEN THE Fuentes_View SHALL mostrar un mensaje de error para esa Empresa
    específica sin descartar el texto de búsqueda ingresado por el usuario ni las Suscripciones ya
    confirmadas exitosamente.

### Requirement 13: Funciones puras de verificación (arnés de tests Vitest)

**User Story:** Como desarrollador construyendo la SPA, quiero un arnés de tests Vitest sobre la lógica
pura crítica, para confirmar que esa lógica hace lo que debe sin depender de correr la aplicación
manualmente cada vez.

#### Acceptance Criteria

1. THE SPA SHALL incluir un test Vitest para Score_Color_Mapper que verifica, para cada uno de los
   cuatro valores de `veredicto` (`excelente`, `buen_encaje`, `parcial`, `bajo`), que la función
   devuelve exactamente el color definido en Requirement 8 criterio 4.
2. THE SPA SHALL incluir un test Vitest para la función que determina la condición de salida del
   polling de `GET /scans/{jobId}`, verificando que devuelve verdadero para `status` igual a `DONE`,
   `PARCIAL`, o `FAILED`, y falso para `status` igual a `RUNNING`.
3. THE SPA SHALL incluir un test Vitest para Rescoring_Freeze_Logic, verificando que devuelve verdadero
   cuando al menos un elemento de una lista de vacantes tiene `staleFlag=true`, que devuelve falso
   cuando ningún elemento la tiene, y que una lista vacía de vacantes se clasifica como "ningún elemento
   tiene `staleFlag=true`" (la función devuelve falso).
4. THE SPA SHALL incluir un test Vitest para la función que construye el `Blob` de descarga del
   CV-ATS, verificando el nombre de archivo generado según la regla de Requirement 11 criterio 5 (debe
   incluir tanto el `companyId` o nombre de empresa como el `vacancyId` o identificador de la vacante),
   la extensión `.txt`, y que el contenido del `Blob` es idéntico al texto de `cvAtsTexto` recibido.
5. THE SPA SHALL incluir un test Vitest para la función que distingue un "escaneo sin cambios" de un
   "escaneo fallido" a partir del `status` de un ScanJob y del conteo de vacantes nuevas, usando, para
   los casos de test, un conteo de empresas revisadas y un conteo de vacantes nuevas expresados como un
   entero dentro del rango de 0 a 999, y verificando que un `status DONE` con cero vacantes nuevas se
   clasifica como éxito sin novedades para cualquier conteo de empresas revisadas dentro de ese rango, y
   que un `status FAILED` se clasifica como fallo para cualquier conteo de vacantes nuevas dentro de ese
   rango.
6. THE SPA SHALL NOT incluir en su suite de Vitest ningún test que renderice un componente React ni que
   dependa de React Testing Library, Playwright, o Cypress.

## Dependencias externas pendientes

Estos puntos son huecos o discrepancias de contrato entre `contexto-tecnico-frontend.md` y los specs de
backend ya implementados o especificados. Esta spec asume el comportamiento descrito abajo para poder
escribir requisitos de frontend verificables; la corrección real del contrato queda pendiente como tarea
correctiva en `backend-core` o en la spec del worker correspondiente — no es parte del alcance de
`frontend-spa`.

1. **Alta de suscripción (`POST /me/companies/{companyId}`).** El `backend-core` ya implementado
   (`backend/api/routes/companies.py`) solo expone `PUT /me/companies/{companyId}` para activar o
   desactivar una Suscripcion **ya existente**; no existe ningún endpoint que cree la primera
   suscripción de un usuario hacia una empresa. Requirement 6 y Requirement 12 de esta spec asumen que
   existirá `POST /me/companies/{companyId}` con el siguiente contrato, ya decidido: el endpoint SHALL
   ser idempotente — si la Suscripcion no existe, la crea con `activa=true` y `addedAt=ahora`; si existe
   con `activa=false`, la actualiza a `activa=true`; si ya existe con `activa=true`, no realiza ningún
   cambio y responde HTTP 200 (en vez de HTTP 201, reservado para la creación real). Esta idempotencia
   elimina la necesidad de que el frontend recuerde si una Empresa fue deseleccionada y reseleccionada
   dentro del mismo paso de Onboarding.

2. **Progreso por empresa nombrada en `GET /scans/{jobId}`.** El contrato real
   (`backend-scan-y-scoring`, Requirement 15) solo expone conteos agregados mientras `status = RUNNING`
   (no la lista de qué `companyId` específico ya se completó; esa lista solo se expone para empresas
   *pendientes* cuando `status = PARCIAL`). Por eso Requirement 7 de esta spec usa un contador agregado
   ("N de M empresas revisadas") en el paso 4 del Onboarding, en vez del checklist por-empresa nombrado
   que sugiere `contexto-tecnico-frontend.md` §7.1. Extender ese contrato para exponer el checklist real
   queda fuera de esta spec.

3. **Disparador de `resumenParaMatching`.** Ningún spec de backend revisado (`backend-core`,
   `backend-scan-y-scoring`, `backend-vacantes-y-notificaciones`) define qué proceso genera
   `resumenParaMatching` ni qué lo dispara tras `PUT /me/profile`. Requirement 5 de esta spec asume que
   ese proceso corre en segundos y expone su progreso a través del campo `resumenGenerating` en la
   respuesta de `GET /me/profile` (booleano derivado internamente por el backend a partir de
   `resumenGenerationStatus` en la tabla Perfiles; ese nombre de campo interno no es lo que la API
   expone al cliente) — de ahí el polling con tope de 30 segundos. Si ese worker no existe todavía en
   el momento de integrar, el paso 2 del Onboarding queda bloqueado en producción hasta que se
   implemente.

4. **Discrepancia de rutas de cargos.** `contexto-tecnico-frontend.md` §5 lista `POST /me/roles/suggest`
   y `PUT /me/roles`, pero el `openapi.json` real generado por el backend implementado expone
   `POST /me/profile/roles/suggest` y `PUT /me/profile/roles`. Esta spec usa las rutas reales de
   `openapi.json` (fuente de verdad declarada en el propio documento de contexto §5), no las del
   documento de contexto. Se recomienda actualizar `contexto-tecnico-frontend.md` para reflejar las
   rutas reales.

5. **Alcance de "reintentar" una fuente específica en Fuentes.** `POST /scans` (Orquestador_Lambda)
   siempre reescanea todas las Suscripciones activas del usuario, no una empresa puntual — no existe
   forma de acotar el escaneo a una sola empresa. Requirement 12 de esta spec documenta esto
   explícitamente: el botón "reintentar" de una fuente fallando dispara un escaneo completo del
   usuario, no limitado a esa empresa.

6. **Inmutabilidad de `firstSeenAt` (supuesto no verificado por código aún).** Requirement 12 de esta
   spec (criterios 5 y 11) deriva el conteo de "vacantes nuevas" de un escaneo manual contando
   registros de `GET /me/vacancies?estado=activas` cuyo `firstSeenAt` sea posterior o igual a
   `scanStartedAt`. Esta lógica depende de que `firstSeenAt` se asigne una sola vez, en la creación del
   `Vacante`, y nunca se modifique en ninguna actualización posterior. El contrato especificado en
   `backend-scan-y-scoring/requirements.md` (Requirement 7, criterios 6-7) y su diseño ya garantizan
   esto explícitamente, incluyendo la rama de reaparición (solo actualiza `lastSeenAt`) y la rama de
   reapertura (`estado cerrada` → `abierta`, tampoco toca `firstSeenAt`). Sin embargo, la Tarea 8 de
   `backend-scan-y-scoring` (`apply_missCount_logic`, en `backend/shared/misscount_logic.py`) todavía no
   está implementada — es, por ahora, una garantía de contrato documentada, no un comportamiento
   verificado por código o test real. **Recomendación operativa**: cuando se implemente la Tarea 8, el
   test de función pura para `apply_missCount_logic` (ya exigido por el alcance de tests de
   `backend-scan-y-scoring`, ver su sección de Tests) debe incluir un caso explícito que verifique que
   `firstSeenAt` permanece sin cambios tanto en la rama de reaparición como en la rama de reapertura de
   una Vacante existente — no solo que `missCount` se resetee correctamente. Esto convierte el supuesto
   de inmutabilidad de `firstSeenAt` en algo verificado por test, no solo documentado por contrato,
   antes de que Requirement 12 de esta spec de frontend se construya sobre él.

## Fuera de alcance

- Panel de administración con UI.
- BYOK (usuario trae su propia API key).
- Registro público.
- Recuperación de contraseña self-service.
- Filtro por idioma.
- Pantalla de históricos de vacantes cerradas.
- Vista agregada de preguntas por empresa.
- Cualquier librería de gestión de estado global (Redux, Zustand, Jotai, Recoil, u otra).
- Cualquier librería de componentes UI instalada como dependencia (MUI, Chakra, Ant Design, Aceternity
  UI, Magic UI).
- Motion decorativo mediante GSAP o Three.js/WebGL.
- Tests de componentes o end-to-end (React Testing Library, Playwright, Cypress).
- Generación de `.docx` para el CV-ATS (opcional únicamente si sobra tiempo; no incluida en los
  requisitos de esta spec).
- Terraform / infraestructura (cubierto por specs de infraestructura, no por esta).

## End of Requirements

---

**Next Steps:**
1. El usuario revisa los requisitos por completitud y claridad.
2. El usuario puede solicitar cambios, aclaraciones, o marcar como aprobado.
3. Tras la aprobación, el flujo continúa a la fase de Diseño.
