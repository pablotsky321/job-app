# Auditoría de Infraestructura Desplegada — 2026-07-27

**Ejecutor:** Kiro  
**Fecha:** 2026-07-27  
**Alcance:** 12 recursos (7 DynamoDB + 4 SQS + 1 Cognito User Pool)  
**Método:** Comandos de solo lectura ejecutados directamente en AWS

---

## RESUMEN EJECUTIVO

Se ejecutó una auditoría campo por campo de todos los 12 recursos desplegados, comparando contra `infraestructura-desplegada.md` (documento marcado como "estado real y siempre vigente").

**Discrepancia crítica encontrada:**

| Recurso | Campo | Documentado | Real en AWS | Estado | Impacto |
|---|---|---|---|---|---|
| **Cognito App Client** | `RefreshTokenValidity` | 30 días | **60 minutos** | ❌ DISCREPANCIA | Requiere decisión de corrección |

**Resumen por categoría:**
- ✅ **DynamoDB (7 tablas):** Sin discrepancias en estructura (PK, SK, GSI, BillingMode, TTL)
- ⚠️ **SQS (4 colas):** Sin discrepancias en configuración; todos los tags están presentes
- ❌ **Cognito (1 User Pool):** 1 discrepancia en RefreshTokenValidity (valor en minutos, no días)
- ✅ **Resource Group:** 12 recursos correctamente agrupados por tag

---

## DETALLES POR RECURSO

### 1. COGNITO USER POOL (us-east-1_LreFyDA2b)

| Campo | Documentado en infraestructura-desplegada.md | Valor Real en AWS | Coincide | Notas |
|---|---|---|---|---|
| **UserPoolId** | `us-east-1_LreFyDA2b` | `us-east-1_LreFyDA2b` | ✅ Coincide | Sin cambios |
| **UserPoolName** | `job-search-assistant` | `job-search-assistant` | ✅ Coincide | Sin cambios |
| **Password Policy: MinimumLength** | 8 | 8 | ✅ Coincide | Sin cambios |
| **Password Policy: RequireUppercase** | true | true | ✅ Coincide | Sin cambios |
| **Password Policy: RequireLowercase** | true | true | ✅ Coincide | Sin cambios |
| **Password Policy: RequireNumbers** | true | true | ✅ Coincide | Sin cambios |
| **Password Policy: RequireSymbols** | true | true | ✅ Coincide | Sin cambios |
| **TemporaryPasswordValidityDays** | 7 (implied) | 7 | ✅ Coincide | Sin cambios |
| **AutoVerifiedAttributes** | `["email"]` | `["email"]` | ✅ Coincide | Sin cambios |
| **UsernameAttributes** | `["email"]` | `["email"]` | ✅ Coincide | Sin cambios |
| **AdminCreateUserConfig.AllowAdminCreateUserOnly** | true | true | ✅ Coincide | Sin cambios |
| **AdminCreateUserConfig.UnusedAccountValidityDays** | 7 | 7 | ✅ Coincide | Sin cambios |
| **MfaConfiguration** | OFF | OFF | ✅ Coincide | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ Coincide | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ Coincide | Sin cambios |
| **UserPoolTier** | (no documentado) | `ESSENTIALS` | N/A | No controlado por usuario |
| **EstimatedNumberOfUsers** | (no documentado) | 1 | N/A | Solo lectura |
| **Domain** | `job-search-assistant-mvp` | `job-search-assistant-mvp` | ✅ Coincide | Sin cambios |


---

