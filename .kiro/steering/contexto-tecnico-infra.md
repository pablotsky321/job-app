---
inclusion: manual
---

# Contexto técnico — Terraform / Infraestructura

> Recorte autosuficiente de contexto_maestro_job_search.md para la spec de terraform.
> No requiere leer contexto-tecnico-backend.md ni contexto-tecnico-frontend.md.

## Qué recursos AWS provisiona esta spec

- Cognito (User Pool + Hosted UI + App Client)
- DynamoDB: seis tablas separadas (ver esquema abajo)
- API Gateway con Cognito Authorizer, integración proxy a una sola Lambda
- Lambda "api" (FastAPI + Mangum) + Lambdas de workers (orquestador, scan-worker, scoring-worker, notificador)
- SQS: dos colas (scan, scoring), cada una con su propia DLQ
- EventBridge Scheduler (cron del escaneo programado)
- SES (sandbox)
- S3 + CloudFront (frontend estático)
- IAM: roles y policies de mínimo privilegio por función Lambda
- CloudWatch: log groups con retención + alarmas de facturación

## Esquema de tablas DynamoDB (para definir claves e índices en Terraform)

### `Empresas` — PK `companyId` (S). Sin SK. Sin GSI.
### `Vacantes` — PK `companyId` (S), SK `vacancyId` (S). Sin GSI.
### `UsuarioVacante` — PK `userId` (S), SK `sk` (S, formato `{companyId}#{vacancyId}`). Sin GSI (deliberado).
### `Entradas` — PK `pk` (S, formato `{userId}#{companyId}#{vacancyId}`), SK `entryId` (S, ULID). Sin GSI.
### `Perfiles` — PK `userId` (S). Sin SK. Sin GSI.
### `Suscripciones` — PK `userId` (S), SK `companyId` (S). GSI `porEmpresa`: PK `companyId`, SK `userId`.
### `ScanJobs` — PK `jobId` (S). Sin SK. TTL en el campo `ttl` (7 días). Sin GSI.

Ningún single-table design: tablas separadas por decisión explícita (ver `decisiones-invertidas.md`).
Todas usan facturación por solicitud (on-demand), no capacidad aprovisionada.

## Arquitectura de cómputo y mensajería

API Gateway (Cognito Authorizer)
└──> Lambda "api" (FastAPI + Mangum, monolítica)
├──> DynamoDB
├──> Bedrock
└──> SQS scan ──┐
│
EventBridge Scheduler ──> Lambda "orquestador" ──> SQS scan
│
┌───────────────────────┘
▼
Lambda "scan-worker" (concurrencia reservada: 5)
│
├──> DynamoDB
└──> SQS scoring
│
▼
Lambda "scoring-worker" (concurrencia reservada: 3)
│
├──> Bedrock
└──> DynamoDB

Lambda "notificador" ──> SES


Una sola Lambda para toda la API síncrona (menos recursos en Terraform). Workers separados por
tener perfiles de concurrencia y timeout distintos. Cada cola SQS con su propia DLQ
(`maxReceiveCount: 3`). **Visibility timeout de cada cola = 6× el timeout de la Lambda consumidora**
(sin esto, SQS re-entrega mientras el worker sigue trabajando).

Región `us-east-1` (N. Virginia) — más barata que São Paulo y con mejor disponibilidad de modelos
de Bedrock. Costo aceptado: más latencia para usuarios en Colombia.

## Terraform

- **Un solo ambiente.** Una sola persona aplica los cambios.
- **Estado en S3 con versionado.** Bucket creado a mano por consola. No hace falta tabla de bloqueo
  si solo una persona aplica.
- **Bus factor:** el segundo desarrollador debe tener acceso al bucket y saber correr `terraform apply`.
- **Retención de log groups de CloudWatch: 7 días** (por defecto AWS nunca expira).
- Alarmas de facturación en CloudWatch.
- IAM con permisos mínimos por función. La tabla exacta de permisos por Lambda la produce la spec
  de backend en su `design.md` — referenciarla ahí en vez de reinventarla aquí.

## CI/CD (GitHub Actions)

- Autenticación a AWS por **OIDC con rol asumido**. Nunca claves de larga vida en secretos del repo.
- Build del frontend → sync a S3 → invalidación de CloudFront.
- Build de los zips de Python → subida a S3 → `terraform apply` (referencia por `s3_key` +
  `source_code_hash`).
- Empaquetado: `pip install --platform manylinux2014_x86_64 --only-binary=:all: --target ./package`.
- Empaquetado Lambda: **zip**, no contenedor/Docker/ECR.

## CloudFront + SPA

Respuestas de error personalizadas: **403 y 404 → `/index.html` con código 200**. Sin esto,
cualquier ruta profunda del frontend da error al recargar.

## Cognito

- Usuarios creados con `AdminCreateUser`. Sin auto-registro, sin recuperación self-service —
  decisión permanente, no parche del hackathon.
- Para el hackathon: 5 usuarios (2 desarrolladores + 3 jurados).
- Hosted UI con Authorization Code + PKCE.
- Callback URLs configuradas en Terraform.
- Deshabilitar jurados post-hackathon con `AdminDisableUser`.

## SES

- Se opera en sandbox: verificar las 5 direcciones (cada dueño recibe un link y hace clic).
  200 correos/día, 1 msg/seg.
- Solicitar acceso de producción como respaldo (suele aprobarse en ~24h, no garantizado).
- No autoalojar servidores de correo: AWS bloquea el puerto 25 saliente por defecto.

## Seguridad

- Sin registro público → sin superficie de abuso externo de tokens de IA.
- IAM de menor privilegio por función Lambda.
- Concurrencia reservada en workers como control de costo y de cuota de Bedrock.

## Estructura del repo (referencia, no genera esta spec)