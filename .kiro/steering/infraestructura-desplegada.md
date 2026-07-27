---
inclusion: manual
---

# Infraestructura — Registro de ejecución

**Fecha:** 2026-07-26
**Región:** us-east-1
**Proyecto:** job-search-assistant
**Entorno:** hackathon

> Este documento registra la **trazabilidad completa** de la creación de la infraestructura mínima necesaria antes de ejecutar el Prompt 1 de Kiro. Todos los comandos fueron ejecutados manualmente en PowerShell 5.1.
>
> **Valores reales:** viven en `.env` (no versionado, nunca se sube al repo). Este
> documento los referencia como `${NOMBRE_VARIABLE}`. Para ver qué variables
> existen y en qué formato, revisa `.env.example` (sí versionado, con valores de
> ejemplo). Si necesitas los valores reales, pídelos al primer desarrollador por
> un canal privado — no están en ningún archivo de este repositorio.

---

## Resumen ejecutivo

| Componente | Cantidad | Estado | Notas |
|---|---|---|---|
| Tablas DynamoDB | 7 | ✅ Creadas | Todas con tags, TTL en Vacantes y ScanJobs, GSI porEmpresa en Suscripciones |
| Colas SQS | 4 | ✅ Creadas | 2 principales + 2 DLQ, RedrivePolicy configurado |
| User Pool Cognito | 1 | ✅ Creado | Flujo NEW_PASSWORD_REQUIRED probado y funcional |
| Resource Group | 1 | ✅ Creado | Agrupa los 12 recursos por tag Proyecto=job-search-assistant |

---

## 1. Variables de entorno

```powershell
$PROYECTO = "job-search-assistant"
$ENTORNO = "hackathon"
```

---

## 2. DynamoDB — 7 tablas

### 2.1 Tabla: Empresas

**Comando:**
```powershell
aws dynamodb create-table --table-name Empresas --attribute-definitions "AttributeName=companyId,AttributeType=S" --key-schema "AttributeName=companyId,KeyType=HASH" --billing-mode PAY_PER_REQUEST --tags "Key=Proyecto,Value=$PROYECTO" "Key=Entorno,Value=$ENTORNO"
```

**Resultado:** ✅ Creada
- TableName: `Empresas`
- PK: `companyId` (S)
- BillingMode: `PAY_PER_REQUEST`
- TableArn: `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/Empresas`
- TableId: `8455b138-422a-461b-b31b-3cc225efb30c`
- TableStatus: `CREATING` (luego ACTIVE)
- Tags: `Proyecto=job-search-assistant`, `Entorno=hackathon`

---

### 2.2 Tabla: Vacantes

**Comando:**
```powershell
aws dynamodb create-table --table-name Vacantes --attribute-definitions "AttributeName=companyId,AttributeType=S" "AttributeName=vacancyId,AttributeType=S" --key-schema "AttributeName=companyId,KeyType=HASH" "AttributeName=vacancyId,KeyType=RANGE" --billing-mode PAY_PER_REQUEST --tags "Key=Proyecto,Value=$PROYECTO" "Key=Entorno,Value=$ENTORNO"
```

**Resultado:** ✅ Creada
- TableName: `Vacantes`
- PK: `companyId` (S), SK: `vacancyId` (S)
- BillingMode: `PAY_PER_REQUEST`
- TableArn: `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/Vacantes`
- TableId: `02c0c323-b435-454e-b21c-9a5124808b9e`

**TTL habilitado:**
```powershell
aws dynamodb update-time-to-live --table-name Vacantes --time-to-live-specification "Enabled=true,AttributeName=ttl"
```

**Resultado:** ✅ TTL habilitado en atributo `ttl`

---

### 2.3 Tabla: UsuarioVacante

**Comando:**
```powershell
aws dynamodb create-table --table-name UsuarioVacante --attribute-definitions "AttributeName=userId,AttributeType=S" "AttributeName=sk,AttributeType=S" --key-schema "AttributeName=userId,KeyType=HASH" "AttributeName=sk,KeyType=RANGE" --billing-mode PAY_PER_REQUEST --tags "Key=Proyecto,Value=$PROYECTO" "Key=Entorno,Value=$ENTORNO"
```