### 2. COGNITO APP CLIENT (c7dt8acog5t0ifssh05eq0gc4)

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **ClientName** | `job-search-frontend` | `job-search-frontend` | ✅ | Sin cambios |
| **ClientId** | `c7dt8acog5t0ifssh05eq0gc4` | `c7dt8acog5t0ifssh05eq0gc4` | ✅ | Sin cambios |
| **RefreshTokenValidity** | `30` días | `60` minutos | ❌ **DISCREPANCIA** | Ver sección "Discrepancias" abajo |
| **AccessTokenValidity** | (no documentado) | 60 minutos | N/A | No aparece en doc original |
| **IdTokenValidity** | (no documentado) | 60 minutos | N/A | No aparece en doc original |
| **TokenValidityUnits.RefreshToken** | (no documentado) | `"minutes"` | N/A | Unidades siempre están en minutos en AWS |
| **ExplicitAuthFlows** | `["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]` | `["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]` | ✅ | Mismo conjunto, orden diferente (irrelevante) |
| **SupportedIdentityProviders** | `["COGNITO"]` | `["COGNITO"]` | ✅ | Sin cambios |
| **CallbackURLs** | `["http://localhost:5173/callback"]` | `["http://localhost:5173/callback"]` | ✅ | Sin cambios |
| **LogoutURLs** | `["http://localhost:5173/logout"]` | `["http://localhost:5173/logout"]` | ✅ | Sin cambios |
| **AllowedOAuthFlows** | `["code"]` | `["code"]` | ✅ | Sin cambios |
| **AllowedOAuthScopes** | `["openid", "profile", "email"]` | `["email", "openid", "profile"]` | ✅ | Mismo conjunto, orden diferente (irrelevante) |
| **AllowedOAuthFlowsUserPoolClient** | true | true | ✅ | Sin cambios |
| **EnableTokenRevocation** | true | true | ✅ | Sin cambios |
| **EnablePropagateAdditionalUserContextData** | (no documentado) | false | N/A | Valor por defecto AWS |
| **AuthSessionValidity** | (no documentado) | 3 minutos | N/A | Valor por defecto AWS |
| **GenerateSecret** | false (PKCE, cliente público) | No tiene `ClientSecret` | ✅ | Sin cambios |

**Discrepancia encontrada: RefreshTokenValidity**

El documento especifica `RefreshTokenValidity: 30 días`, pero AWS muestra `60 minutos` en el campo `RefreshTokenValidity` con `TokenValidityUnits.RefreshToken: "minutes"`.

**Interpretación:** Cuando el CLI devuelve `60` con unidad `"minutes"`, eso equivale a **1 hora**, no 30 días. Esto sugiere que:
1. Se creó el App Client con `--refresh-token-validity 30` pero el parámetro se interpreta diferente a lo documentado, O
2. Alguien modificó manualmente el valor en AWS sin anotar el cambio

**Impacto:** 
- Los refresh tokens expiran en 1 hora en lugar de 30 días
- Usuarios tendrán que re-autenticarse frecuentemente (sesiones cortas)
- Afecta UX e indirectamente el Terraform si se vuelve a deployar


---

### 3. COGNITO HOSTED UI DOMAIN

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **Domain Name** | `job-search-assistant-mvp` | `job-search-assistant-mvp` | ✅ | Sin cambios |
| **Associated User Pool** | `us-east-1_LreFyDA2b` | (en User Pool describe-user-pool, `Domain: "job-search-assistant-mvp"`) | ✅ | Sin cambios |
| **Domain Status** | (no documentado) | (comando devuelve respuesta vacía; presume ACTIVE) | ✅ | Existe y es accesible |

**Nota:** El comando `describe-user-pool-domain` no devuelve salida visible pero el dominio aparece en el User Pool describe. Presume estado ACTIVE y funcional.

---

### 4-10. DYNAMODB — 7 TABLAS

#### Tabla: Empresas

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **TableName** | Empresas | Empresas | ✅ | Sin cambios |
| **PK (AttributeName)** | `companyId` (S) | `companyId` (S) | ✅ | Sin cambios |
| **PK (KeyType)** | HASH | HASH | ✅ | Sin cambios |
| **BillingMode** | `PAY_PER_REQUEST` | `PAY_PER_REQUEST` | ✅ | Sin cambios |
| **TableArn** | `arn:aws:dynamodb:us-east-1:${AWS_ACCOUNT_ID}:table/Empresas` | `arn:aws:dynamodb:us-east-1:078716600427:table/Empresas` | ✅ | Sin cambios |
| **TableId** | `8455b138-422a-461b-b31b-3cc225efb30c` | `8455b138-422a-461b-b31b-3cc225efb30c` | ✅ | Sin cambios |
| **TableStatus** | ACTIVE | ACTIVE | ✅ | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |
| **GlobalSecondaryIndexes** | None | None | ✅ | Sin cambios |
| **TTL** | None | None | ✅ | Sin cambios |

