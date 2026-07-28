# DynamoDB Tables Module

This module creates and manages all DynamoDB tables for the job-search-assistant application.

## Overview

The module creates 7 DynamoDB tables for storing company information, job vacancies, user profiles, subscriptions, and scanning jobs. All tables use on-demand (PAY_PER_REQUEST) billing and are protected from accidental deletion with `prevent_destroy` lifecycle policies.

## Tables

### 1. Empresas (Companies)
- **Purpose**: Store company/employer information
- **PK**: `companyId` (String)
- **Billing**: PAY_PER_REQUEST
- **Protection**: prevent_destroy

### 2. Vacantes (Vacancies)
- **Purpose**: Store job vacancy listings
- **PK**: `companyId` (String)
- **SK**: `vacancyId` (String)
- **TTL**: `ttl` attribute for automatic cleanup
- **Billing**: PAY_PER_REQUEST
- **Protection**: prevent_destroy

### 3. UsuarioVacante (User-Vacancy Relationships)
- **Purpose**: Store user-vacancy relationships (applications, matches, interactions)
- **PK**: `userId` (String)
- **SK**: `sk` (String) - format: "vacancy#{vacancyId}" or similar
- **Billing**: PAY_PER_REQUEST
- **Protection**: prevent_destroy
- **Note**: Holds all user-vacancy relationship state (critical data)

### 4. Entradas (Entries/Interview Questions)
- **Purpose**: Store interview questions/entries - the project's innovation differentiator
- **PK**: `pk` (String)
- **SK**: `entryId` (String)
- **Billing**: PAY_PER_REQUEST
- **Protection**: prevent_destroy
- **Note**: Contains the interview question bank (critical data)

### 5. Perfiles (User Profiles)
- **Purpose**: Store user profiles with parsed CV data
- **PK**: `userId` (String)
- **Billing**: PAY_PER_REQUEST
- **Protection**: prevent_destroy
- **Note**: Holds parsed CVs (critical user data)

### 6. Suscripciones (Subscriptions)
- **Purpose**: Store user subscriptions to companies
- **PK**: `userId` (String)
- **SK**: `companyId` (String)
- **GSI**: `porEmpresa` (PK: `companyId`, SK: `userId`)
- **Billing**: PAY_PER_REQUEST
- **Protection**: prevent_destroy
- **Note**: Holds all user relationship state (critical data)
- **GSI Use Case**: Query all users subscribed to a specific company

### 7. ScanJobs (Scanning Jobs)
- **Purpose**: Store scanning job metadata and progress
- **PK**: `jobId` (String)
- **TTL**: `ttl` attribute for automatic cleanup of completed/abandoned jobs (24 hours)
- **Billing**: PAY_PER_REQUEST
- **Protection**: prevent_destroy

## Billing Mode

All tables use **PAY_PER_REQUEST** (on-demand) billing mode:
- **Advantages**: No need to provision capacity, automatic scaling, pay only for usage
- **Cost Model**: Charged per read/write request unit (4KB read, 1KB write)
- **Recommended for**: Unpredictable traffic, development/testing environments, MVP phase

## Lifecycle Protection

All 7 tables have `prevent_destroy = true` lifecycle policy because:
- **Empresas**: Companies are the core reference data
- **Vacantes**: Vacancy listings are essential operational data
- **UsuarioVacante**: User-vacancy relationships are critical interaction history
- **Entradas**: Interview questions are the project's innovation differentiator
- **Perfiles**: Parsed CVs represent valuable user data
- **Suscripciones**: User subscriptions represent all user relationship state
- **ScanJobs**: Scanning job history is important for audit and debugging

There is no principled reason to protect some tables and not others — losing any one of them is equally catastrophic and unrecoverable.

## TTL (Time To Live)

- **Vacantes**: TTL attribute `ttl` for automatic cleanup of expired vacancies
- **ScanJobs**: TTL attribute `ttl` for automatic cleanup of completed/abandoned jobs (default: 24 hours)

TTL attribute should contain Unix timestamp (seconds since epoch). DynamoDB will automatically delete items where `ttl` <= current time.

## Global Secondary Index (GSI)

### Suscripciones.porEmpresa