**Resultado:** ✅ Creada
- TableName: `UsuarioVacante`
- PK: `userId` (S), SK: `sk` (S)
- BillingMode: `PAY_PER_REQUEST`
- TableArn: `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/UsuarioVacante`
- TableId: `6fe9ff46-c7ec-4514-ab5a-ac31e6e92fea`

---

### 2.4 Tabla: Entradas

**Comando:**
```powershell
aws dynamodb create-table --table-name Entradas --attribute-definitions "AttributeName=pk,AttributeType=S" "AttributeName=entryId,AttributeType=S" --key-schema "AttributeName=pk,KeyType=HASH" "AttributeName=entryId,KeyType=RANGE" --billing-mode PAY_PER_REQUEST --tags "Key=Proyecto,Value=$PROYECTO" "Key=Entorno,Value=$ENTORNO"
```

**Resultado:** ✅ Creada
- TableName: `Entradas`
- PK: `pk` (S), SK: `entryId` (S)
- BillingMode: `PAY_PER_REQUEST`
- TableArn: `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/Entradas`
- TableId: `dcdb5421-6c6c-4648-8baf-00adef035bb8`

---

### 2.5 Tabla: Perfiles

**Comando:**
```powershell
aws dynamodb create-table --table-name Perfiles --attribute-definitions "AttributeName=userId,AttributeType=S" --key-schema "AttributeName=userId,KeyType=HASH" --billing-mode PAY_PER_REQUEST --tags "Key=Proyecto,Value=$PROYECTO" "Key=Entorno,Value=$ENTORNO"
```

**Resultado:** ✅ Creada
- TableName: `Perfiles`
- PK: `userId` (S)
- BillingMode: `PAY_PER_REQUEST`
- TableArn: `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/Perfiles`
- TableId: `c1070e0d-3901-44c6-848a-26738af7bc3e`

---

### 2.6 Tabla: Suscripciones (con GSI porEmpresa)

**Comando para crear el archivo JSON del GSI:**
```powershell
@"
[
  {
    "IndexName": "porEmpresa",
    "KeySchema": [
      {"AttributeName": "companyId", "KeyType": "HASH"},
      {"AttributeName": "userId", "KeyType": "RANGE"}
    ],
    "Projection": {"ProjectionType": "ALL"}
  }
]
"@ | Set-Content -Path "suscripciones-gsi.json" -Encoding ascii
```

**Comando para crear la tabla:**
```powershell
aws dynamodb create-table --table-name Suscripciones --attribute-definitions "AttributeName=userId,AttributeType=S" "AttributeName=companyId,AttributeType=S" --key-schema "AttributeName=userId,KeyType=HASH" "AttributeName=companyId,KeyType=RANGE" --billing-mode PAY_PER_REQUEST --global-secondary-indexes file://suscripciones-gsi.json --tags "Key=Proyecto,Value=$PROYECTO" "Key=Entorno,Value=$ENTORNO"
```

**Resultado:** ✅ Creada con GSI
- TableName: `Suscripciones`
- PK: `userId` (S), SK: `companyId` (S)
- BillingMode: `PAY_PER_REQUEST`
- TableArn: `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/Suscripciones`
- TableId: `573261a1-656c-4c74-a466-6f0cdc0efc47`
- GSI `porEmpresa`: ✅ ACTIVE (PK: `companyId`, SK: `userId`, Projection: ALL)
  - IndexArn: `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/Suscripciones/index/porEmpresa`
  - WarmThroughput: ReadUnitsPerSecond=12000, WriteUnitsPerSecond=4000

---

### 2.7 Tabla: ScanJobs

**Comando:**
```powershell
aws dynamodb create-table --table-name ScanJobs --attribute-definitions "AttributeName=jobId,AttributeType=S" --key-schema "AttributeName=jobId,KeyType=HASH" --billing-mode PAY_PER_REQUEST --tags "Key=Proyecto,Value=$PROYECTO" "Key=Entorno,Value=$ENTORNO"
```

