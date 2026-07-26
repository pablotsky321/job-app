---
inclusion: manual
---

# Contexto maestro — Asistente de Búsqueda de Empleo
 
> **Propósito de este documento.** Es el estado consolidado del proyecto, pensado para **restaurar
> contexto en conversaciones futuras** (generar prompts para el backend, diseñar el frontend, escribir
> el README, preparar el video, etc.). No es el prompt que se le entrega a Kiro — de este documento se
> derivan esos prompts.
>
> **Reemplaza a `contexto_proyecto.txt` y `requisitos_job_search_assistant.md`, que fueron eliminados.**
> Todo lo rescatable de ellos está absorbido aquí, incluyendo lo que quedó fuera de alcance, para no
> perder el razonamiento.
>
> Última actualización: julio 2026, tras cuatro rondas de revisión crítica del diseño.
 
---
 
## Índice
 
1. [Contexto del hackathon](#1-contexto-del-hackathon)
2. [Panorama competitivo](#2-panorama-competitivo)
3. [Visión de producto completo](#3-visión-de-producto-completo-referencia-histórica)
4. [Stack cerrado y stacks descartados](#4-stack-cerrado-y-stacks-descartados)
5. [Alcance del MVP](#5-alcance-del-mvp)
6. [Modelo de datos](#6-modelo-de-datos-dynamodb)
7. [Arquitectura AWS](#7-arquitectura-aws)
8. [Flujo de descubrimiento](#8-flujo-de-descubrimiento)
9. [Scoring de match](#9-scoring-de-match-diferenciador-principal)
10. [Contratos de API](#10-contratos-de-api)
11. [Tareas de Bedrock](#11-tareas-de-bedrock)
12. [Frontend](#12-frontend)
13. [Infraestructura](#13-infraestructura)
14. [Tests y datos de demo](#14-tests-y-datos-de-demo)
15. [Bloqueos con latencia externa](#15-bloqueos-con-latencia-externa)
16. [Plan de construcción](#16-plan-de-construcción)
17. [Registro de decisiones invertidas](#17-registro-de-decisiones-invertidas-con-argumento)
18. [Preguntas abiertas](#18-preguntas-abiertas)
19. [Trampas técnicas conocidas](#19-trampas-técnicas-conocidas)
20. [Conversaciones pendientes](#20-conversaciones-pendientes)
---
 
## 1. Contexto del hackathon
 
**Hackathon Código Facilito — Reto 2: Aplicaciones Web.**
Equipo de 2 desarrolladores. Créditos de Kiro disponibles. Plazo: 1–2 semanas de desarrollo real.
 
### Criterios de evaluación
 
| Peso | Criterio | Qué mide |
|---|---|---|
| 30% | **Impacto tecnológico** | Necesidad real, valor en entornos de desarrollo/empresa/educación |
| 30% | **Innovación** | Ventaja técnica frente a alternativas del mercado |
| 30% | **Software funcional y entregables** | Repo público con README, demo en línea, video ≤5 min (1 por equipo) |
| 10% | **Uso de AWS y Kiro** | Al menos un servicio de AWS visible en la arquitectura |
 
### Implicaciones estratégicas de la rúbrica
 
- **El 30% de software funcional castiga la implementación parcial de muchas funcionalidades** más de lo
  que castiga un alcance pequeño y completo. Esto justifica todos los recortes de §5.
- **El 10% de AWS ya está sobradamente cubierto** (Cognito, Bedrock, DynamoDB, Lambda, SQS, SES, S3,
  CloudFront, API Gateway, EventBridge). No hay que añadir servicios "para mostrar".
- **El 30% de innovación descansa sobre el scoring de match** (§9), no sobre el descubrimiento de
  vacantes, que es commodity.
- **Terraform y CI/CD no están en la rúbrica.** Valen cero puntos directos y cuestan 15–20 horas. Son el
  primer sacrificable.
### Motivación de fondo
 
Utilidad personal real más allá del concurso. El modelo de usuarios cerrados es una **decisión
permanente**, no un parche para el hackathon: el producto está pensado para un grupo pequeño de personas
conocidas, no para escalar a público general.
 
---
 
## 2. Panorama competitivo
 
El espacio de "asistentes de búsqueda de empleo con IA" ya está ocupado:
 
- **Jobright.ai** — sugiere roles y personaliza materiales a partir del CV
- **Teal / Simplify Copilot** — autocompletan postulaciones en 100+ portales
- **LazyApply** y similares — auto-aplicación masiva
- **Glassdoor / Blind** — crowdsourcean preguntas de entrevista
**La idea general no es única.** El diferenciador real tiene que ser de ejecución.
 
**Diferenciador original (descartado):** el banco de preguntas de entrevista por empresa. Al decidirse que
es **privado por usuario** y **por vacante**, dejó de tener efecto de red y quedó reducido a "una libreta
de notas con IA". Útil, pero no defendible como innovación.
 
**Diferenciador actual:** el **scoring de match con explicación desglosada** contra el perfil del usuario.
Ver §9. Esto es lo que carga el 30% de innovación y debe ser lo primero que se vea en el video.
 
---
 
## 3. Visión de producto completo (referencia histórica)
 
> Esta sección preserva lo que estaba en los documentos borrados y **no** entra al MVP. Sirve para el
> README (sección de roadmap) y para retomar el proyecto después del hackathon.
 
### 3.1 CV-visual con marca de empresa
 
Se identificó una contradicción en el planteamiento original: un CV optimizado para ATS (texto plano) y un
CV con colores/diseño de marca son objetivos que se pisan. Resolución conceptual (válida, solo aplazada):
 
1. **CV-ATS**: texto plano, estructura simple, optimizado por palabras clave. Es el que se sube a sistemas
   automatizados. **← este sí entra al MVP.**
2. **CV-visual**: `.docx` simple **construido por código** (no por un agente de IA) — plantilla con los
   colores de marca guardados de la empresa, donde el código inserta el texto ya generado por IA una sola
   vez. Se descartó la idea de un "agente especializado": no aporta nada que el templating por código no
   resuelva más barato.
**Precaución que se mantiene:** aunque sea texto y no imagen, un `.docx` con columnas/tablas/cabeceras de
color todavía puede confundir a ATS estrictos. Por eso son dos artefactos separados, no uno que intente
servir ambos propósitos.
 
**Modelo de datos correcto (si se retoma):** las plantillas de marca **no son por usuario, son globales y
compartidas**. Cuando cualquier usuario matricula una empresa por primera vez, el código genera su
plantilla una sola vez; otro usuario que aplique después reutiliza la existente.
 
**Pendiente si se retoma:** mecanismo exacto para capturar colores/logo la primera vez (extracción del
sitio, entrada manual, u otro método por código).
 
### 3.2 Panel de administración
 
Rol de administrador (Cognito Group `Admins`, un único usuario). Funciones: crear usuarios,
deshabilitar/reactivar, ver y ajustar límites, resetear contadores.
 
**Cortado** porque es un módulo completo (UI + backend + rol) con cero valor demostrable ante el jurado.
En el MVP se hace todo por consola y CLI de AWS.
 
### 3.3 APIs públicas de empleo
 
Candidatas: **Adzuna, Arbeitnow, RemoteOK, Jooble.**
 
Decisión tomada en su momento: usarlas **solo como fuente de vacantes remotas**. Adzuna está confirmado
que no cubre Colombia y la cobertura local del resto es incierta; al limitarlas a remoto, deja de importar
la cobertura geográfica local. RemoteOK en particular está construido para eso y no requiere autenticación.
 
**Cortado del MVP** porque cada una es registro + key + esquema distinto + mapeo. Si sobra tiempo, agregar
**solo RemoteOK** (sin auth).
 
### 3.4 Otros elementos fuera de alcance
 
- **BYOK** (el usuario trae su propia key de OpenAI/Anthropic/Google) — descartado permanentemente: choca
  con el criterio de uso de AWS y complica el modelo de costos sin beneficio a esta escala.
- **Registro público / multi-tenant** — descartado permanentemente por diseño.
- **Login o scraping con credenciales a LinkedIn, Computrabajo, etc.** — descartado permanentemente por
  riesgo legal de ToS, fragilidad técnica y manejo de credenciales de terceros. *(La entrada manual de
  vacante por texto pegado, §8.5, resuelve el mismo problema sin ninguno de esos riesgos.)*
- **Parsers dedicados por plataforma de ATS más allá de Greenhouse/Lever** (Workday, etc.) — solo si el
  camino genérico resulta insuficiente en la práctica.
- **Recuperación de contraseña / flujo self-service de cuenta.**
- **Filtro por idioma requerido** — poco confiable de extraer, poco visible en demo.
- **Pantalla de históricos** — el TTL sí se implementa; la pantalla no.
- **Vista agregada de preguntas por empresa** — es un GSI aditivo, se puede añadir después sin migración.
### 3.5 Investigación preservada: Lambda MicroVMs — NO aplica
 
AWS lanzó **Lambda MicroVMs el 22 de junio de 2026**. Es un recurso **nuevo y distinto** de las Lambda
Functions normales, con su propio namespace de API. Provee aislamiento a nivel de VM (Firecracker),
arranque y reanudación casi instantáneos, y preservación de estado hasta 8 horas — pensado para ejecutar
**código no confiable o generado dinámicamente por IA**: sandboxes de asistentes de código, plataformas de
análisis, escáneres de vulnerabilidades.
 
**El nombre se presta a confusión con "microservicios" pero es un producto distinto para un problema
distinto.** Esta app nunca ejecuta código arbitrario (la IA solo genera texto/JSON estructurado), así que
las **Lambda Functions normales son la herramienta correcta**. Está disponible en `us-east-1`, pero eso no
cambia que no aplica.
 
*Preservado aquí para no repetir la investigación.*
 
### 3.6 Bedrock AgentCore — sin caso de uso
 
Al descartarse el "agente especializado" para generar el CV visual (§3.1) en favor de templating por
código, **no quedó ningún candidato para AgentCore** en el alcance. Ningún componente necesita un ciclo
agéntico real (planear, usar herramientas, iterar); todo son llamadas puntuales a un modelo.
 
**No forzar su uso solo por mostrarlo.** El criterio (d) ya está sobradamente cubierto.
 
---
 
## 4. Stack cerrado y stacks descartados
 
### 4.1 Stack final
 
| Capa | Tecnología |
|---|---|
| Frontend | React + Vite + TypeScript (SPA, build estático) |
| Backend | **Python únicamente.** FastAPI + Mangum en una Lambda para la API; Lambdas separadas para workers |
| Base de datos | DynamoDB, **tablas separadas** (no single-table) |
| Asincronía | SQS (dos colas) + Lambda workers |
| IA | Amazon Bedrock, región `us-east-1` |
| Hosting frontend | S3 + CloudFront |
| Infra | Terraform, un solo ambiente, estado en S3 con versionado |
| CI/CD | GitHub Actions con OIDC (rol asumido) |
| Empaquetado Lambda | **Zip**, construido en CI, subido a S3 |
 
### 4.2 Descartados, con el argumento completo
 
**Backend en Java + Python (planteamiento inicial).**
La justificación era "Java para peticiones a la base de datos, Python para procesar archivos y comunicación
con los agentes". Ninguna se sostuvo:
- El acceso a DynamoDB es donde menos importa el lenguaje. No hay carga de CPU ni lógica de dominio compleja.
- No hay agentes — el propio análisis concluyó que no hay caso de uso para AgentCore. Son llamadas
  `InvokeModel`, que el SDK de Java hace igual.
- No hay archivos que procesar: el CV entra por copiar y pegar, no por upload.
- Limpieza de HTML: Jsoup (Java) es incluso mejor herramienta que BeautifulSoup.
- Generación de `.docx`: era la única tarea que apuntaba a Python, y ese módulo se cortó.
El costo real de dos runtimes: dos pipelines de build, dos sistemas de dependencias, dos formas de
empaquetar Lambdas, dos configuraciones en Terraform, y **dos lugares donde definir los mismos modelos de
datos**, que hay que mantener sincronizados a mano.
 
Además: **Java en Lambda con tráfico esporádico es casi todo cold start.** Con 5 usuarios, prácticamente
cada request llega a un contenedor frío. Sin SnapStart son varios segundos; con SnapStart hay que versionar
y publicar cada función, lo que complica Terraform. "La primera petición tarda 6 segundos" es visible en la
demo y afecta el criterio de software funcional (30%).
 
> La única condición que invertiría esto: si uno del equipo es materialmente más lento escribiendo Python.
> En ese caso, **todo Java** con SnapStart. Lo que no se debe hacer es los dos.
 
**Next.js con SSR.**
La app está 100% detrás de Cognito. No hay contenido público, no hay SEO, no hay link previews, no hay
first-paint que optimizar para usuarios anónimos. SSR obligaría al servidor de Next a recibir el JWT y
reenviarlo a API Gateway — plomería adicional para no ganar nada que un fetch en cliente no dé.
 
Next.js en modo estático tampoco vale la pena con este plazo: añade configuración (`output: 'export'`,
cuidado con lo que se puede usar) a cambio de un DX que no se necesita en una app de ~8 pantallas.
 
**Amplify Hosting.**
Su valor es hacer el CI/CD por ti conectándose al repo. Con CI/CD propio + Terraform, son dos pipelines
compitiendo. S3 + CloudFront es más coherente y suma servicios visibles.
 
**ElastiCache / Redis (para almacenar resultados de escaneo).**
Dos objeciones:
- *Conceptual:* lo que se quiere guardar no es caché. Los resultados del escaneo son **datos durables** que
  deben sobrevivir, compararse contra el escaneo anterior y persistir semanas. En Redis serían una segunda
  fuente de verdad con un problema de sincronización. DynamoDB ya hace todo eso.
- *Costo y complejidad:* ElastiCache vive en una VPC. Meter las Lambdas en una VPC obliga a NAT Gateway
  (~$32/mes de piso + tráfico) para que puedan seguir saliendo a internet y llegar a Bedrock y DynamoDB.
  El clúster más pequeño son otros ~$12/mes corriendo 24/7. ElastiCache Serverless tiene un piso de varias
  decenas de dólares al mes. Esto **rompe frontalmente** el argumento con que se eligió DynamoDB sobre RDS
  ("pago por solicitud es más barato que una instancia 24/7"). Y en Terraform, VPC + subredes + NAT +
  endpoints es un día completo sin funcionalidad visible.
**EventBridge Bus.**
Hay que separar dos servicios que se llaman igual:
- **EventBridge Scheduler (cron)** — sí se usa, dispara el escaneo programado.
- **EventBridge Bus (enrutador de eventos)** — no. Un bus brilla con muchos productores y muchos
  consumidores que no se conocen. Aquí hay un productor y un consumidor: añade un salto, una regla de
  patrón que depurar, y un modo de falla nuevo ("¿por qué no matcheó?") a cambio de cero desacoplamiento.
  Más importante: **EventBridge Bus no da contrapresión.** SQS es un búfer que se drena al ritmo que uno
  decide, que es exactamente lo que se necesita para no reventar la cuota de Bedrock. EventBridge empuja
  a sus destinos. El patrón habitual en producción es EventBridge → **SQS** → Lambda: se acaba usando SQS
  de todas formas, más un componente extra.
**Step Functions.**
 
| | SQS + Lambda | Step Functions |
|---|---|---|
| Paralelismo | Automático, con concurrencia reservada | `Map` con `MaxConcurrency` |
| Reintentos | Automáticos + DLQ | Declarativos `Retry`/`Catch` |
| Estado del trabajo | **Se construye** (~15 líneas) | **Incluido** (`DescribeExecution`) |
| Visibilidad | Métricas y logs | Grafo visual en consola |
| Costo a esta escala | Cero (1M req/mes gratis) | Cero (4.000 transiciones/mes gratis) |
| Terraform | ~30 líneas | Definición ASL en JSON, más molesta de depurar |
| Curva de aprendizaje | Cero | Real: ASL, JSONPath, `ResultPath` |
 
Lo único que Step Functions ahorra es el seguimiento de progreso (~15 líneas). A cambio cuesta un día
depurando ASL — entre el 7% y el 10% del presupuesto total. El único argumento a favor es de
**presentación** (el grafo se ve más sofisticado en el video), no técnico, y el criterio (d) ya está
cubierto. *Se invertiría solo si alguien del equipo ya construyó máquinas de estado antes.*
 
**Secrets Manager / SSM Parameter Store.**
Greenhouse, Lever y RemoteOK no requieren autenticación. Sin API keys de terceros, el componente
desaparece de la arquitectura y del Terraform.
 
**`lxml`.**
Usar `html.parser` de BeautifulSoup. Sin binarios compilados en el zip, desaparece toda una clase de
errores de "funciona en mi máquina, falla en Lambda".
 
**Single-table design en DynamoDB.**
Es una optimización que no compra nada con 5 usuarios y cuesta horas de diseño de claves e índices. Además
el planteamiento original se contradecía: decía single-table y luego que empresas debía ir separado. Con
tablas separadas, Kiro también genera código más predecible.
 
**Imagen de contenedor para las Lambdas.**
Zip tiene arranque en frío más rápido, no necesita repositorio ECR ni build de Docker en el CI, y las
dependencias son pequeñas (FastAPI, Mangum, Pydantic, BeautifulSoup, boto3). Límite de 50 MB comprimido /
250 MB descomprimido — sobra.
 
---
 
## 5. Alcance del MVP
 
### Dentro
 
1. Auth con Cognito (usuarios pre-creados, Hosted UI)
2. Onboarding guiado de 4 pasos
3. Perfil: pegar CV → parseo con IA → editable
4. Sugerencia y selección de cargos objetivo
5. Descubrimiento en cascada (board API → JSON-LD → HTML+LLM)
6. **Scoring de match con explicación** ← diferenciador
7. Escaneo asíncrono con seguimiento de progreso
8. Ciclo de vida de vacantes con detección robusta de cierres
9. Vacante manual por texto pegado + link
10. CV-ATS en texto plano, descargable desde el navegador
11. Banco de preguntas y notas por vacante
12. Escaneo programado (EventBridge Scheduler) + correo (SES)
### Fuera
 
Ver §3 para el detalle y el razonamiento de cada corte. Resumen: CV-visual `.docx`, panel de admin con UI,
APIs públicas de empleo, filtro de idioma, pantalla de históricos, descarga automática de vacante por URL,
vista agregada de preguntas por empresa, BYOK, registro público, scraping con credenciales.
 
---
 
## 6. Modelo de datos (DynamoDB)
 
Seis tablas separadas.
 
### 6.1 `Empresas` (global, compartida)
 
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
 
La empresa **nunca se elimina**. Quitar ≠ borrar: quitar una empresa de la lista personal solo desactiva
la suscripción de ese usuario; la empresa sigue en el catálogo compartido y se puede reactivar sin perder
nada si se eliminó por error.
 
### 6.2 `Vacantes` (global, compartida)
 
| Campo | Tipo | Notas |
|---|---|---|
| `companyId` (**PK**) | S | |
| `vacancyId` (**SK**) | S | SHA-256 de la URL normalizada. Sin URL: hash de `companyId+titulo+ubicacion` normalizados |
| `titulo` | S | |
| `descripcion` | S | texto completo |
| `ubicacion` | S | |
| `modalidad` | S | `remoto` \| `presencial` \| `hibrido` \| `sin_dato` — **nunca adivinar** |
| `url` | S | link oficial. **Siempre se guarda**, para que el usuario abra la publicación original |
| `publishedAt` | S | si la fuente lo da |
| `origen` | S | `board_api` \| `json_ld` \| `html_llm` \| `manual` |
| `firstSeenAt` / `lastSeenAt` | S | |
| `missCount` | N | ver §8.3 |
| `estado` | S | `abierta` \| `cerrada` |
| `ttl` | N | epoch; solo se fija al cerrar y si nadie la aplicó |
 
> **La clave es la URL, no `empresa+cargo+ubicación`.** El título y la ubicación los produce un LLM y no
> son deterministas ("Bogotá" / "Bogotá, Colombia" / "Bogotá D.C."), lo que generaría duplicados, falsos
> "nueva", y correos con falsos positivos — justo en la funcionalidad más visible.
 
### 6.3 `UsuarioVacante` (por usuario)
 
| Campo | Tipo | Notas |
|---|---|---|
| `userId` (**PK**) | S | `sub` de Cognito |
| `sk` (**SK**) | S | `{companyId}#{vacancyId}` |
| `estado` | S | `nueva` \| `vista` \| `aplicada` \| `archivada` |
| `score` | N | 0–100 |
| `scoreDetalle` | M | ver §9.3 |
| `scoreProfileVersion` | N | versión del perfil con la que se calculó |
| `appliedAt` | S | |
| `cvAtsTexto` | S | texto plano del CV generado |
| `cvGeneratedAt` | S | |
| `updatedAt` | S | |
 
**Sin GSI, intencionalmente.** Se consulta por `userId` y se filtra/ordena en la Lambda. Con <500 items
por usuario es correcto y más barato. Revisar solo si el volumen crece un orden de magnitud.
 
### 6.4 `Entradas` (banco de preguntas y notas)
 
| Campo | Tipo | Notas |
|---|---|---|
| `pk` (**PK**) | S | `{userId}#{companyId}#{vacancyId}` |
| `entryId` (**SK**) | S | ULID (ordena cronológicamente por sí solo) |
| `tipo` | S | `preguntas` \| `nota_entrevista` |
| `contenido` | S / L | texto libre, o lista de `{pregunta, respuesta}` |
| `ronda` | N | opcional |
| `createdAt` | S | |
 
Lista **append-only**: soporta rondas sucesivas del proceso de selección sin rediseño.
 
> **Consecuencia asumida de la decisión "solo por vacante":** si el usuario aplica dos veces a la misma
> empresa en momentos distintos, el segundo proceso arranca en blanco. La decisión es **reversible barata**
> — agregar un GSI por empresa es aditivo, no rompe nada, y toma media hora.
 
### 6.5 `Perfiles` (por usuario)
 
| Campo | Tipo | Notas |
|---|---|---|
| `userId` (**PK**) | S | |
| `cvOriginalTexto` | S | lo que el usuario pegó |
| `perfilEstructurado` | M | ver abajo |
| `resumenParaMatching` | S | resumen condensado ≤500 palabras, generado una vez |
| `cargosSugeridos` | L | |
| `cargosActivos` | L | |
| `profileVersion` | N | **se incrementa en cada guardado de perfil o cargos** |
| `updatedAt` | S | |
 
`perfilEstructurado` tiene cuatro secciones:
- `experienciaLaboral[]` — con `proyectos[]` anidados dentro de cada empresa
- `proyectosPersonales[]`
- `formacionAcademica[]`
- `cursosCertificaciones[]`
> **Pregunta abierta del documento original, resuelta:** formación académica va **separada** de cursos y
> certificaciones. Un título universitario y una certificación corta son cosas distintas y los ATS las
> tratan distinto.
 
> `resumenParaMatching` existe para no meter el perfil completo en cada prompt de scoring. Se regenera
> solo cuando cambia `profileVersion`.
 
### 6.6 `Suscripciones` (usuario ↔ empresa)
 
| Campo | Tipo | Notas |
|---|---|---|
| `userId` (**PK**) | S | |
| `companyId` (**SK**) | S | |
| `activa` | BOOL | quitar ≠ borrar |
| `addedAt` | S | |
 
**GSI `porEmpresa`**: PK `companyId`, SK `userId`. Necesario para que el worker de scoring sepa a qué
usuarios puntuar cuando aparece una vacante nueva. Es la única consulta inversa del sistema.
 
### 6.7 `ScanJobs`
 
| Campo | Tipo | Notas |
|---|---|---|
| `jobId` (**PK**) | S | UUID |
| `userId` | S | null si es escaneo programado global |
| `status` | S | `RUNNING` \| `DONE` \| `PARCIAL` \| `FAILED` |
| `empresasTotal` | N | |
| `empresasCompletadas` | SS | **String Set** — ver §8.2 |
| `empresasOmitidas` | L | las que estaban dentro de la ventana de frescura |
| `empresasFallidas` | L | |
| `startedAt` | S | |
| `ttl` | N | 7 días |
 
---
 
## 7. Arquitectura AWS
 
```
                                    ┌──────────────────────────────┐
  Navegador ──> CloudFront ──> S3   │  frontend estático (Vite)    │
      │                             └──────────────────────────────┘
      │
      ├──> Cognito Hosted UI (Authorization Code + PKCE)
      │
      └──> API Gateway (Cognito Authorizer)
                 │
                 └──> Lambda "api"  (FastAPI + Mangum, monolítica)
                          │
                          ├──> DynamoDB
                          ├──> Bedrock  (llamadas cortas y síncronas)
                          └──> SQS scan ──┐
                                          │
  EventBridge Scheduler (cron) ──> Lambda "orquestador" ──> SQS scan
                                                              │
                                          ┌───────────────────┘
                                          ▼
                              Lambda "scan-worker"  (concurrencia reservada: 5)
                                          │
                                          ├──> DynamoDB (upsert vacantes)
                                          └──> SQS scoring
                                                   │
                                                   ▼
                                       Lambda "scoring-worker"  (concurrencia reservada: 3)
                                                   │
                                                   ├──> Bedrock
                                                   └──> DynamoDB
 
  Lambda "notificador" (al cerrar un job programado) ──> SES
```
 
**Por qué una sola Lambda para toda la API síncrona:** una sola función en Terraform en vez de ~18, y
FastAPI genera el OpenAPI gratis. Los workers asíncronos sí van como Lambdas separadas porque tienen
perfiles de concurrencia y timeout distintos.
 
**Por qué dos colas, no una:** escaneo y scoring tienen perfiles de concurrencia y dominios de falla
distintos. Si el scoring falla, no se debe reintentar la descarga de la página. Cuesta ~15 líneas más de
Terraform.
 
Cada cola con su **DLQ** (`maxReceiveCount: 3`).
 
**Por qué DynamoDB y no RDS:** a esta escala, serverless de pago por solicitud es más barato que mantener
una instancia 24/7, y encaja mejor con Lambda.
 
**Región `us-east-1` (N. Virginia):** más barata que São Paulo y con la disponibilidad de modelos de
Bedrock más amplia y madura. Costo aceptado conscientemente: más latencia para usuarios en Colombia, sin
problema para 5 usuarios internos.
 
---
 
## 8. Flujo de descubrimiento
 
### 8.1 Cascada de extracción (por empresa)
 
Se intenta en orden y se para en el primero que funcione:
 
1. **API de board pública** — si `plataforma` es `greenhouse` o `lever`, se llama su endpoint JSON. Sin
   autenticación, determinista, **cero tokens**.
2. **JSON-LD `JobPosting`** — buscar en el HTML el bloque `application/ld+json` con `@type: JobPosting`.
   Muchos sitios lo publican para Google Jobs. Parseo directo, **cero tokens**.
3. **HTML → LLM** — descargar, limpiar por código (quitar `<script>`, `<style>`, atributos de estilo,
   etiquetas vacías) **una sola vez por página**, y pasar el resultado a un modelo pequeño de Bedrock.
   Deduplicar después, por código.
> **Esto invirtió la decisión original de "no hacer parsers dedicados por plataforma de ATS".** La premisa
> era incorrecta: para Greenhouse y Lever **no hay parser que escribir**, son endpoints JSON públicos y
> documentados. Son *menos* código que el camino con IA, más rápidos, gratis y deterministas.
>
> Y el camino 3 falla con la mayoría de páginas de carreras modernas: Greenhouse y Lever se embeben por
> iframe o se pintan por JavaScript, Workday es una SPA que carga por XHR. Un `fetch` desde Lambda devuelve
> un cascarón vacío y el modelo extrae cero vacantes o alucina. La alternativa (headless Chromium en
> Lambda, ~250 MB de capa) es justo lo que no cabe en este plazo.
>
> Segundo problema del camino 3: una página de carreras limpia puede ser de 50k–200k tokens. "El volumen es
> bajo, no importa" es cierto para el costo pero no para el límite de contexto ni para la latencia.
 
**Semilla:** 8–10 empresas verificadas **a mano** antes de comprometerse. No asumir que el patrón de URL
funciona: Greenhouse tiene más de un dominio de board vigente y muchas empresas lo sirven bajo dominio
propio.
 
### 8.2 Escaneo asíncrono
 
```
POST /scans
  Lambda orquestador:
    1. resuelve las empresas activas del usuario (Suscripciones)
    2. filtra por VENTANA DE FRESCURA (§8.4)
    3. crea ScanJob { empresasTotal: N, empresasCompletadas: {} }
    4. publica N mensajes en SQS scan
    5. responde { jobId } de inmediato
 
SQS scan → Lambda scan-worker (UNA empresa por mensaje):
    1. ejecuta la cascada §8.1
    2. clasifica el resultado (§8.3)
    3. upsert de vacantes en DynamoDB
    4. encola las vacantes nuevas en SQS scoring
    5. ADD empresasCompletadas :companyId
 
GET /scans/{jobId}   ← polling del frontend; se detiene en DONE/PARCIAL/FAILED
```
 
**Por qué asíncrono:** API Gateway corta la integración a los ~29 segundos. Descargar 15 páginas + llamar
a Bedrock por cada una + deduplicar no cabe ahí ni de cerca. El planteamiento original describía el
escaneo manual como request-response, lo cual era un hueco arquitectónico, no un detalle.
 
> ⚠️ **Idempotencia.** SQS entrega *al menos una vez*. Un contador `pending -= 1` es incorrecto: si un
> mensaje se procesa dos veces, el job se marca completo antes de tiempo o el contador queda negativo. Por
> eso `empresasCompletadas` es un **String Set** y el worker hace `ADD`: agregar el mismo elemento dos
> veces no cambia el conjunto. El job está listo cuando `size(empresasCompletadas) == empresasTotal`.
>
> El upsert de vacantes ya es idempotente porque la clave es el hash de la URL.
 
> ⚠️ **Jobs zombis.** Si un mensaje agota reintentos y cae en la DLQ, el job nunca llega a `DONE` y el
> frontend hace polling para siempre. Regla: si `now - startedAt > 10 min`, pasa a `PARCIAL` con la lista
> de empresas no completadas.
 
### 8.3 Clasificación del resultado y cierre de vacantes
 
| Resultado | Condición | Acción |
|---|---|---|
| `OK` | respuesta válida, N > 0 vacantes | evaluar cierres normalmente |
| `FAILED` | timeout, HTTP 4xx/5xx, JSON inválido, excepción | **no tocar nada**, `consecutiveFailures += 1` |
| `EMPTY_SOSPECHOSO` | 0 vacantes pero `lastVacancyCount > 0` | **no tocar nada**, tratar como fallo |
| `EMPTY_LEGITIMO` | 0 vacantes y `lastVacancyCount == 0` | OK, la empresa no tiene vacantes |
 
> El caso `EMPTY_SOSPECHOSO` es el que evita el desastre: "el JavaScript no renderizó y recibí un cascarón
> con HTTP 200" es **indistinguible** de "la empresa cerró todas sus vacantes" si solo miras el conteo.
> Comparar contra el escaneo anterior las distingue.
 
**Cierre con margen** (solo tras un escaneo `OK`):
- No aparece → `missCount += 1`
- Reaparece → `missCount = 0`
- `missCount >= 2` → `estado = cerrada`, sale del listado activo. Si nunca se aplicó, `ttl` a 30 días. Si
  sí se aplicó, permanece indefinidamente en "Postulaciones hechas".
> **Por qué el margen:** la regla original ("si no aparece en el escaneo más reciente, está cerrada")
> significaba que un fallo de la fuente marcaba **todas** las vacantes de una empresa como cerradas de
> golpe, silenciosamente, arrancando su TTL de un mes.
 
**Las vacantes de `origen = manual` nunca se auto-cierran.** No tienen fuente que reescanear; la lógica de
`missCount` las cerraría en dos escaneos. Solo el usuario puede archivarlas.
 
**Superficie de errores en la UI (obligatoria).** Con `consecutiveFailures >= 3`, la vista de fuentes
muestra: *"No hemos podido revisar Empresa X desde el 20 de julio"*, con botones de reintentar y desactivar.
**Sin esto, todo el diseño anterior es invisible y el usuario no puede confiar en el listado.**
 
### 8.4 Ventana de frescura (reemplazó al contador diario)
 
No hay contador de ejecuciones por usuario. Cada empresa tiene `lastScannedAt` y se omite si fue escaneada
recientemente:
 
| Tipo de fuente | Ventana |
|---|---|
| `board_api` / `json_ld` (cero tokens) | 1 hora |
| `html_llm` (caro) | 12 horas |
 
**Razón del cambio.** Con la cascada de §8.1, la mayoría de escaneos ya no consumen tokens. El gasto real
quedó así:
 
| Operación | Costo en tokens |
|---|---|
| Escanear vía API de board | **Cero** |
| Escanear vía JSON-LD | **Cero** |
| Escanear vía HTML→LLM | Alto (decenas de miles) |
| **Scoring por (usuario, vacante)** | **Medio, multiplicado por usuarios** |
 
Un contador por usuario controlaba la unidad equivocada (un usuario con 40 empresas y 2 escaneos gasta 8x
uno con 5 empresas y 4 escaneos), y además era incoherente con vacantes globales: el escaneo manual del
usuario A refresca los datos del usuario B gratis.
 
> ⚠️ **UX crítica.** Si el escaneo programado corrió a las 7am y el usuario dispara uno manual a las 9am,
> no habrá nada que escanear. La UI **no puede** mostrar un spinner que termina sin cambios. Debe decir:
> *"Tus 12 empresas están al día — última revisión hace 2 horas"*, con la lista y sus timestamps. Un
> resultado vacío tiene que verse como éxito, no como fallo.
 
### 8.5 Vacante manual
 
El usuario **pega el texto** de la descripción y, aparte, **pega el link**. El link se guarda pero **nunca
se descarga ni se escanea** — existe solo para que el usuario abra la publicación oficial. *(Esto aplica a
todas las vacantes: el campo `url` siempre se conserva con ese propósito.)*
 
**Por qué pegar texto y no descargar la URL:**
- Es coherente con cómo se maneja el CV (pegar, no subir).
- Funciona con LinkedIn, Computrabajo y cualquier portal **sin tocar sus ToS**: el usuario copia
  manualmente lo que ya está viendo.
- No puede fallar por JavaScript ni bloqueos de bot. **En la demo funciona siempre.**
- Descargar una página de vacante individual metería el camino HTML→LLM en la ruta crítica del MVP, que es
  justo el camino frágil.
Si la empresa no existe en el catálogo, se crea con lo mínimo (`nombre`, `plataforma: manual`) pero **el
usuario no queda suscrito** a ella, porque no hay `careersUrl` escaneable.
 
---
 
## 9. Scoring de match (diferenciador principal)
 
Al dejar el banco de preguntas como privado por usuario y por vacante, **este módulo carga el peso del
criterio de Innovación (30%)**. Debe ser lo primero que se ve en el video y la explicación tiene que ser
específica. Un "78%" sin desglose es un número inventado; con desglose contra el CV, es un producto.
 
### 9.1 Prefiltro por código (antes de gastar tokens)
 
No mandar las 40 vacantes de una empresa al modelo. Primero, comparación normalizada del título de la
vacante contra los cargos activos (minúsculas, sin tildes, solapamiento de tokens significativos). Solo lo
que pasa el prefiltro va a scoring. Reduce el gasto un orden de magnitud.
 
> El problema que resuelve: el scoring es **inherentemente por usuario** y no se puede compartir. Si una
> empresa publica 40 vacantes y 5 usuarios la siguen, son 200 evaluaciones. El ahorro de la extracción
> global (§6.2) no aplica aquí.
 
### 9.2 Cuándo se calcula
 
- **Una vez** por par (usuario, vacante), guardado en `UsuarioVacante`.
- Nunca al cargar una pantalla.
- Siempre desde la cola `scoring`, nunca dentro de una petición HTTP.
### 9.3 Formato de salida
 
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
 
### 9.4 Rescoring cuando cambia el perfil (híbrido)
 
1. Al guardar perfil o cargos, `profileVersion += 1`. **No se recalcula nada en ese momento.**
2. Al cargar el listado, el backend detecta los scores con `scoreProfileVersion` desfasado.
3. Los encola en `scoring` y **responde de inmediato** con los scores viejos marcados con badge
   *"actualizando…"*.
4. El frontend refresca a los pocos segundos.
**Por qué híbrido y no "bajo demanda" puro:** si "bajo demanda" significara llamar a Bedrock cuando el
usuario abre el detalle, serían 2–5 segundos de espera cada vez que el jurado abre una tarjeta en el video.
 
> Detalle: si el listado se ordena por score, congelar el orden hasta que el lote termine, o cambia bajo
> los pies del usuario.
 
---
 
## 10. Contratos de API
 
Todo detrás del Cognito Authorizer. `userId` sale siempre del JWT, **nunca** del body.
 
| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/me/profile/parse` | pega CV → perfil estructurado (no guarda) |
| `GET` | `/me/profile` | |
| `PUT` | `/me/profile` | guarda perfil, incrementa `profileVersion` |
| `POST` | `/me/roles/suggest` | sugiere cargos desde el perfil |
| `PUT` | `/me/roles` | fija `cargosActivos`, incrementa `profileVersion` |
| `GET` | `/companies` | catálogo compartido |
| `POST` | `/companies` | agrega empresa por URL de carreras; detecta plataforma |
| `GET` | `/me/companies` | suscripciones con estado y `lastScanStatus` |
| `PUT` | `/me/companies/{companyId}` | activar / desactivar |
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
 
### Contrato de tipos
 
1. **Modelos Pydantic en un paquete compartido** (`backend/shared/models.py`), importados por todas las
   Lambdas. Fuente única de verdad de qué es una `Vacante`, un `Perfil`, un `ScanJob`.
2. **FastAPI genera el OpenAPI automáticamente.**
3. **Tipos de TypeScript generados desde ese OpenAPI** con `openapi-typescript`.
> ~1 hora de setup, y es la decisión de tooling con mejor retorno del proyecto: con dos personas en
> paralelo en front y back, el frontend nunca se desincroniza del backend.
 
---
 
## 11. Tareas de Bedrock
 
Región `us-east-1`. **Todas las salidas se validan con Pydantic, con un reintento si el parseo falla.**
Nunca `json.loads()` directo sobre la respuesta de un modelo.
 
| Tarea | Tamaño de modelo | Entrada | Salida |
|---|---|---|---|
| Parsear CV pegado | pequeño | texto del CV | `PerfilEstructurado` |
| Generar `resumenParaMatching` | pequeño | perfil estructurado | texto ≤500 palabras |
| Sugerir cargos | pequeño | `resumenParaMatching` | `string[]` |
| Extraer vacantes de HTML limpio | pequeño | HTML limpio | `Vacante[]` |
| Extraer vacante de texto pegado | pequeño | texto | `Vacante` |
| **Scoring de match** | pequeño/intermedio | `resumenParaMatching` + vacante + cargos activos | objeto §9.3 |
| Redactar CV-ATS | intermedio | perfil completo + vacante | texto plano |
| Apoyo para responder preguntas | intermedio | pregunta + `resumenParaMatching` + vacante | texto |
 
**Principio de arquitectura:** la IA genera **solo contenido (texto/JSON)**. Nunca renderizado visual,
nunca código que se ejecute.
 
**Idioma:** el CV-ATS y las respuestas de entrevista se generan **en el idioma de la vacante**, no siempre
en español.
 
---
 
## 12. Frontend
 
### 12.1 Onboarding (4 pasos)
 
1. Pegar CV → parseo → confirmar/editar perfil
2. Confirmar cargos sugeridos + agregar propios
3. Elegir empresas del catálogo semilla
4. Primer escaneo con barra de progreso
> Es la experiencia entera del jurado en su primer minuto. Si aterrizan en un dashboard vacío, la
> evaluación arranca mal.
 
### 12.2 Listado principal
 
Tarjeta, en este orden:
- Fecha de publicación (pequeña, izquierda) + ✓ si ya se aplicó
- **Badge de score con color** ← lo más visible de la pantalla
- Cargo (título principal)
- Empresa (subtítulo)
- Lugar / modalidad (subtítulo)
### 12.3 Detalle de vacante
 
Descripción completa + desglose del score (coincidencias / faltantes / resumen) + **link a la publicación
oficial** + botón "Presentarse".
 
Al presionar "Presentarse", **en la misma vista, sin navegar**: aparece el link listo para copiar y tres
acciones — "Generar hoja de vida" / "Guardar preguntas" / "Guardar" (marca como aplicada sin generar nada).
 
### 12.4 Postulaciones hechas → detalle
 
Mismo componente visual que el listado principal, sin el check (redundante ahí). Al entrar al detalle, en
este orden:
 
1. Descripción de la vacante + link oficial
2. Entradas guardadas (preguntas y notas), cronológicas
3. CV-ATS generado — con botón **copiar** y botón **descargar**
4. Botón "Continuar proceso" → agrega una entrada nueva (rondas posteriores)
### 12.5 Fuentes
 
Catálogo compartido + suscripciones propias, con `lastScannedAt` y **avisos de fuentes fallando** (§8.3).
La lista de fuentes activas debe ser transparente: el usuario ve qué se está escaneando.
 
### 12.6 Descarga del CV — en el navegador, no en el backend
 
El CV-ATS vive como **texto en DynamoDB** (5–10 KB, lejos del límite de 400 KB por item). La descarga se
construye en el cliente con un `Blob` y un enlace: cero llamadas al backend, cero Lambda, instantáneo. Se
elimina S3 del camino crítico y con él las presigned URLs y su IAM.
 
En pantalla: el texto renderizado con botón de **copiar** (lo que más se usa en la práctica, porque el
usuario lo pega en el formulario del portal) y botón de **descargar `.md`/`.txt`**.
 
*Opcional si sobra tiempo:* generar `.docx` desde el navegador con una librería JS (~2 horas), porque
muchos portales no aceptan `.txt`. Sigue sin tocar el backend.
 
---
 
## 13. Infraestructura
 
### 13.1 Terraform
 
- **Un solo ambiente.** Una sola persona aplica.
- **Estado en S3 con versionado.** Bucket creado a mano por consola (2 minutos). **No** hace falta tabla
  de bloqueo si solo una persona aplica.
  > El estado local es un riesgo catastrófico: si ese portátil falla o el archivo se corrompe a mitad de
  > un `apply`, quedan sin capacidad de gestionar la infraestructura y hay que importar todo a mano en la
  > última semana. Cinco minutos eliminan el riesgo.
- **Bus factor:** el segundo desarrollador debe tener acceso al bucket y saber correr `terraform apply`.
- **Retención de log groups de CloudWatch: 7 días.** Por defecto nunca expiran.
- Alarmas de facturación en CloudWatch.
- IAM con permisos mínimos por función (menor privilegio).
### 13.2 CI/CD (GitHub Actions)
 
- Autenticación a AWS por **OIDC con rol asumido**. Nunca claves de larga vida en secretos del repo.
- Build del frontend → sync a S3 → **invalidación de CloudFront**.
- Build de los zips de Python → subida a S3 → `terraform apply` (referencia por `s3_key` +
  `source_code_hash`).
Empaquetado: `pip install --platform manylinux2014_x86_64 --only-binary=:all: --target ./package`.
 
### 13.3 CloudFront + SPA
 
Configurar respuestas de error personalizadas: **403 y 404 → `/index.html` con código 200**. Sin esto,
cualquier ruta profunda da error al recargar.
 
### 13.4 Cognito
 
- Usuarios creados con `AdminCreateUser`. Sin auto-registro, sin recuperación self-service —
  **decisión permanente**, no un parche para el hackathon.
- Para el hackathon: 5 usuarios (2 desarrolladores + 3 jurados). El modelo permite agregar usuarios
  manualmente después sin rediseñar.
- **Hosted UI** con Authorization Code + PKCE. No construir UI de login propia.
- Callback URLs en Terraform. Decidir dónde vive el token (memoria vs. localStorage).
- Deshabilitar jurados post-hackathon con `AdminDisableUser`.
### 13.5 SES
 
- **Se opera en sandbox.** Verificar las 5 direcciones (cada dueño recibe un link y hace clic). 200
  correos/día, 1 msg/seg. Costo cero, conserva el argumento "AWS-nativo".
- Correo **solo en escaneos automáticos/programados**, nunca en manuales.
- ⚠️ **Los 3 jurados tienen que hacer clic en un link de verificación** antes de recibir cualquier correo.
  Si no se puede coordinar, la notificación se demuestra con capturas, no en vivo.
- Pedir acceso de producción como respaldo: suele aprobarse en ~24h pero **no está garantizado** y a
  cuentas nuevas con respuestas vagas las rechazan seguido.
- **No autoalojar servidores de correo** (Postfix, Mailu, Mailcow): AWS bloquea el puerto 25 saliente por
  defecto, y reputación de IP + SPF + DKIM + DMARC son días de trabajo para un resultado peor.
### 13.6 Seguridad
 
- Sin registro público → sin superficie de abuso externo de tokens de IA.
- IAM de menor privilegio por función Lambda.
- Concurrencia reservada en workers como control de costo y de cuota.
### 13.7 Estructura del repo
 
```
/infra          terraform
/backend        python  (api/, workers/, shared/)
/frontend       vite + react + ts
/scripts        seed de datos de demo, creación de usuarios
```
 
---
 
## 14. Tests y datos de demo
 
### Tests: solo funciones puras
 
Con 1–2 semanas, una suite completa con mocks de AWS cuesta un día que no existe. Cubrir:
- generación de la clave de deduplicación (normalización de URL)
- limpieza de HTML
- detección de plataforma desde una URL
- prefiltro de cargos
- lógica de `missCount` y clasificación de resultado de escaneo
> Decirlo explícitamente en el prompt de Kiro, o generará una suite completa con mocks.
 
### Datos de demo
 
Script de seed que deje un usuario con perfil cargado, 3 empresas y ~20 vacantes ya escaneadas **y
scoreadas**. Sin esto, el video son 4 minutos de spinners. **Planearlo desde el día 1, no la última noche.**
 
---
 
## 15. Bloqueos con latencia externa
 
Resolver **antes** de escribir código. No dependen del equipo.
 
- [ ] Solicitar acceso a modelos en Bedrock (`us-east-1`), consola → Model Access
- [ ] Verificar los IDs exactos de modelo / inference profiles
- [ ] Verificar las direcciones de correo de los 5 usuarios en SES
- [ ] Solicitar acceso de producción de SES (respaldo)
- [ ] Verificar a mano los endpoints de board de las 8–10 empresas semilla
- [ ] Crear el bucket S3 del estado de Terraform
- [ ] Configurar el rol OIDC para GitHub Actions
---
 
## 16. Plan de construcción
 
| Días | Entregable |
|---|---|
| 1 | Bloqueos de §15, Terraform base (Cognito, DynamoDB, S3, CloudFront), CI/CD mínimo |
| 2 | Lambda `api` con FastAPI + Mangum, auth extremo a extremo, tipos TS generados |
| 3 | Perfil: parseo de CV, edición, cargos sugeridos |
| 4 | Cascada de descubrimiento, empresas semilla, catálogo |
| 5 | SQS + orquestador + scan-worker, ScanJobs con progreso |
| 6 | Scoring (prefiltro + cola + prompt + persistencia) |
| 7 | Listado, detalle, "Presentarse", estados |
| 8 | CV-ATS + banco de preguntas y notas + vacante manual |
| 9 | Onboarding, avisos de fuentes fallando, EventBridge + SES, seed de demo |
| 10 | README, video, colchón |
 
**Primer sacrificable si el día 8 no está el flujo completo:** Terraform + CI/CD. Ninguno está en la
rúbrica, cuestan 15–20 horas y suman cero puntos directos. Desplegar con un script de `aws cli` y dejar el
Terraform parcial en el repo es infinitamente mejor que una demo incompleta.
 
**Reparto entre los dos: corte vertical, no horizontal.** Uno toma infra + auth + escaneo + datos; el otro
toma frontend + los flujos de IA. Si ambos tocan todo, se bloquean mutuamente.
 
---
 
## 17. Registro de decisiones invertidas (con argumento)
 
| Decisión original | Cambió a | Argumento |
|---|---|---|
| Backend Java + Python | **Python únicamente** | Ninguna tarea requería Java; dos runtimes = dos pipelines y modelos duplicados; cold starts de segundos con tráfico esporádico |
| Next.js con SSR | **React + Vite + TS** | App 100% detrás de auth, sin SEO ni contenido público. SSR no aporta nada |
| Amplify Hosting | **S3 + CloudFront** | Su valor es hacer el CI/CD por ti; choca con CI/CD propio + Terraform |
| Redis para resultados de escaneo | **SQS + DynamoDB** | Los datos son durables, no caché; obliga a VPC + NAT (~$44/mes de piso) y contradice el argumento de DynamoDB sobre RDS |
| EventBridge Bus como orquestador | **SQS** (Scheduler sí se queda) | Un productor y un consumidor no justifican un bus; y un bus no da contrapresión contra la cuota de Bedrock |
| Escaneo síncrono | **SQS fan-out + polling de `jobId`** | No cabía en el límite de ~29s de API Gateway |
| HTML+LLM como método principal | **Cascada: board API → JSON-LD → HTML+LLM** | Greenhouse/Lever son JSON públicos: *menos* código que la IA y más confiables. El HTML crudo falla con páginas renderizadas por JS |
| Clave de dedup = empresa+cargo+ubicación | **Hash de la URL** | Título y ubicación los produce un LLM y no son deterministas |
| Vacante como dato por usuario | **Vacante global + relación por usuario** | Evita pagar la extracción N veces y las inconsistencias entre usuarios |
| Contador diario de escaneos por usuario | **Ventana de frescura por empresa** | Controlaba la unidad equivocada (escaneos, no páginas) y era incoherente con vacantes globales |
| Cierre por ausencia en un escaneo | **`missCount >= 2` + clasificación del resultado** | Un fallo de la fuente cerraba silenciosamente todas las vacantes de una empresa |
| Single-table design | **Tablas separadas** | Optimización que no compra nada con 5 usuarios y cuesta horas de diseño de claves |
| CV-visual `.docx` con marca | **Fuera de alcance** | Varios días para algo cosmético que el propio análisis admite que puede romper ATS |
| Panel de administración con UI | **Consola/CLI de AWS** | Módulo completo, cero valor demostrable |
| Descargar vacante suelta desde URL | **Pegar texto + guardar link** | Metería el camino frágil en la ruta crítica; pegar texto no viola ToS y nunca falla en demo |
| Banco de preguntas como diferenciador | **Scoring de match como diferenciador** | Al quedar privado por usuario y por vacante, el banco es una libreta con IA; no es defendible como innovación |
| APIs públicas de empleo en el MVP | **Fuera de alcance** | Cada una es registro + key + esquema + mapeo. Solo RemoteOK si sobra tiempo |
 
---
 
## 18. Preguntas abiertas
 
1. **Lista concreta de empresas semilla.** Falta definirla y verificar a mano cada endpoint de board.
   Sugerido: investigar empleadores tech conocidos en Colombia/LatAm que usen Greenhouse o Lever.
2. **Confiabilidad del campo `modalidad`** cuando la fuente no lo menciona. Regla acordada: dejar
   `sin_dato`, nunca adivinar. Falta ver si en la práctica queda demasiado vacío para ser útil.
3. **Umbral del prefiltro de cargos** (§9.1): cuántos tokens de solapamiento se exigen. Ajustar con datos
   reales, no a priori.
4. **Valor concreto de las ventanas de frescura** (1h / 12h son propuestas, no medidas).
5. **Dónde vive el token de Cognito** en el frontend: memoria vs. localStorage.
6. **Undo de "Presentarse".** No hay forma de deshacer si el usuario se equivoca. Hueco menor de UX sin
   resolver.
7. **Generación de `.docx` en el navegador** — opcional, decidir según tiempo restante (§12.6).
---
 
## 19. Trampas técnicas conocidas
 
Lista de cosas que rompen silenciosamente. Repasar antes de cada módulo.
 
| Trampa | Detalle |
|---|---|
| **IDs de modelo de Bedrock** | Varios modelos actuales solo se invocan vía *inference profiles* entre regiones (ID con prefijo `us.`), no con el ID base. Falla con un error poco descriptivo. Verificar en consola |
| **Acceso a modelos de Bedrock** | Se solicita manualmente por región. No es automático ni instantáneo |
| **Cuota de Bedrock** | Cuentas nuevas tienen cuotas bajas de tokens por minuto. Sin concurrencia reservada en los workers, la demo se cae en vivo |
| **Visibility timeout de SQS** | Debe ser **mayor que el timeout de la Lambda** (regla: 6×). Si no, SQS re-entrega mientras el worker trabaja y se procesa todo por duplicado |
| **SQS entrega al menos una vez** | Los workers deben ser idempotentes. Usar String Set con `ADD`, no contadores |
| **TTL de DynamoDB** | No borra en el momento: típicamente dentro de 48 horas del vencimiento. "1 mes" es aproximado |
| **CloudFront + SPA** | 403/404 deben mapearse a `/index.html` con código 200, o las rutas profundas fallan al recargar |
| **Primer login de Cognito** | `AdminCreateUser` fuerza `NEW_PASSWORD_REQUIRED`. Sin recuperación self-service, un jurado que se atore queda bloqueado **durante la evaluación**. Probar el flujo antes de crear usuarios jurado |
| **SES sandbox** | Solo destinatarios verificados. Cada jurado debe hacer clic en un link |
| **Puerto 25 saliente** | Bloqueado por defecto en AWS. No intentar autoalojar correo |
| **Log groups de CloudWatch** | Por defecto nunca expiran. Fijar retención en Terraform |
| **Dominios de board de Greenhouse** | Hay más de uno vigente, y muchas empresas lo sirven bajo dominio propio. Verificar a mano |
| **Páginas de carreras con JS** | Un `fetch` devuelve un cascarón vacío con HTTP 200. De ahí la necesidad de `EMPTY_SOSPECHOSO` |
| **`lxml` en Lambda** | Binario compilado, problemas de plataforma. Usar `html.parser` |
| **Salida de LLM sin validar** | Nunca `json.loads()` directo. Validar con Pydantic y reintentar |
 
---
 
## 20. Conversaciones pendientes
 
Temas que conviene abordar cada uno en su propia conversación, usando este documento como base:
 
1. **Prompts del backend** — redacción concreta de los 8 prompts de §11, con sus esquemas Pydantic de
   entrada y salida, y estrategia de reintento ante fallo de validación.
2. **Prompt maestro para Kiro** — cómo trocear este documento en instrucciones que Kiro pueda ejecutar sin
   perder las trampas de §19 (las que más probablemente genere mal: la idempotencia del `ScanJob` y la
   clasificación `EMPTY_SOSPECHOSO`).
3. **Terraform** — estructura de módulos, orden de creación, variables.
4. **Diseño del frontend** — sistema visual, componentes, estados de carga y de error.
5. **Empresas semilla** — investigación y verificación de endpoints.
6. **README** — estructura, diagrama de arquitectura, sección de roadmap (alimentada por §3).
7. **Guion del video de 5 minutos** — qué se muestra, en qué orden, y qué se deja fuera.
### Nota sobre cómo se ha trabajado este proyecto
 
Las decisiones de este documento salieron de rondas de crítica explícita, no de acuerdo automático. Varias
conclusiones iniciales se invirtieron (§17) tras cuestionar sus premisas. **Conviene mantener ese modo de
trabajo en las conversaciones siguientes:** cuestionar suposiciones, verificar el razonamiento, proponer
alternativas y priorizar exactitud sobre aprobación.