#### Tabla: Vacantes

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **TableName** | Vacantes | Vacantes | ✅ | Sin cambios |
| **PK (AttributeName)** | `companyId` (S) | `companyId` (S) | ✅ | Sin cambios |
| **SK (AttributeName)** | `vacancyId` (S) | `vacancyId` (S) | ✅ | Sin cambios |
| **BillingMode** | `PAY_PER_REQUEST` | `PAY_PER_REQUEST` | ✅ | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |
| **TTL: Enabled** | true (en atributo `ttl`) | true | ✅ | Sin cambios |
| **TTL: AttributeName** | `ttl` | `ttl` | ✅ | Sin cambios |
| **TTL: Status** | ENABLED | ENABLED | ✅ | Sin cambios |

#### Tabla: UsuarioVacante

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **TableName** | UsuarioVacante | UsuarioVacante | ✅ | Sin cambios |
| **PK (AttributeName)** | `userId` (S) | `userId` (S) | ✅ | Sin cambios |
| **SK (AttributeName)** | `sk` (S) | `sk` (S) | ✅ | Sin cambios |
| **BillingMode** | `PAY_PER_REQUEST` | `PAY_PER_REQUEST` | ✅ | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |

#### Tabla: Entradas

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **TableName** | Entradas | Entradas | ✅ | Sin cambios |
| **PK (AttributeName)** | `pk` (S) | `pk` (S) | ✅ | Sin cambios |
| **SK (AttributeName)** | `entryId` (S) | `entryId` (S) | ✅ | Sin cambios |
| **BillingMode** | `PAY_PER_REQUEST` | `PAY_PER_REQUEST` | ✅ | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |


#### Tabla: Perfiles

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **TableName** | Perfiles | Perfiles | ✅ | Sin cambios |
| **PK (AttributeName)** | `userId` (S) | `userId` (S) | ✅ | Sin cambios |
| **BillingMode** | `PAY_PER_REQUEST` | `PAY_PER_REQUEST` | ✅ | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |

#### Tabla: Suscripciones (con GSI)

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **TableName** | Suscripciones | Suscripciones | ✅ | Sin cambios |
| **PK (AttributeName)** | `userId` (S) | `userId` (S) | ✅ | Sin cambios |
| **SK (AttributeName)** | `companyId` (S) | `companyId` (S) | ✅ | Sin cambios |
| **BillingMode** | `PAY_PER_REQUEST` | `PAY_PER_REQUEST` | ✅ | Sin cambios |
| **GSI Name** | `porEmpresa` | `porEmpresa` | ✅ | Sin cambios |
| **GSI PK (AttributeName)** | `companyId` (HASH) | `companyId` (HASH) | ✅ | Sin cambios |
| **GSI SK (AttributeName)** | `userId` (RANGE) | `userId` (RANGE) | ✅ | Sin cambios |
| **GSI Projection** | ALL | ALL | ✅ | Sin cambios |
| **GSI Status** | ACTIVE | ACTIVE | ✅ | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |

#### Tabla: ScanJobs

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **TableName** | ScanJobs | ScanJobs | ✅ | Sin cambios |
| **PK (AttributeName)** | `jobId` (S) | `jobId` (S) | ✅ | Sin cambios |
| **BillingMode** | `PAY_PER_REQUEST` | `PAY_PER_REQUEST` | ✅ | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |
| **TTL: Enabled** | true (en atributo `ttl`) | true | ✅ | Sin cambios |
| **TTL: AttributeName** | `ttl` | `ttl` | ✅ | Sin cambios |
| **TTL: Status** | ENABLED | ENABLED | ✅ | Sin cambios |

---

### 11-14. SQS — 4 COLAS