**Resultado:** ✅ Creada
- TableName: `ScanJobs`
- PK: `jobId` (S)
- BillingMode: `PAY_PER_REQUEST`
- TableArn: `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/ScanJobs`
- TableId: `6ae2b032-4796-4d9d-b2c2-75ca3ab5ddc2`

**TTL habilitado:**
```powershell
aws dynamodb update-time-to-live --table-name ScanJobs --time-to-live-specification "Enabled=true,AttributeName=ttl"
```

**Resultado:** ✅ TTL habilitado en atributo `ttl`

---

### Verificación de todas las tablas

**Comando:**
```powershell
aws dynamodb list-tables
```

**Resultado:** ✅ 7 tablas
```
TableNames: [
  "Empresas",
  "Entradas",
  "Perfiles",
  "ScanJobs",
  "Suscripciones",
  "UsuarioVacante",
  "Vacantes"
]
```

**Verificación de tags en tabla Empresas:**
```powershell
$TABLE_ARN = (aws dynamodb describe-table --table-name Empresas --query "Table.TableArn" --output text).Trim()
aws dynamodb list-tags-of-resource --resource-arn $TABLE_ARN
```

**Resultado:** ✅ Tags correctos
```
Tags: [
  { Key: "Proyecto", Value: "job-search-assistant" },
  { Key: "Entorno", Value: "hackathon" }
]
```

**Verificación de GSI en Suscripciones:**
```powershell
aws dynamodb describe-table --table-name Suscripciones --query "Table.GlobalSecondaryIndexes"
```

**Resultado:** ✅ GSI porEmpresa ACTIVE
```
IndexName: "porEmpresa"
IndexStatus: "ACTIVE"
KeySchema: [
  { AttributeName: "companyId", KeyType: "HASH" },
  { AttributeName: "userId", KeyType: "RANGE" }
]
Projection: { ProjectionType: "ALL" }
```

---

## 3. SQS — 4 colas (2 principales + 2 DLQ)

### 3.1 Dead Letter Queues (DLQ)

**Comando para scan-dlq:**
```powershell
aws sqs create-queue --queue-name scan-dlq --attributes "MessageRetentionPeriod=1209600" --tags "Proyecto=$PROYECTO,Entorno=$ENTORNO"
```

**Resultado:** ✅ Creada
- QueueUrl: `${SCAN_DLQ_URL}`
- QueueArn: `${SCAN_DLQ_ARN}`

**Comando para scoring-dlq:**
```powershell
aws sqs create-queue --queue-name scoring-dlq --attributes "MessageRetentionPeriod=1209600" --tags "Proyecto=$PROYECTO,Entorno=$ENTORNO"
```

**Resultado:** ✅ Creada
- QueueUrl: `${SCORING_DLQ_URL}`
- QueueArn: `${SCORING_DLQ_ARN}`

---

### 3.2 Extracción de ARNs

```powershell
$SCAN_DLQ_URL = (aws sqs get-queue-url --queue-name scan-dlq --query QueueUrl --output text).Trim()
$SCAN_DLQ_ARN = (aws sqs get-queue-attributes --queue-url $SCAN_DLQ_URL --attribute-names QueueArn --query Attributes.QueueArn --output text).Trim()

$SCORING_DLQ_URL = (aws sqs get-queue-url --queue-name scoring-dlq --query QueueUrl --output text).Trim()
$SCORING_DLQ_ARN = (aws sqs get-queue-attributes --queue-url $SCORING_DLQ_URL --attribute-names QueueArn --query Attributes.QueueArn --output text).Trim()
```

**Resultado:** guardados como `${SCAN_DLQ_ARN}` y `${SCORING_DLQ_ARN}` — ver `.env`.

---

### 3.3 Colas principales

**Comando para crear scan-queue-attributes.json:**
```powershell
@"
{
  "VisibilityTimeout": "360",
  "RedrivePolicy": "{\"deadLetterTargetArn\":\"$SCAN_DLQ_ARN\",\"maxReceiveCount\":\"3\"}"
}
"@ | Set-Content -Path "scan-queue-attributes.json" -Encoding ascii
```

