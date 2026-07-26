---
inclusion: auto
name: decisiones-invertidas
description: >
  Alternativas de arquitectura ya evaluadas y descartadas con argumento explícito.
  Consultar antes de proponer un cambio de lenguaje, servicio de AWS, patrón de datos,
  o herramienta de infraestructura — para no re-litigar algo ya resuelto.
---

# Decisiones invertidas — no proponer estas alternativas de nuevo

| Se descartó | A favor de | Por qué |
|---|---|---|
| Backend Java + Python | Python únicamente | Ninguna tarea requería Java; dos runtimes = dos pipelines y modelos duplicados; cold starts de segundos con tráfico esporádico |
| Next.js con SSR | React + Vite + TS | App 100% detrás de auth, sin SEO ni contenido público. SSR no aporta nada |
| Amplify Hosting | S3 + CloudFront | Su valor es hacer el CI/CD por ti; choca con CI/CD propio + Terraform |
| Redis/ElastiCache para resultados de escaneo | SQS + DynamoDB | Los datos son durables, no caché; obliga a VPC + NAT (~$44/mes de piso) |
| EventBridge Bus como orquestador | SQS (Scheduler sí se queda) | Un productor y un consumidor no justifican un bus; un bus no da contrapresión contra la cuota de Bedrock |
| Escaneo síncrono request-response | SQS fan-out + polling de jobId | No cabía en el límite de ~29s de API Gateway |
| HTML+LLM como método principal de extracción | Cascada: board API → JSON-LD → HTML+LLM | Greenhouse/Lever son JSON públicos: menos código que la IA, más confiables. El HTML crudo falla con páginas renderizadas por JS |
| Clave de dedup = empresa+cargo+ubicación | Hash de la URL normalizada | Título y ubicación los produce un LLM y no son deterministas |
| Vacante como dato por usuario | Vacante global + relación por usuario | Evita pagar la extracción N veces y las inconsistencias entre usuarios |
| Contador diario de escaneos por usuario | Ventana de frescura por empresa (1h/12h) | Controlaba la unidad equivocada; incoherente con vacantes globales |
| Cierre por ausencia en un solo escaneo | missCount >= 2 + clasificación del resultado | Un fallo de la fuente cerraba silenciosamente todas las vacantes de una empresa |
| Single-table design en DynamoDB | Tablas separadas | Optimización que no compra nada con 5 usuarios y cuesta horas de diseño de claves |
| Step Functions | SQS + Lambda | Único ahorro real es ~15 líneas de seguimiento de progreso; cuesta un día de ASL |
| Descargar vacante suelta desde URL | Pegar texto + guardar link | Metería el camino frágil (HTML→LLM) en la ruta crítica; pegar texto no viola ToS y nunca falla en demo |
| Banco de preguntas como diferenciador | Scoring de match como diferenciador | Al quedar privado por usuario y por vacante, el banco es solo una libreta con IA |