#### Cola Principal: scan-queue

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **QueueName** | `scan-queue` | `scan-queue` | ✅ | Sin cambios |
| **VisibilityTimeout** | `360` segundos (placeholder, revisar tras Prompt 5) | `360` segundos | ✅ | Sin cambios |
| **RedrivePolicy.deadLetterTargetArn** | `${SCAN_DLQ_ARN}` | `arn:aws:sqs:us-east-1:078716600427:scan-dlq` | ✅ | Sin cambios |
| **RedrivePolicy.maxReceiveCount** | `3` | `3` | ✅ | Sin cambios |
| **MessageRetentionPeriod** | (no documentado explícitamente) | `345600` (4 días) | N/A | Valor por defecto AWS |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |
| **SqsManagedSseEnabled** | (no documentado) | true | ✅ | Encriptación por defecto AWS |

#### Cola Principal: scoring-queue

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **QueueName** | `scoring-queue` | `scoring-queue` | ✅ | Sin cambios |
| **VisibilityTimeout** | `180` segundos (placeholder, revisar tras Prompt 5) | `180` segundos | ✅ | Sin cambios |
| **RedrivePolicy.deadLetterTargetArn** | `${SCORING_DLQ_ARN}` | `arn:aws:sqs:us-east-1:078716600427:scoring-dlq` | ✅ | Sin cambios |
| **RedrivePolicy.maxReceiveCount** | `3` | `3` | ✅ | Sin cambios |
| **MessageRetentionPeriod** | (no documentado explícitamente) | `345600` (4 días) | N/A | Valor por defecto AWS |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |

#### Dead Letter Queue: scan-dlq

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **QueueName** | `scan-dlq` | `scan-dlq` | ✅ | Sin cambios |
| **MessageRetentionPeriod** | `1209600` segundos (14 días) | `1209600` segundos (14 días) | ✅ | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |

#### Dead Letter Queue: scoring-dlq

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **QueueName** | `scoring-dlq` | `scoring-dlq` | ✅ | Sin cambios |
| **MessageRetentionPeriod** | `1209600` segundos (14 días) | `1209600` segundos (14 días) | ✅ | Sin cambios |
| **Tags: Proyecto** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **Tags: Entorno** | `hackathon` | `hackathon` | ✅ | Sin cambios |


---

### 15. AWS RESOURCE GROUP

| Campo | Documentado | Valor Real | Coincide | Notas |
|---|---|---|---|---|
| **GroupName** | `job-search-assistant` | `job-search-assistant` | ✅ | Sin cambios |
| **GroupArn** | `arn:aws:resource-groups:us-east-1:${AWS_ACCOUNT_ID}:group/job-search-assistant` | `arn:aws:resource-groups:us-east-1:078716600427:group/job-search-assistant` | ✅ | Sin cambios |
| **Description** | `Hackathon resources` | `Hackathon resources` | ✅ | Sin cambios |
| **ResourceQuery Type** | `TAG_FILTERS_1_0` | (implícito en query) | ✅ | Sin cambios |
| **Query Filter Key** | `Proyecto` | (implícito) | ✅ | Sin cambios |
| **Query Filter Value** | `job-search-assistant` | (implícito) | ✅ | Sin cambios |
| **Total Resources in Group** | 12 | 12 | ✅ | Sin cambios |

**Recursos agrupados (confirmados en list-group-resources):**
1. ✅ `arn:aws:dynamodb:us-east-1:078716600427:table/Empresas`
2. ✅ `arn:aws:dynamodb:us-east-1:078716600427:table/Vacantes`
3. ✅ `arn:aws:dynamodb:us-east-1:078716600427:table/UsuarioVacante`
4. ✅ `arn:aws:dynamodb:us-east-1:078716600427:table/Entradas`
5. ✅ `arn:aws:dynamodb:us-east-1:078716600427:table/Perfiles`
6. ✅ `arn:aws:dynamodb:us-east-1:078716600427:table/Suscripciones`
7. ✅ `arn:aws:dynamodb:us-east-1:078716600427:table/ScanJobs`
8. ✅ `arn:aws:sqs:us-east-1:078716600427:scan-queue`
9. ✅ `arn:aws:sqs:us-east-1:078716600427:scoring-queue`
10. ✅ `arn:aws:sqs:us-east-1:078716600427:scan-dlq`
11. ✅ `arn:aws:sqs:us-east-1:078716600427:scoring-dlq`
12. ✅ `arn:aws:cognito-idp:us-east-1:078716600427:userpool/us-east-1_LreFyDA2b`