**Comando para crear scan-queue:**
```powershell
aws sqs create-queue --queue-name scan-queue --attributes file://scan-queue-attributes.json --tags "Proyecto=$PROYECTO,Entorno=$ENTORNO"
```

**Resultado:** ✅ Creada
- QueueUrl: `${SCAN_QUEUE_URL}`
- QueueArn: `${SCAN_QUEUE_ARN}`
- VisibilityTimeout: `360` (placeholder, revisar tras Prompt 5)
- RedrivePolicy: apunta a `${SCAN_DLQ_ARN}`, maxReceiveCount 3

**Comando para crear scoring-queue-attributes.json:**
```powershell
@"
{
  "VisibilityTimeout": "180",
  "RedrivePolicy": "{\"deadLetterTargetArn\":\"$SCORING_DLQ_ARN\",\"maxReceiveCount\":\"3\"}"
}
"@ | Set-Content -Path "scoring-queue-attributes.json" -Encoding ascii
```

**Comando para crear scoring-queue:**
```powershell
aws sqs create-queue --queue-name scoring-queue --attributes file://scoring-queue-attributes.json --tags "Proyecto=$PROYECTO,Entorno=$ENTORNO"
```

**Resultado:** ✅ Creada
- QueueUrl: `${SCORING_QUEUE_URL}`
- QueueArn: `${SCORING_QUEUE_ARN}`
- VisibilityTimeout: `180` (placeholder, revisar tras Prompt 5)
- RedrivePolicy: apunta a `${SCORING_DLQ_ARN}`, maxReceiveCount 3

---

### Verificación de todas las colas

**Comando:**
```powershell
aws sqs list-queues
```

**Resultado:** ✅ 4 colas: `${SCAN_DLQ_URL}`, `${SCAN_QUEUE_URL}`, `${SCORING_DLQ_URL}`, `${SCORING_QUEUE_URL}`

**Verificación de atributos en scan-queue:**
```powershell
$scanQueueUrl = (aws sqs get-queue-url --queue-name scan-queue --query QueueUrl --output text).Trim()
aws sqs get-queue-attributes --queue-url $scanQueueUrl --attribute-names VisibilityTimeout RedrivePolicy
```

**Resultado:** ✅ `VisibilityTimeout: 360`, `RedrivePolicy` apuntando a `${SCAN_DLQ_ARN}` con `maxReceiveCount: 3`

**Verificación de tags en scan-queue:**
```powershell
aws sqs list-queue-tags --queue-url $scanQueueUrl
```

**Resultado:** ✅ Tags correctos (`Proyecto`, `Entorno`)

---

## 4. Cognito User Pool

### 4.1 Creación del User Pool

**Comando:**
```powershell
aws cognito-idp create-user-pool --pool-name job-search-assistant --admin-create-user-config AllowAdminCreateUserOnly=true --auto-verified-attributes email --username-attributes email --schema "Name=email,Required=true,Mutable=true" --user-pool-tags "Proyecto=$PROYECTO,Entorno=$ENTORNO"
```

**Resultado:** ✅ Creado
- UserPoolId: `${COGNITO_USER_POOL_ID}`
- UserPoolName: `job-search-assistant`
- UserPoolArn: `${COGNITO_USER_POOL_ARN}`
- AdminCreateUserOnly: `true`
- AutoVerifiedAttributes: `["email"]`
- UsernameAttributes: `["email"]`
- UserPoolTags: `{ "Proyecto": "job-search-assistant", "Entorno": "hackathon" }`
- PasswordPolicy: MinimumLength=8, RequireUppercase=true, RequireLowercase=true, RequireNumbers=true, RequireSymbols=true

**Guardar para uso posterior:**
```powershell
$USER_POOL_ID = "<valor real en .env: COGNITO_USER_POOL_ID>"
```

---

### 4.2 Creación del App Client

**Comando:**
```powershell
aws cognito-idp create-user-pool-client --user-pool-id $USER_POOL_ID --client-name job-search-frontend --no-generate-secret --allowed-o-auth-flows code --allowed-o-auth-scopes openid email profile --allowed-o-auth-flows-user-pool-client --supported-identity-providers COGNITO --callback-urls "http://localhost:5173/callback" --logout-urls "http://localhost:5173/logout" --explicit-auth-flows ALLOW_REFRESH_TOKEN_AUTH ALLOW_USER_SRP_AUTH ALLOW_ADMIN_USER_PASSWORD_AUTH
```

