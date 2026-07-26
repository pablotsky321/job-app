---
inclusion: always
---

# Stack cerrado — no proponer alternativas

- Python 3.12 únicamente. FastAPI + Mangum en una Lambda monolítica para la API síncrona.
- Lambdas separadas para workers asíncronos (orquestador, scan-worker, scoring-worker, notificador).
- DynamoDB con TABLAS SEPARADAS. Prohibido single-table design.
- SQS (dos colas, cada una con DLQ, maxReceiveCount 3).
- Amazon Bedrock, región us-east-1, vía boto3.
- boto3, Pydantic v2, BeautifulSoup con html.parser. PROHIBIDO lxml (binario compilado, falla en Lambda).
- Empaquetado zip. Sin Docker, sin capas pesadas, sin headless Chromium.

# Reglas invariantes (violarlas es un bug, no una preferencia)

1. IDs de modelo de Bedrock NUNCA hardcodeados. Se leen de variables de entorno
   (BEDROCK_MODEL_SMALL, BEDROCK_MODEL_MID) en un único módulo shared/bedrock.py.
2. Toda salida de un LLM se valida con un modelo Pydantic. Prohibido json.loads() directo.
   Ante fallo de validación: un reintento con el error inyectado en el prompt, luego error controlado.
3. Los workers de SQS deben ser IDEMPOTENTES. SQS entrega al menos una vez.
   El progreso de un ScanJob se lleva con un String Set y operación ADD, NUNCA con un contador decreciente.
4. userId SIEMPRE se extrae del JWT del authorizer (event.requestContext.authorizer.claims.sub).
   NUNCA se acepta desde el body o los query params.
5. Los modelos de dominio viven en backend/shared/models.py y son la única fuente de verdad.
   Ninguna Lambda redefine un modelo.
6. La IA genera solo texto o JSON estructurado. Nunca código ejecutable, nunca HTML renderizable.
7. Sin secretos en el código. Las fuentes usadas (Greenhouse, Lever, RemoteOK) no requieren autenticación.
8. Logging estructurado en JSON a stdout. Nunca loguear el texto del CV ni contenido de perfil.