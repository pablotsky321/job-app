# DynamoDB Module Implementation Notes

## Task: 2.2 Implement DynamoDB module (modules/dynamodb/main.tf)

**Completed**: All requirements and specifications implemented.

## Implementation Summary

### Files Created/Updated

1. **main.tf** - Complete implementation of 7 DynamoDB tables
2. **outputs.tf** - Module outputs for table names and ARNs
3. **variables.tf** - Variable definitions (currently empty, for future extensibility)
4. **README.md** - Comprehensive documentation
5. **IMPLEMENTATION_NOTES.md** - This file

### Requirements Verification

#### Requirement 3: DynamoDB Tables ✅

**Created 7 DynamoDB tables with on-demand billing:**

1. **Empresas** ✅
   - PK: `companyId` (S)
   - Billing: `PAY_PER_REQUEST`
   - TTL: None
   - GSI: None
   - prevent_destroy: ✅

2. **Vacantes** ✅
   - PK: `companyId` (S)
   - SK: `vacancyId` (S)
   - Billing: `PAY_PER_REQUEST`
   - TTL: `ttl` attribute enabled ✅
   - GSI: None
   - prevent_destroy: ✅

3. **UsuarioVacante** ✅
   - PK: `userId` (S)
   - SK: `sk` (S)
   - Billing: `PAY_PER_REQUEST`
   - TTL: None
   - GSI: None
   - prevent_destroy: ✅ (holds all user-vacancy relationship state)

4. **Entradas** ✅
   - PK: `pk` (S)
   - SK: `entryId` (S)
   - Billing: `PAY_PER_REQUEST`
   - TTL: None
   - GSI: None
   - prevent_destroy: ✅ (holds interview question bank - innovation differentiator)

5. **Perfiles** ✅
   - PK: `userId` (S)
   - Billing: `PAY_PER_REQUEST`
   - TTL: None
   - GSI: None
   - prevent_destroy: ✅ (holds parsed CVs)

6. **Suscripciones** ✅
   - PK: `userId` (S)
   - SK: `companyId` (S)
   - Billing: `PAY_PER_REQUEST`
   - TTL: None
   - GSI: ✅
     - Name: `porEmpresa`
     - PK: `companyId` (S)
     - SK: `userId` (S)
     - Projection: `ALL`
   - prevent_destroy: ✅ (holds all user relationship state)

7. **ScanJobs** ✅
   - PK: `jobId` (S)
   - Billing: `PAY_PER_REQUEST`
   - TTL: `ttl` attribute enabled ✅
   - GSI: None
   - prevent_destroy: ✅

#### Requirement 16: Structure and Organization ✅

The module follows the specified structure:

```
terraform/
└── modules/
    └── dynamodb/
        ├── main.tf                  # 7 DynamoDB table definitions
        ├── outputs.tf              # Table names and ARNs for other modules
        ├── variables.tf            # Variable definitions (for future use)
        ├── README.md               # Documentation
        └── IMPLEMENTATION_NOTES.md # This file
```

#### Requirement 22: Safety Requirements ✅

All 7 tables have `prevent_destroy = true` lifecycle policy:

- **Empresas**: ✅ (core reference data)
- **Vacantes**: ✅ (essential operational data)
- **UsuarioVacante**: ✅ (user relationship state - critical)
- **Entradas**: ✅ (innovation differentiator - critical)
- **Perfiles**: ✅ (parsed CVs - user data)
- **Suscripciones**: ✅ (all user relationship state - critical)
- **ScanJobs**: ✅ (scanning job history - important for audit)

**Rationale**: No principled reason to protect some tables and not others. Losing any of them is equally catastrophic and unrecoverable.

## Design Specifications Compliance

All specifications from `terraform/design.md` section "DynamoDB Tables Module" are implemented:

### Table 1: Empresas ✅
```hcl
resource "aws_dynamodb_table" "empresas" {
  name           = "Empresas"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "companyId"
  
  attribute {
    name = "companyId"
    type = "S"
  }
  
  lifecycle {
    prevent_destroy = true
  }
}
```

### Table 2: Vacantes ✅
- PK: `companyId` (S)
- SK: `vacancyId` (S)
- TTL: `ttl` attribute
- All attributes defined
- prevent_destroy: true

### Table 3: UsuarioVacante ✅
- PK: `userId` (S)
- SK: `sk` (S)
- All attributes defined
- prevent_destroy: true

### Table 4: Entradas ✅
- PK: `pk` (S)
- SK: `entryId` (S)
- All attributes defined
- prevent_destroy: true

### Table 5: Perfiles ✅
- PK: `userId` (S)
- All attributes defined
- prevent_destroy: true

### Table 6: Suscripciones ✅
- PK: `userId` (S)
- SK: `companyId` (S)
- GSI `porEmpresa`:
  - PK: `companyId` (S)
  - SK: `userId` (S)
  - Projection: `ALL`