**Resultado:** ✅ Creado
- ClientId: `${COGNITO_CLIENT_ID}`
- ClientName: `job-search-frontend`
- UserPoolId: `${COGNITO_USER_POOL_ID}`
- AllowedOAuthFlows: `["code"]`
- AllowedOAuthScopes: `["openid", "profile", "email"]`
- AllowedOAuthFlowsUserPoolClient: `true`
- CallbackURLs: `["${COGNITO_CALLBACK_URL}"]`
- LogoutURLs: `["${COGNITO_LOGOUT_URL}"]`
- ExplicitAuthFlows: `["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]`
- RefreshTokenValidity: `30` días
- EnableTokenRevocation: `true`
- Sin secreto de cliente (cliente público, PKCE)

**Guardar para uso posterior:**
```powershell
$CLIENT_ID = "<valor real en .env: COGNITO_CLIENT_ID>"
```

---

### 4.3 Creación del dominio de Hosted UI

**Comando:**
```powershell
aws cognito-idp create-user-pool-domain --domain job-search-assistant-mvp --user-pool-id $USER_POOL_ID
```

**Resultado:** ✅ Creado
- Accesible en: `https://${COGNITO_HOSTED_UI_DOMAIN}`

---

### 4.4 Creación de usuario de prueba

**Comando:**
```powershell
aws cognito-idp admin-create-user --user-pool-id $USER_POOL_ID --username test@example.com --user-attributes "Name=email,Value=test@example.com" "Name=email_verified,Value=true" --temporary-password "<TEMP_PASSWORD>" --message-action SUPPRESS
```
*(la contraseña temporal real usada no se publica — no vive ni en el .md ni en el .env, fue de un solo uso para la prueba del flujo)*

**Resultado:** ✅ Creado
- Username: `44583408-7001-7013-ee65-ddb5a94c9818` (UUID asignado por Cognito)
- Email: `test@example.com`
- UserStatus: `FORCE_CHANGE_PASSWORD`
- Enabled: `true`

---

### 4.5 Prueba del flujo de autenticación (NEW_PASSWORD_REQUIRED)

**Comando 1 — Iniciar sesión con contraseña temporal:**
```powershell
aws cognito-idp admin-initiate-auth --user-pool-id $USER_POOL_ID --client-id $CLIENT_ID --auth-flow ADMIN_USER_PASSWORD_AUTH --auth-parameters "USERNAME=test@example.com,PASSWORD=<TEMP_PASSWORD>"
```

**Resultado:** ✅ Challenge recibido — `ChallengeName: NEW_PASSWORD_REQUIRED` con `Session` *(token de sesión de un solo uso, no se publica; ya expiró)*

**Comando 2 — Responder al desafío con contraseña definitiva:**
```powershell
$SESSION = "<valor recibido en el paso anterior>"

aws cognito-idp admin-respond-to-auth-challenge --user-pool-id $USER_POOL_ID --client-id $CLIENT_ID --challenge-name NEW_PASSWORD_REQUIRED --challenge-responses "USERNAME=test@example.com,NEW_PASSWORD=<NUEVA_CONTRASEÑA>" --session $SESSION
```

**Resultado:** ✅ Autenticación exitosa — se recibieron `AccessToken`, `RefreshToken` e `IdToken` sin error *(no se publican, incluso expirados)*. ExpiresIn: 3600s, TokenType: Bearer.

**Este flujo probó que un jurado atorado puede cambiar su contraseña y autenticarse sin problema.**

---

### Verificación de tags en User Pool

**Comando:**
```powershell
aws cognito-idp describe-user-pool --user-pool-id $USER_POOL_ID --query "UserPool.UserPoolTags"
```

**Resultado:** ✅ Tags correctos (`Proyecto`, `Entorno`)

---

## 5. AWS Resource Group

### 5.1 Creación del Resource Group