- **PK**: `companyId` (String) - Query by company
- **SK**: `userId` (String) - Sub-partition by user
- **Projection**: ALL - Project all attributes from the main table
- **Use Case**: Find all users subscribed to a specific company
- **Billing**: Included in table's PAY_PER_REQUEST billing (no separate costs)

## Outputs

The module exports the following outputs:

- `empresas_table_name`: Name of the Empresas table
- `empresas_table_arn`: ARN of the Empresas table
- `vacantes_table_name`: Name of the Vacantes table
- `vacantes_table_arn`: ARN of the Vacantes table
- `usuario_vacante_table_name`: Name of the UsuarioVacante table
- `usuario_vacante_table_arn`: ARN of the UsuarioVacante table
- `entradas_table_name`: Name of the Entradas table
- `entradas_table_arn`: ARN of the Entradas table
- `perfiles_table_name`: Name of the Perfiles table
- `perfiles_table_arn`: ARN of the Perfiles table
- `suscripciones_table_name`: Name of the Suscripciones table
- `suscripciones_table_arn`: ARN of the Suscripciones table
- `scan_jobs_table_name`: Name of the ScanJobs table
- `scan_jobs_table_arn`: ARN of the ScanJobs table
- `all_table_arns`: Map of all table ARNs for IAM policy references
- `all_table_names`: Map of all table names for Lambda environment variables

## Usage

### In Root Module (terraform/main.tf)

```hcl
module "dynamodb" {
  source = "./modules/dynamodb"
}
```

### Referencing Outputs

In other modules (e.g., Lambda, IAM):

```hcl
# Reference a specific table name
environment {
  variables = {
    DYNAMODB_TABLE_EMPRESA = module.dynamodb.empresas_table_name
    DYNAMODB_TABLE_VACANTE = module.dynamodb.vacantes_table_name
  }
}

# Reference a specific table ARN for IAM policy
{
  Resource = module.dynamodb.empresas_table_arn
}

# Reference all table ARNs for a wildcard policy
{
  Resource = values(module.dynamodb.all_table_arns)
}
```

## Security Considerations

1. **Encryption at Rest**: DynamoDB tables are encrypted at rest by default using AWS-managed keys. No additional configuration needed.

2. **Encryption in Transit**: All data in transit uses TLS/HTTPS. Configure S3 VPC endpoints if needed for compliance.

3. **Access Control**: IAM roles control table access. Each Lambda function has its own role with minimal permissions to specific tables.

4. **Prevent Destroy**: All tables are protected from accidental deletion via `prevent_destroy = true`.

5. **TTL**: Automatic cleanup of expired data reduces storage costs and maintains GDPR compliance for time-limited data.

## Cost Optimization

- **On-Demand Billing**: Scales automatically with demand, no over-provisioning
- **TTL**: Reduces storage costs by automatically deleting expired items
- **GSI Projection**: Using "ALL" projection uses more storage but avoids fetch calls. Consider "KEYS_ONLY" if you frequently need to fetch full items
- **Monitoring**: Use CloudWatch metrics to monitor read/write capacity and adjust as needed

## Disaster Recovery

- **Backups**: Enable point-in-time recovery (PITR) for all tables in production
- **DynamoDB Streams**: Consider enabling streams for real-time change capture
- **Global Tables**: Not configured by default, but can be enabled for multi-region replication

## Importing Existing Tables

If tables already exist in AWS, use the import command:

```bash
terraform import module.dynamodb.aws_dynamodb_table.empresas Empresas
terraform import module.dynamodb.aws_dynamodb_table.vacantes Vacantes
terraform import module.dynamodb.aws_dynamodb_table.usuario_vacante UsuarioVacante
terraform import module.dynamodb.aws_dynamodb_table.entradas Entradas
terraform import module.dynamodb.aws_dynamodb_table.perfiles Perfiles
terraform import module.dynamodb.aws_dynamodb_table.suscripciones Suscripciones
terraform import module.dynamodb.aws_dynamodb_table.scan_jobs ScanJobs
```

## References

- [AWS DynamoDB Documentation](https://docs.aws.amazon.com/dynamodb/)
- [Terraform AWS DynamoDB Resources](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/dynamodb_table)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