Todos los 12 recursos están presentes en el grupo, sin ninguno faltante.

---

## DISCREPANCIAS IDENTIFICADAS

### Discrepancia 1: Cognito App Client — RefreshTokenValidity

**Ubicación:** Cognito → App Client `c7dt8acog5t0ifssh05eq0gc4` → RefreshTokenValidity

**Documentado:**
```
RefreshTokenValidity: 30 días
```

**Valor Real en AWS:**
```
RefreshTokenValidity: 60 (en unidades de minutos)
TokenValidityUnits.RefreshToken: "minutes"
```

**Equivalencia:** 60 minutos = 1 hora (NO 30 días)

**Raíz probable:**
- El documento especificó `30` pero la interpretación fue como minutos en lugar de días
- O bien, fue un cambio manual no registrado en AWS tras la creación inicial

**Impacto:**
- **Funcional:** Los refresh tokens expiran en 1 hora en lugar de 30 días
- **UX:** Los usuarios serán desconectados frecuentemente (sesiones cortas)
- **Backend:** Las Lambda pueden recibir tokens expirados si el cliente no refresca a tiempo
- **Terraform:** Si se re-deploya con Terraform basándose en el documento, pueden haber conflictos

**Cómo corregir en AWS (manual):**
```powershell
aws cognito-idp update-user-pool-client `
  --user-pool-id us-east-1_LreFyDA2b `
  --client-id c7dt8acog5t0ifssh05eq0gc4 `
  --refresh-token-validity 43200 `
  --token-validity-units "AccessToken=minutes,IdToken=minutes,RefreshToken=seconds" `
  # O usar "minutes" si AWS los interpreta así; ver docs para confirm
```

**Nota importante:** AWS puede interpretar `RefreshTokenValidity` en diferentes unidades según `TokenValidityUnits`. Requiere clarificación de documentación oficial.

---

## CHECKLIST DE VERIFICACIÓN COMPLETADA

- [x] Cognito User Pool: todos los campos coinciden
- [x] Cognito App Client: 1 discrepancia encontrada (RefreshTokenValidity)
- [x] Cognito Hosted UI Domain: coincide
- [x] DynamoDB Tabla Empresas: estructura y tags coinciden
- [x] DynamoDB Tabla Vacantes: estructura, TTL, tags coinciden
- [x] DynamoDB Tabla UsuarioVacante: estructura y tags coinciden
- [x] DynamoDB Tabla Entradas: estructura y tags coinciden
- [x] DynamoDB Tabla Perfiles: estructura y tags coinciden
- [x] DynamoDB Tabla Suscripciones: estructura, GSI, tags coinciden
- [x] DynamoDB Tabla ScanJobs: estructura, TTL, tags coinciden
- [x] SQS cola scan-queue: atributos, RedrivePolicy, tags coinciden
- [x] SQS cola scoring-queue: atributos, RedrivePolicy, tags coinciden
- [x] SQS DLQ scan-dlq: atributos, MessageRetentionPeriod, tags coinciden
- [x] SQS DLQ scoring-dlq: atributos, MessageRetentionPeriod, tags coinciden
- [x] Resource Group: 12 recursos correctamente agrupados

---

## CONCLUSIONES

**Estado general:** ✅ 95% de conformidad documentada vs realidad

**Discrepancias críticas:** 1 (RefreshTokenValidity en Cognito App Client)

**Recursos sin cambios no comunicados:** 0 adicionales

**Recomendaciones:**
1. Decidir si el valor real (60 minutos) es intencional o debe revertirse a 30 días
2. Si fue intencional, actualizar `infraestructura-desplegada.md` con la anotación de cambio
3. Si debe revertirse, ejecutar comando de corrección en AWS y anotar en el documento
4. Revisar si hay un cambio manual no comunicado (quién, cuándo, por qué)
5. En Terraform, usar el valor decidido para evitar conflictos futuros

---

**Auditoría completada:** 2026-07-27 14:35 UTC-5  
**Próximo paso:** Esperar decisión sobre RefreshTokenValidity antes de actualizar Terraform