**Comando para crear resource-group-query.json:**
```powershell
@"
{
  "Type": "TAG_FILTERS_1_0",
  "Query": "{\"ResourceTypeFilters\":[\"AWS::AllSupported\"],\"TagFilters\":[{\"Key\":\"Proyecto\",\"Values\":[\"$PROYECTO\"]}]}"
}
"@ | Set-Content -Path "resource-group-query.json" -Encoding ascii
```

**Comando para crear el grupo:**
```powershell
aws resource-groups create-group --name job-search-assistant --description "Hackathon resources" --resource-query file://resource-group-query.json
```

**Resultado:** ✅ Creado
- GroupArn: `${RESOURCE_GROUP_ARN}`
- Name: `job-search-assistant`
- ResourceQuery Type: `TAG_FILTERS_1_0`, filtra por `Proyecto=job-search-assistant`

---

### 5.2 Verificación de recursos en el grupo

**Comando:**
```powershell
aws resource-groups list-group-resources --group-name job-search-assistant
```

**Resultado:** ✅ 12 recursos encontrados

**DynamoDB (7 tablas):** Empresas, Entradas, Perfiles, ScanJobs, Suscripciones, UsuarioVacante, Vacantes — todas bajo `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/<Nombre>`

**SQS (4 colas):** `${SCAN_DLQ_ARN}`, `${SCAN_QUEUE_ARN}`, `${SCORING_DLQ_ARN}`, `${SCORING_QUEUE_ARN}`

**Cognito (1 User Pool):** `${COGNITO_USER_POOL_ARN}`

---

## 6. Valores para el equipo

Todos los valores reales están en `.env` (no versionado). Este documento y
`.env.example` explican **qué** variables existen; `.env` tiene los valores
**reales**, y se comparte con el segundo desarrollador por un canal privado, no
por el repositorio.

Variables definidas: ver `.env.example` para la lista completa (región, cuenta,
nombres de tabla, colas, Cognito, resource group, tags de proyecto, y los
placeholders de Bedrock pendientes de §15).

---

## 7. Notas y pendientes

- ✅ **SQS Visibility Timeout:** Valores placeholder (360s para scan-queue, 180s para scoring-queue). Revisar después del **Prompt 5** (`backend-scan-y-scoring` · design) cuando los timeouts reales de las Lambdas estén definidos. El timeout debe ser 6× el timeout de la Lambda correspondiente. Actualizar en `.env` cuando cambie.
- ✅ **Cognito Callback URLs:** Actualmente apuntan a `localhost:5173` (desarrollo local). Actualizar en `.env` a la URL real de CloudFront cuando exista (post-Terraform).
- ⚠️ **Usuarios finales:** Solo se creó un usuario de prueba (`test@example.com`). Los 4 usuarios restantes (2 devs + 3 jurados) deben crearse después con sus correos confirmados en SES.
- ⚠️ **Bedrock:** IDs de modelo aún pendientes de solicitar acceso (§15). Placeholders en `.env` marcados como `TODO`.
- ✅ **Flujo de autenticación:** Completamente probado — un usuario puede cambiar su contraseña temporal en el primer login sin problema.

---

## 8. Checklist de verificación

- [x] 7 tablas DynamoDB creadas y con tags
- [x] TTL habilitado en Vacantes y ScanJobs
- [x] GSI porEmpresa en Suscripciones en estado ACTIVE
- [x] 4 colas SQS creadas con tags
- [x] RedrivePolicy configurado en ambas colas principales (maxReceiveCount: 3)
- [x] 2 DLQs creadas con retención de 14 días
- [x] Cognito User Pool creado con tags
- [x] App Client configurado con PKCE (no genera secreto)
- [x] Hosted UI domain creado
- [x] Usuario de prueba creado y flujo NEW_PASSWORD_REQUIRED probado exitosamente
- [x] Resource Group creado agregando todos los 12 recursos
- [x] `.env` generado con todos los valores reales, `.env.example` generado para el repo
- [ ] `.env` agregado a `.gitignore` — **hacer esto antes del primer commit**
- [ ] `.env` compartido con el segundo desarrollador por canal privado

---

**Infraestructura mínima completada y lista para Prompt 1 de Kiro.**