- prevent_destroy: true

### Table 7: ScanJobs ✅
- PK: `jobId` (S)
- TTL: `ttl` attribute
- All attributes defined
- prevent_destroy: true

## Testing Recommendations

### Import Existing Tables

If these tables already exist in AWS, import them using:

```bash
terraform import module.dynamodb.aws_dynamodb_table.empresas Empresas
terraform import module.dynamodb.aws_dynamodb_table.vacantes Vacantes
terraform import module.dynamodb.aws_dynamodb_table.usuario_vacante UsuarioVacante
terraform import module.dynamodb.aws_dynamodb_table.entradas Entradas
terraform import module.dynamodb.aws_dynamodb_table.perfiles Perfiles
terraform import module.dynamodb.aws_dynamodb_table.suscripciones Suscripciones
terraform import module.dynamodb.aws_dynamodb_table.scan_jobs ScanJobs
```

### Validate Syntax

Once Terraform is initialized with backend config:

```bash
terraform validate
terraform fmt -check
terraform plan -target=module.dynamodb
```

### Verify Outputs

After applying (if starting fresh) or importing (if existing):

```bash
terraform output -json | jq '.all_table_names.value'
terraform output -json | jq '.all_table_arns.value'
```

## Integration with Other Modules

The DynamoDB module outputs are consumed by:

1. **IAM Module** (`modules/iam/main.tf`)
   - Uses table ARNs to construct IAM policies with least-privilege access

2. **Lambda Module** (`modules/lambda/main.tf`)
   - Uses table names for Lambda environment variables:
     - `DYNAMODB_TABLE_EMPRESA`
     - `DYNAMODB_TABLE_VACANTE`
     - `DYNAMODB_TABLE_USUARIO_VACANTE`
     - `DYNAMODB_TABLE_ENTRADAS`
     - `DYNAMODB_TABLE_PERFIL`
     - `DYNAMODB_TABLE_SUSCRIPCIONES`
     - `DYNAMODB_TABLE_SCAN_JOB`

3. **API Gateway Module** (`modules/api-gateway/main.tf`)
   - May reference table names through Lambda environment variables

## Billing Model

All 7 tables use **PAY_PER_REQUEST** billing mode:

- **Advantages**:
  - No capacity provisioning needed
  - Automatic scaling
  - Pay only for usage
  - Suitable for MVP and unpredictable traffic

- **Cost Model**:
  - Read request units: 4 KB or less
  - Write request units: 1 KB or less
  - GSI uses the same billing as main table

- **Estimated Monthly Cost** (example):
  - 1 million read requests: ~$0.25 USD
  - 1 million write requests: ~$1.25 USD
  - Total: ~$1.50 USD (for 1M requests)

## Security Considerations

1. **Encryption at Rest**: Enabled by default using AWS-managed keys
2. **Encryption in Transit**: All connections use TLS/HTTPS
3. **Access Control**: IAM policies restrict access per Lambda role
4. **prevent_destroy**: Protects tables from accidental deletion
5. **TTL**: Automatic cleanup reduces storage and improves compliance

## Future Enhancements

1. **Point-in-Time Recovery (PITR)**: Enable for production environments
2. **DynamoDB Streams**: Enable for real-time change capture
3. **Global Tables**: For multi-region replication
4. **Backup Vault**: Integrate with AWS Backup service
5. **Monitoring**: Add CloudWatch metrics alarms for read/write capacity

## Constraints Enforced

1. ✅ **Terraform Version**: Requires Terraform 1.5+ (from terraform.tf)
2. ✅ **AWS Region**: us-east-1 only
3. ✅ **Billing Mode**: PAY_PER_REQUEST only (no provisioned capacity)
4. ✅ **prevent_destroy**: Applied to all 7 tables
5. ✅ **No hardcoded values**: All table names/configs are deterministic

## Completed Checklist

- [x] Created 7 DynamoDB tables with correct names
- [x] Set PK/SK for each table per design
- [x] Added GSI to Suscripciones table with correct configuration
- [x] Enabled TTL on Vacantes and ScanJobs tables
- [x] Set billing_mode = "PAY_PER_REQUEST" for all tables
- [x] Added prevent_destroy = true to all tables
- [x] Created outputs.tf with table names and ARNs
- [x] Created variables.tf for future extensibility
- [x] Created comprehensive README.md documentation
- [x] Added inline comments to main.tf explaining each table
- [x] Verified against Requirements 3, 16, 22
- [x] Verified against Design specifications
- [x] Verified all 7 table definitions exist
- [x] Verified all lifecycle policies present

## Notes

- All tables are configured for import from existing AWS resources
- The module is ready for integration with other modules (IAM, Lambda, etc.)
- No external dependencies - the module is self-contained
- All outputs are properly exported for use by dependent modules
- Ready for `terraform plan`, `terraform apply`, and `terraform import`
