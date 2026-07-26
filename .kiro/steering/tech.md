---
inclusion: always
---

# Stack cerrado — no proponer alternativas

- Python 3.12 únicamente. FastAPI + Mangum en una Lambda monolítica para la API síncrona.
- Lambdas separadas para workers asíncronos (orquestador, scan-worker, scoring-worker, notificador).
- DynamoDB con TABLAS SEPARADAS. Prohibido single-table design.
- SQS (dos colas: scan y scoring), cada una con su propia DLQ (maxReceiveCount: 3).
- Amazon Bedrock, región us-east-1, vía boto3.
- Frontend: React + Vite + TypeScript (SPA estática, sin SSR).
- Hosting frontend: S3 + CloudFront.
- Infra: Terraform, un solo ambiente, estado en S3 con versionado.
- CI/CD: GitHub Actions con OIDC (rol asumido), sin claves de larga vida.
- Empaquetado Lambda: zip. Prohibido contenedor/Docker/ECR.
- boto3, Pydantic v2, BeautifulSoup con html.parser. PROHIBIDO lxml (binario compilado, falla en Lambda).

# Reglas invariantes (violarlas es un bug, no una preferencia)

1. IDs de modelo de Bedrock NUNCA hardcodeados. Se leen de variables de entorno
   (BEDROCK_MODEL_SMALL, BEDROCK_MODEL_MID) en un único módulo backend/shared/bedrock.py.
2. Toda salida de un LLM se valida con un modelo Pydantic. Prohibido json.loads() directo
   sobre la respuesta de un modelo. Ante fallo de validación: un reintento con el error
   inyectado en el prompt, luego error controlado.
3. Los workers de SQS deben ser IDEMPOTENTES (SQS entrega al menos una vez). El progreso
   de un ScanJob se lleva con un String Set y operación ADD, nunca con un contador decreciente.
4. userId SIEMPRE se extrae del JWT del authorizer de Cognito
   (event.requestContext.authorizer.claims.sub). Nunca se acepta desde el body o query params.
5. Los modelos de dominio viven en backend/shared/models.py y son la única fuente de verdad.
   Ninguna Lambda redefine un modelo por su cuenta.
6. La IA genera solo texto o JSON estructurado. Nunca renderizado visual, nunca código
   que se ejecute.
7. Sin secretos ni API keys de terceros en el código: las fuentes usadas (Greenhouse,
   Lever, RemoteOK) no requieren autenticación.
8. Logging estructurado en JSON a stdout. Nunca loguear el texto del CV ni contenido de perfil.
9. Visibility timeout de cada cola SQS = 6× el timeout de la Lambda consumidora.
10. Retención de log groups de CloudWatch: 7 días (por defecto AWS no expira nunca).