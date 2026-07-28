# Design Document: Terraform Infrastructure for Job-Search-Assistant

## Overview

This document specifies the Terraform infrastructure design for deploying the job-search-assistant application on AWS. The infrastructure includes all AWS resources needed to run the application, including DynamoDB tables, SQS queues, Lambda functions, API Gateway, Cognito, S3/CloudFront, EventBridge Scheduler, SES, and CloudWatch monitoring.

The infrastructure will be deployed in the `us-east-1` region and will import 15 existing manually created resources while provisioning the remaining 20+ resources.

## Module Structure

### Proposed Structure

```
terraform/
├── main.tf                 # Root module, calls submodules
├── variables.tf            # Variables definition
├── terraform.tfvars        # Actual values (gitignored)
├── terraform.tfvars.example # Template (versioned)
├── outputs.tf              # Outputs
├── backend.tf              # Backend configuration
├── providers.tf            # Provider configuration
├── terraform.tf            # Terraform version constraint
├── scripts/
│   └── import_resources.sh # Import commands for existing resources
└── modules/
    ├── dynamodb/
    │   └── main.tf         # DynamoDB tables (7 tables)
    ├── sqs/
    │   └── main.tf         # SQS queues and DLQs (4 queues)
    ├── iam/
    │   └── main.tf         # IAM roles/policies (5 Lambda roles + GitHub Actions OIDC role)
    ├── lambda/
    │   └── main.tf         # Lambda functions (5 functions)
    ├── api-gateway/
    │   └── main.tf         # API Gateway with Cognito authorizer
    ├── cognito/
    │   └── main.tf         # Cognito User Pool (import only)
    ├── s3-cloudfront/
    │   └── main.tf         # S3 bucket and CloudFront distribution
    ├── eventbridge/
    │   └── main.tf         # EventBridge Scheduler
    ├── ses/
    │   └── main.tf         # SES configuration
    └── cloudwatch/
        └── main.tf         # CloudWatch log groups and alarms
```

### Justification

- **Separate modules per service**: Clear separation of concerns, easier to maintain and test
- **Single Lambda module**: All 5 Lambda functions share similar packaging and IAM role structure
- **Flat structure for simple resources**: DynamoDB, SQS, Cognito don't need submodules
- **Scripts directory**: Centralized import commands for documentation and automation
- **terraform.tfvars.example**: Template for developers to understand required variables

## Resource Dependencies Order

The following order must be respected for resource creation:

```
1. S3 Bucket (backend state) - must exist before Terraform initialization
2. IAM Module (api_role, orquestador_role, scan_worker_role, scoring_worker_role,
   notificador_role, eventbridge_scheduler_role, github_actions role + OIDC provider)
   - Must be created before the Lambda module (roles are required for Lambda execution roles)
   - Must be created before the EventBridge module (the Scheduler needs an IAM role to
     invoke the orquestador Lambda)
3. DynamoDB Tables (Empresas, Vacantes, UsuarioVacante, Entradas, Perfiles, Suscripciones, ScanJobs)
4. SQS Queues (scan-dlq, scan-queue, scoring-dlq, scoring-queue)
5. Lambda Functions (api, orquestador, scan-worker, scoring-worker, notificador)
6. Cognito User Pool (import only - already exists)
7. API Gateway (depends on Cognito User Pool ARN)
8. S3 Bucket (frontend assets)
9. CloudFront Distribution (depends on S3 bucket)
10. EventBridge Scheduler (depends on orquestador Lambda ARN and IAM module's eventbridge_scheduler_role)
11. SES Configuration (email identity)
12. CloudWatch Alarms (depends on Lambda and S3 resources)
```

### Terraform depends_on Usage

Explicit `depends_on` will be used where implicit dependencies are not sufficient:

```hcl
# Lambda function depends on IAM role
resource "aws_lambda_function" "api" {
  # ... configuration ...
  depends_on = [aws_iam_role.api-role]
}

# API Gateway depends on Cognito User Pool
resource "aws_api_gateway_authorizer" "cognito" {
  # ... configuration ...
  depends_on = [aws_cognito_user_pool.user_pool]
}

# CloudFront depends on S3 bucket
resource "aws_cloudfront_distribution" "frontend" {
  # ... configuration ...
  depends_on = [aws_s3_bucket.frontend]
}
```

## Import Commands for Existing Resources

The following 15 existing resources must be imported: 7 DynamoDB tables + 4 SQS queues +
1 Cognito User Pool + 1 Cognito App Client + 1 Cognito Hosted UI Domain + 1 Resource
Group = 15.

### DynamoDB Tables (7)

```bash
# Import commands for existing DynamoDB tables
terraform import aws_dynamodb_table.empresas arn:aws:dynamodb:us-east-1:123456789012:table/Empresas
terraform import aws_dynamodb_table.vacantes arn:aws:dynamodb:us-east-1:123456789012:table/Vacantes
terraform import aws_dynamodb_table.usuario_vacante arn:aws:dynamodb:us-east-1:123456789012:table/UsuarioVacante
terraform import aws_dynamodb_table.entradas arn:aws:dynamodb:us-east-1:123456789012:table/Entradas
terraform import aws_dynamodb_table.perfiles arn:aws:dynamodb:us-east-1:123456789012:table/Perfiles
terraform import aws_dynamodb_table.suscripciones arn:aws:dynamodb:us-east-1:123456789012:table/Suscripciones
terraform import aws_dynamodb_table.scan_jobs arn:aws:dynamodb:us-east-1:123456789012:table/ScanJobs
```

### SQS Queues (4)

```bash
# Import commands for existing SQS queues
terraform import aws_sqs_queue.scan_dlq https://sqs.us-east-1.amazonaws.com/123456789012/scan-dlq
terraform import aws_sqs_queue.scan_queue https://sqs.us-east-1.amazonaws.com/123456789012/scan-queue
terraform import aws_sqs_queue.scoring_dlq https://sqs.us-east-1.amazonaws.com/123456789012/scoring-dlq
terraform import aws_sqs_queue.scoring_queue https://sqs.us-east-1.amazonaws.com/123456789012/scoring-queue
```

### Cognito User Pool (1)

```bash
# Import command for existing Cognito User Pool
terraform import aws_cognito_user_pool.user_pool us-east-1_abcdefghi

# Import command for existing App Client (job-search-frontend)
# Format: <user_pool_id>/<client_id>
terraform import aws_cognito_user_pool_client.frontend us-east-1_LreFyDA2b/c7dt8acog5t0ifssh05eq0gc4

# Import command for existing Hosted UI Domain
terraform import aws_cognito_user_pool_domain.frontend job-search-assistant-mvp
```

### Resource Group (1)

The Resource Group must be declared in `main.tf` before it can be imported —
`terraform import` requires an existing resource address to bind to, it cannot
create one implicitly:

```hcl
resource "aws_resourcegroups_group" "job_search_assistant" {
  name = "job-search-assistant"

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [{ Key = "Proyecto", Values = ["job-search-assistant"] }]
    })
  }
}
```

```bash
# Import command for existing Resource Group
terraform import aws_resourcegroups_group.job_search_assistant arn:aws:resource-groups:us-east-1:<ACCOUNT_ID>:group/job-search-assistant
```

## Variable Definitions (variables.tf)

```hcl
variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod, hackathon)"
  type        = string
  default     = "hackathon"
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
  default     = "job-search-assistant"
}

variable "terraform_state_bucket" {
  description = "S3 bucket name for Terraform state storage (required)"
  type        = string
  # No default - user must specify
}

variable "terraform_state_key" {
  description = "S3 key for Terraform state file"
  type        = string
  default     = "terraform.tfstate"
}

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID (required, import only)"
  type        = string
  # No default - user must specify
}

variable "frontend_domain" {
  description = "Frontend domain for CloudFront and CORS"
  type        = string
  default     = "job-search-assistant.mvp"
}

variable "ses_email" {
  description = "Source email for SES (required for email sending)"
  type        = string
  # No default - user must specify
}

variable "scan_worker_timeout" {
  description = "Lambda timeout for scan-worker (seconds)"
  type        = number
  default     = 90
}

variable "scoring_worker_timeout" {
  description = "Lambda timeout for scoring-worker (seconds)"
  type        = number
  default     = 30
}

variable "billing_alarm_threshold" {
  description = "Monthly billing threshold in USD for billing alarm"
  type        = number
  default     = 500
}

variable "cors_origins" {
  description = "Comma-separated list of CORS allowed origins"
  type        = string
  default     = "http://localhost:5173"
}

variable "lambda_code_bucket" {
  description = "S3 bucket for Lambda function code"
  type        = string
  # No default - user must specify
}

variable "lambda_code_key_prefix" {
  description = "S3 key prefix for Lambda function code"
  type        = string
  default     = "lambda-code"
}

variable "orchestration_schedule_expression" {
  description = "EventBridge Scheduler expression for orquestador"
  type        = string
  default     = "cron(0 8,12,18 * * ? *)"
}
```

## Provider Configuration (providers.tf)

```hcl
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend configuration in backend.tf
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = var.project_name
    }
  }
}
```

## Backend Configuration (backend.tf)

```hcl
terraform {
  backend "s3" {
    bucket         = var.terraform_state_bucket
    key            = var.terraform_state_key
    region         = var.aws_region
    encrypt        = true
    dynamodb_table = "terraform-state-lock" # Optional: enable state locking
  }
}
```

## Security Considerations

### Secrets Handling

- **Never commit secrets**: `terraform.tfvars` is gitignored
- **Environment variables**: Use `sensitive = true` for sensitive variables
- **IAM policies**: Follow least privilege principle

### Least Privilege IAM

Each Lambda gets its own IAM role with minimal permissions:

- **api-role**: API Gateway invoke permissions only
- **orquestador-role**: DynamoDB, SQS_Scan, Cognito permissions
- **scan-worker-role**: DynamoDB, SQS_Scan, SQS_Scoring, Bedrock permissions
- **scoring-worker-role**: DynamoDB, SQS_Scoring, Bedrock permissions
- **notificador-role**: SES permissions only

### Prevent Destroy Protection

```hcl
resource "aws_dynamodb_table" "empresas" {
  # ... configuration ...
  
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cognito_user_pool" "user_pool" {
  # ... configuration ...
  
  lifecycle {
    prevent_destroy = true
  }
}
```

### Encryption

- S3 default encryption enabled
- DynamoDB encryption at rest enabled
- SQS server-side encryption optional

## CloudFront SPA Support

### Error Responses Configuration

```hcl
resource "aws_cloudfront_distribution" "frontend" {
  # ... other configuration ...
  
  default_cache_behavior {
    # ... other configuration ...
  }
  
  # SPA routing support
  custom_error_response {
    error_code            = 403
    response_page_path    = "/index.html"
    response_code         = 200
    error_caching_min_ttl = 300
  }
  
  custom_error_response {
    error_code            = 404
    response_page_path    = "/index.html"
    response_code         = 200
    error_caching_min_ttl = 300
  }
}
```

### Viewer Protocol Policy

```hcl
default_cache_behavior {
  # ... other configuration ...
  
  viewer_protocol_policy = "redirect-to-https"
  
  # Forward all headers for SPA routing
  forwarded_values {
    headers = ["*"]
    query_string = true
    cookies {
      forward = "all"
    }
  }
}
```

## SQS Visibility Timeout Calculation

### Source

The Lambda timeouts and the resulting visibility timeout values below (scan-worker:
90s → 540s, scoring-worker: 30s → 180s) are not assumptions or placeholders invented
by this Terraform design. They come directly from `backend-scan-y-scoring/design.md`,
section "SQS Queue Configuration & Visibility Timeout Formulas", which already fixes
these exact numbers. This design only applies the `6 × Lambda Timeout` formula
mechanically to values that are sourced from that document.

### Formula

```
Visibility Timeout = 6 × Lambda Timeout
```

### Calculated Values

| Queue | Lambda Timeout | Visibility Timeout | Reasoning |
|-------|---------------|-------------------|-----------|
| scan-queue | 90 seconds (scan-worker) | 540 seconds (9 min) | 6 × 90s = 540s |
| scoring-queue | 30 seconds (scoring-worker) | 180 seconds (3 min) | 6 × 30s = 180s |

### DLQ Configuration

Both DLQs have `maxReceiveCount = 3`:

```hcl
resource "aws_sqs_queue" "scan_queue" {
  # ... other configuration ...
  
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scan_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "scoring_queue" {
  # ... other configuration ...
  
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scoring_dlq.arn
    maxReceiveCount     = 3
  })
}
```

## Lambda Environment Variables

### From backend-scan-y-scoring Design

All Lambda functions read Bedrock Model IDs from environment variables (never hardcoded):

```hcl
resource "aws_lambda_function" "scan_worker" {
  # ... other configuration ...
  
  environment {
    variables = {
      BEDROCK_REGION         = "us-east-1"
      BEDROCK_MODEL_SMALL    = var.bedrock_model_small
      BEDROCK_MODEL_MID      = var.bedrock_model_mid
      DYNAMODB_TABLE_EMPRESA = aws_dynamodb_table.empresas.name
      DYNAMODB_TABLE_VACANTE = aws_dynamodb_table.vacantes.name
      DYNAMODB_TABLE_SCAN_JOB = aws_dynamodb_table.scan_jobs.name
      SQS_QUEUE_SCAN_URL     = aws_sqs_queue.scan_queue.url
      SQS_QUEUE_SCORING_URL  = aws_sqs_queue.scoring_queue.url
      PREFILTRO_TOKEN_THRESHOLD = var.prefiltro_token_threshold
      HTML_CLEAN_MAX_KB      = var.html_clean_max_kb
      LOG_LEVEL              = var.log_level
    }
  }
}

resource "aws_lambda_function" "scoring_worker" {
  # ... other configuration ...
  
  environment {
    variables = {
      BEDROCK_REGION         = "us-east-1"
      BEDROCK_MODEL_SMALL    = var.bedrock_model_small
      BEDROCK_MODEL_MID      = var.bedrock_model_mid
      DYNAMODB_TABLE_PERFIL  = aws_dynamodb_table.perfiles.name
      DYNAMODB_TABLE_USUARIO_VACANTE = aws_dynamodb_table.usuario_vacante.name
      DYNAMODB_TABLE_VACANTE = aws_dynamodb_table.vacantes.name
      DYNAMODB_TABLE_EMPRESA = aws_dynamodb_table.empresas.name
      SQS_QUEUE_SCORING_URL  = aws_sqs_queue.scoring_queue.url
      PREFILTRO_TOKEN_THRESHOLD = var.prefiltro_token_threshold
      LOG_LEVEL              = var.log_level
    }
  }
}

resource "aws_lambda_function" "api" {
  # ... other configuration ...
  
  environment {
    variables = {
      BEDROCK_REGION         = "us-east-1"
      BEDROCK_MODEL_SMALL    = var.bedrock_model_small
      BEDROCK_MODEL_MID      = var.bedrock_model_mid
      DYNAMODB_TABLE_EMPRESA = aws_dynamodb_table.empresas.name
      DYNAMODB_TABLE_VACANTE = aws_dynamodb_table.vacantes.name
      DYNAMODB_TABLE_USUARIO_VACANTE = aws_dynamodb_table.usuario_vacante.name
      DYNAMODB_TABLE_SCAN_JOB = aws_dynamodb_table.scan_jobs.name
      DYNAMODB_TABLE_SUSCRIPCIONES = aws_dynamodb_table.suscripciones.name
      DYNAMODB_TABLE_PERFIL  = aws_dynamodb_table.perfiles.name
      COGNITO_USER_POOL_ID   = var.cognito_user_pool_id
      SQS_QUEUE_SCAN_URL     = aws_sqs_queue.scan_queue.url
      SQS_QUEUE_SCORING_URL  = aws_sqs_queue.scoring_queue.url
      SES_EMAIL              = var.ses_email
      CORS_ORIGINS           = var.cors_origins
      LOG_LEVEL              = var.log_level
    }
  }
}

resource "aws_lambda_function" "orquestador" {
  # ... other configuration ...
  
  environment {
    variables = {
      BEDROCK_REGION         = "us-east-1"
      BEDROCK_MODEL_SMALL    = var.bedrock_model_small
      BEDROCK_MODEL_MID      = var.bedrock_model_mid
      DYNAMODB_TABLE_EMPRESA = aws_dynamodb_table.empresas.name
      DYNAMODB_TABLE_VACANTE = aws_dynamodb_table.vacantes.name
      DYNAMODB_TABLE_SCAN_JOB = aws_dynamodb_table.scan_jobs.name
      DYNAMODB_TABLE_SUSCRIPCIONES = aws_dynamodb_table.suscripciones.name
      DYNAMODB_TABLE_PERFIL  = aws_dynamodb_table.perfiles.name
      SQS_QUEUE_SCAN_URL     = aws_sqs_queue.scan_queue.url
      LOG_LEVEL              = var.log_level
    }
  }
}

resource "aws_lambda_function" "notificador" {
  # ... other configuration ...
  
  environment {
    variables = {
      SES_EMAIL              = var.ses_email
      LOG_LEVEL              = var.log_level
    }
  }
}
```

### Additional Variables for Environment Variables

```hcl
# NOTE: For cross-region inference in us-east-1, several current Bedrock models are
# only invocable via inference profiles, which require the region-prefixed model ID
# (e.g. "us.anthropic.claude-...") — NOT the bare base model ID
# (e.g. "anthropic.claude-..." alone). Using the bare ID fails with a non-obvious error.
# PLACEHOLDER: the exact Haiku model ID below is pending confirmation from the AWS
# console/Bedrock model catalog before this value is finalized.
variable "bedrock_model_small" {
  description = "Bedrock model ID for small model (Claude Haiku). Must use the us.-prefixed cross-region inference profile ID in us-east-1, not the bare base model ID."
  type        = string
  # No default - read from .env or user input
}

# NOTE: same cross-region inference profile caveat as bedrock_model_small above applies here.
variable "bedrock_model_mid" {
  description = "Bedrock model ID for mid model (Claude Sonnet). Must use the us.-prefixed cross-region inference profile ID in us-east-1, not the bare base model ID."
  type        = string
  # No default - read from .env or user input
}

variable "prefiltro_token_threshold" {
  description = "Token overlap threshold for prefiltro_cargos"
  type        = number
  default     = 1
}

variable "html_clean_max_kb" {
  description = "Maximum HTML size in KB before truncation"
  type        = number
  default     = 100
}

variable "log_level" {
  description = "Logging level (DEBUG, INFO, WARN, ERROR)"
  type        = string
  default     = "INFO"
}
```

## IAM Module (modules/iam/main.tf)

All IAM roles and policies — the 5 per-Lambda roles below, the EventBridge Scheduler
invoke role, and the GitHub Actions OIDC role (see "GitHub Actions OIDC Role" further
below) — live together in `modules/iam/main.tf`. Centralizing them here means the
Lambda module and the EventBridge module only ever reference role ARNs as inputs; they
never declare `aws_iam_role` resources themselves. This matches the dependency order in
"Resource Dependencies Order": the IAM module must exist before both Lambda and
EventBridge.

### API Role Permissions

```hcl
resource "aws_iam_role" "api_role" {
  name = "job-search-api-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "api_policy" {
  name = "job-search-api-policy"
  role = aws_iam_role.api_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.empresas.arn,
          aws_dynamodb_table.vacantes.arn,
          aws_dynamodb_table.usuario_vacante.arn,
          aws_dynamodb_table.perfiles.arn,
          aws_dynamodb_table.suscripciones.arn,
          aws_dynamodb_table.scan_jobs.arn
        ]
      },
      # Bedrock (invoke only, no model ARN specified - user must configure)
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      },
      # API Gateway invoke (for integration)
      {
        Effect = "Allow"
        Action = [
          "execute-api:Invoke"
        ]
        Resource = "*"
      }
    ]
  })
}
```

### Orquestador Role Permissions

```hcl
resource "aws_iam_role" "orquestador_role" {
  name = "job-search-orquestador-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "orquestador_policy" {
  name = "job-search-orquestador-policy"
  role = aws_iam_role.orquestador_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.empresas.arn,
          aws_dynamodb_table.vacantes.arn,
          aws_dynamodb_table.scan_jobs.arn,
          aws_dynamodb_table.suscripciones.arn,
          aws_dynamodb_table.perfil.arn
        ]
      },
      # SQS (publish to scan queue)
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.scan_queue.arn
      }
    ]
  })
}
```

### Scan Worker Role Permissions

```hcl
resource "aws_iam_role" "scan_worker_role" {
  name = "job-search-scan-worker-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "scan_worker_policy" {
  name = "job-search-scan-worker-policy"
  role = aws_iam_role.scan_worker_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.empresas.arn,
          aws_dynamodb_table.vacantes.arn,
          aws_dynamodb_table.scan_jobs.arn
        ]
      },
      # SQS (receive from scan queue, send to scoring queue)
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:SendMessage"
        ]
        Resource = [
          aws_sqs_queue.scan_queue.arn,
          aws_sqs_queue.scoring_queue.arn
        ]
      },
      # Bedrock
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      }
    ]
  })
}
```

### Scoring Worker Role Permissions

```hcl
resource "aws_iam_role" "scoring_worker_role" {
  name = "job-search-scoring-worker-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "scoring_worker_policy" {
  name = "job-search-scoring-worker-policy"
  role = aws_iam_role.scoring_worker_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.perfiles.arn,
          aws_dynamodb_table.usuario_vacante.arn,
          aws_dynamodb_table.vacantes.arn,
          aws_dynamodb_table.empresas.arn
        ]
      },
      # SQS (receive from scoring queue)
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.scoring_queue.arn
      },
      # Bedrock
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      }
    ]
  })
}
```

### Notificador Role Permissions

```hcl
resource "aws_iam_role" "notificador_role" {
  name = "job-search-notificador-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "notificador_policy" {
  name = "job-search-notificador-policy"
  role = aws_iam_role.notificador_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # SES
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      }
    ]
  })
}
```

## Out of Scope Items

The following items are explicitly out of scope for this Terraform infrastructure spec:

1. **GitHub Actions workflow YAML**: Only the IAM role for OIDC is included (workflow YAML must be created separately)
2. **Manual S3 bucket creation**: Terraform cannot manage its own initial backend (user must create S3 bucket manually)
3. **Manual SES email verification**: Each email identity must be manually verified by clicking a link sent to the email
4. **Frontend code**: React SPA source code is out of scope
5. **Backend code**: Python Lambda function source code is out of scope
6. **Database migrations**: Schema changes and data migrations are out of scope
7. **Data seeding**: Initial data population is out of scope
8. **Custom domain for CloudFront**: not part of project scope. The distribution uses the default `*.cloudfront.net` domain with its built-in certificate (`cloudfront_default_certificate = true`) — no ACM certificate request, no DNS validation, no custom domain. The only post-deploy step involving Cognito is updating its Callback URLs to point to the real CloudFront domain.
9. **Route53 hosted zone or DNS configuration**: DNS setup is out of scope (there is no custom domain to point DNS at)
10. **VPC, subnets, security groups**: Lambda functions run in the default VPC
11. **KMS keys for encryption**: S3 default encryption is sufficient
12. **CloudWatch dashboards**: Only alarms are included (dashboards are optional)
13. **Lambda layers or provisioned concurrency**: Not required for this design
## DynamoDB Tables Module (modules/dynamodb/main.tf)

### Table 1: Empresas

```hcl
resource "aws_dynamodb_table" "empresas" {
  name         = "Empresas"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "companyId"
  
  attribute {
    name = "companyId"
    type = "S"
  }
  
  # Prevent accidental deletion
  lifecycle {
    prevent_destroy = true
  }
}
```

### Table 2: Vacantes

```hcl
resource "aws_dynamodb_table" "vacantes" {
  name         = "Vacantes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "companyId"
  range_key    = "vacancyId"
  
  attribute {
    name = "companyId"
    type = "S"
  }
  
  attribute {
    name = "vacancyId"
    type = "S"
  }
  
  # TTL for automatic cleanup
  ttl {
    enabled         = true
    name            = "ttl"
    default_ttl     = 31536000 # 1 year
  }
  
  lifecycle {
    prevent_destroy = true
  }
}
```

### Table 3: UsuarioVacante

```hcl
resource "aws_dynamodb_table" "usuario_vacante" {
  name         = "UsuarioVacante"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "sk"
  
  attribute {
    name = "userId"
    type = "S"
  }
  
  attribute {
    name = "sk"
    type = "S"
  }
  
  # Prevent accidental deletion: holds all user-vacancy relationship state
  lifecycle {
    prevent_destroy = true
  }
}
```

### Table 4: Entradas

```hcl
resource "aws_dynamodb_table" "entradas" {
  name         = "Entradas"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "entryId"
  
  attribute {
    name = "pk"
    type = "S"
  }
  
  attribute {
    name = "entryId"
    type = "S"
  }
  
  # Prevent accidental deletion: holds the interview question bank, the project's innovation differentiator
  lifecycle {
    prevent_destroy = true
  }
}
```

### Table 5: Perfiles

```hcl
resource "aws_dynamodb_table" "perfiles" {
  name         = "Perfiles"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  
  attribute {
    name = "userId"
    type = "S"
  }
  
  # Prevent accidental deletion: holds parsed CVs
  lifecycle {
    prevent_destroy = true
  }
}
```

### Table 6: Suscripciones

```hcl
resource "aws_dynamodb_table" "suscripciones" {
  name         = "Suscripciones"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "companyId"
  
  attribute {
    name = "userId"
    type = "S"
  }
  
  attribute {
    name = "companyId"
    type = "S"
  }
  
  # GSI for querying by company
  global_secondary_index {
    name            = "porEmpresa"
    hash_key        = "companyId"
    range_key       = "userId"
    projection_type = "ALL"
  }
  
  # Prevent accidental deletion: holds all user relationship state
  lifecycle {
    prevent_destroy = true
  }
}
```

All 7 tables carry `prevent_destroy = true` for the same reason: there is no
principled basis for protecting some tables and not others — losing any one of them
(including `UsuarioVacante`, `Entradas`, `Perfiles`, and `Suscripciones`) is equally
catastrophic and unrecoverable.

### Table 7: ScanJobs

```hcl
resource "aws_dynamodb_table" "scan_jobs" {
  name         = "ScanJobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "jobId"
  
  attribute {
    name = "jobId"
    type = "S"
  }
  
  # TTL for zombie cleanup
  ttl {
    enabled         = true
    name            = "ttl"
    default_ttl     = 86400 # 24 hours
  }
  
  lifecycle {
    prevent_destroy = true
  }
}
```

## SQS Queues Module (modules/sqs/main.tf)

### DLQ 1: scan-dlq

```hcl
resource "aws_sqs_queue" "scan_dlq" {
  name = "scan-dlq"
}
```

### Main Queue 1: scan-queue

```hcl
resource "aws_sqs_queue" "scan_queue" {
  name = "scan-queue"
  
  # Visibility timeout = 6 × Lambda timeout (90s) = 540s
  visibility_timeout_seconds        = 540
  message_retention_seconds         = 1209600 # 14 days
  delay_seconds                     = 0
  receive_wait_time_seconds         = 10
  
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scan_dlq.arn
    maxReceiveCount     = 3
  })
}
```

### DLQ 2: scoring-dlq

```hcl
resource "aws_sqs_queue" "scoring_dlq" {
  name = "scoring-dlq"
}
```

### Main Queue 2: scoring-queue

```hcl
resource "aws_sqs_queue" "scoring_queue" {
  name = "scoring-queue"
  
  # Visibility timeout = 6 × Lambda timeout (30s) = 180s
  visibility_timeout_seconds        = 180
  message_retention_seconds         = 1209600 # 14 days
  delay_seconds                     = 0
  receive_wait_time_seconds         = 10
  
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scoring_dlq.arn
    maxReceiveCount     = 3
  })
}
```

## Lambda Functions Module (modules/lambda/main.tf)

### Lambda 1: api (FastAPI + Mangum)

```hcl
resource "aws_lambda_function" "api" {
  function_name = "job-search-api"
  runtime       = "python3.12"
  handler       = "main.handler"
  role          = aws_iam_role.api_role.arn
  filename      = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256
  
  timeout = 10
  memory_size = 512
  
  environment {
    variables = {
      BEDROCK_REGION         = var.bedrock_region
      BEDROCK_MODEL_SMALL    = var.bedrock_model_small
      BEDROCK_MODEL_MID      = var.bedrock_model_mid
      DYNAMODB_TABLE_EMPRESA = var.dynamodb_table_empresas
      DYNAMODB_TABLE_VACANTE = var.dynamodb_table_vacantes
      DYNAMODB_TABLE_USUARIO_VACANTE = var.dynamodb_table_usuario_vacante
      DYNAMODB_TABLE_SCAN_JOB = var.dynamodb_table_scan_jobs
      DYNAMODB_TABLE_SUSCRIPCIONES = var.dynamodb_table_suscripciones
      DYNAMODB_TABLE_PERFIL  = var.dynamodb_table_perfiles
      COGNITO_USER_POOL_ID   = var.cognito_user_pool_id
      SQS_QUEUE_SCAN_URL     = var.sqs_queue_scan_url
      SQS_QUEUE_SCORING_URL  = var.sqs_queue_scoring_url
      SES_EMAIL              = var.ses_email
      CORS_ORIGINS           = var.cors_origins
      LOG_LEVEL              = var.log_level
    }
  }
}
```

### Lambda 2: orquestador (EventBridge Scheduler)

```hcl
resource "aws_lambda_function" "orquestador" {
  function_name = "job-search-orquestador"
  runtime       = "python3.12"
  handler       = "main.handler"
  role          = aws_iam_role.orquestador_role.arn
  filename      = data.archive_file.orquestador.output_path
  source_code_hash = data.archive_file.orquestador.output_base64sha256
  
  timeout = 60
  memory_size = 512
  
  environment {
    variables = {
      BEDROCK_REGION         = var.bedrock_region
      BEDROCK_MODEL_SMALL    = var.bedrock_model_small
      BEDROCK_MODEL_MID      = var.bedrock_model_mid
      DYNAMODB_TABLE_EMPRESA = var.dynamodb_table_empresas
      DYNAMODB_TABLE_VACANTE = var.dynamodb_table_vacantes
      DYNAMODB_TABLE_SCAN_JOB = var.dynamodb_table_scan_jobs
      DYNAMODB_TABLE_SUSCRIPCIONES = var.dynamodb_table_suscripciones
      DYNAMODB_TABLE_PERFIL  = var.dynamodb_table_perfiles
      SQS_QUEUE_SCAN_URL     = var.sqs_queue_scan_url
      LOG_LEVEL              = var.log_level
    }
  }
}
```

### Lambda 3: scan-worker

```hcl
resource "aws_lambda_function" "scan_worker" {
  function_name = "job-search-scan-worker"
  runtime       = "python3.12"
  handler       = "main.handler"
  role          = aws_iam_role.scan_worker_role.arn
  filename      = data.archive_file.scan_worker.output_path
  source_code_hash = data.archive_file.scan_worker.output_base64sha256
  
  # Timeout: 90s, Memory: 1024MB (from backend-scan-y-scoring design)
  timeout = 90
  memory_size = 1024
  
  reserved_concurrent_executions = 5
  
  environment {
    variables = {
      BEDROCK_REGION         = var.bedrock_region
      BEDROCK_MODEL_SMALL    = var.bedrock_model_small
      BEDROCK_MODEL_MID      = var.bedrock_model_mid
      DYNAMODB_TABLE_EMPRESA = var.dynamodb_table_empresas
      DYNAMODB_TABLE_VACANTE = var.dynamodb_table_vacantes
      DYNAMODB_TABLE_SCAN_JOB = var.dynamodb_table_scan_jobs
      SQS_QUEUE_SCAN_URL     = var.sqs_queue_scan_url
      SQS_QUEUE_SCORING_URL  = var.sqs_queue_scoring_url
      PREFILTRO_TOKEN_THRESHOLD = var.prefiltro_token_threshold
      HTML_CLEAN_MAX_KB      = var.html_clean_max_kb
      LOG_LEVEL              = var.log_level
    }
  }
}
```

### Lambda 4: scoring-worker

```hcl
resource "aws_lambda_function" "scoring_worker" {
  function_name = "job-search-scoring-worker"
  runtime       = "python3.12"
  handler       = "main.handler"
  role          = aws_iam_role.scoring_worker_role.arn
  filename      = data.archive_file.scoring_worker.output_path
  source_code_hash = data.archive_file.scoring_worker.output_base64sha256
  
  # Timeout: 30s, Memory: 1024MB (from backend-scan-y-scoring design)
  timeout = 30
  memory_size = 1024
  
  reserved_concurrent_executions = 3
  
  environment {
    variables = {
      BEDROCK_REGION         = var.bedrock_region
      BEDROCK_MODEL_SMALL    = var.bedrock_model_small
      BEDROCK_MODEL_MID      = var.bedrock_model_mid
      DYNAMODB_TABLE_PERFIL  = var.dynamodb_table_perfiles
      DYNAMODB_TABLE_USUARIO_VACANTE = var.dynamodb_table_usuario_vacante
      DYNAMODB_TABLE_VACANTE = var.dynamodb_table_vacantes
      DYNAMODB_TABLE_EMPRESA = var.dynamodb_table_empresas
      SQS_QUEUE_SCORING_URL  = var.sqs_queue_scoring_url
      PREFILTRO_TOKEN_THRESHOLD = var.prefiltro_token_threshold
      LOG_LEVEL              = var.log_level
    }
  }
}
```

### Lambda 5: notificador (SES)

```hcl
resource "aws_lambda_function" "notificador" {
  function_name = "job-search-notificador"
  runtime       = "python3.12"
  handler       = "main.handler"
  role          = aws_iam_role.notificador_role.arn
  filename      = data.archive_file.notificador.output_path
  source_code_hash = data.archive_file.notificador.output_base64sha256
  
  timeout = 30
  memory_size = 512
  
  environment {
    variables = {
      SES_EMAIL              = var.ses_email
      LOG_LEVEL              = var.log_level
    }
  }
}
```

## API Gateway Module (modules/api-gateway/main.tf)

```hcl
resource "aws_api_gateway_rest_api" "api" {
  name        = "job-search-api"
  description = "Job Search Assistant API"
}

resource "aws_api_gateway_resource" "api_root" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "api_proxy" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_resource.api_root.id
  http_method   = "ANY"
  authorization = "COGNITO"
  
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "api_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_method.api_proxy.resource_id
  http_method             = aws_api_gateway_method.api_proxy.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.api.invoke_arn
}

resource "aws_api_gateway_authorizer" "cognito" {
  name          = "cognito-authorizer"
  type          = "COGNITO"
  rest_api_id   = aws_api_gateway_rest_api.api.id
  provider_arns = [aws_cognito_user_pool.user_pool.arn]
}

resource "aws_api_gateway_stage" "api_stage" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  stage_name  = "prod"
}

resource "aws_api_gateway_method_settings" "api_settings" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  stage_name  = aws_api_gateway_stage.api_stage.stage_name
  method_path = "*/*"
  
  settings {
    metrics_enabled    = true
    logging_level      = "INFO"
    data_trace_enabled = true
    throttling_burst_limit = 500
    throttling_rate_limit  = 1000
  }
}
```

## Cognito Module (modules/cognito/main.tf)

```hcl
# Note: This module imports existing Cognito User Pool
# The actual User Pool creation is not done here (would lose existing users)

resource "aws_cognito_user_pool" "user_pool" {
  # Imported from existing resource
  # No configuration needed for import-only
}

resource "aws_cognito_user_pool_client" "frontend" {
  # IMPORTED, not created: this App Client already exists in AWS
  # (client_name "job-search-frontend", no secret, PKCE-only OAuth flow).
  # Attributes below must match the real client exactly or Terraform will
  # attempt to modify/recreate it on the first plan after import.
  user_pool_id = var.cognito_user_pool_id

  client_name                   = "job-search-frontend"
  generate_secret               = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows           = ["code"] # PKCE-only. "implicit" is intentionally excluded: it leaks tokens in the URL fragment. CONFIRMED via `aws cognito-idp describe-user-pool-client` on 2026-07-27: AllowedOAuthFlows=["code"].
  allowed_oauth_scopes          = ["email", "openid", "profile"]
  callback_urls                 = ["http://localhost:5173/callback"]
  logout_urls                   = ["http://localhost:5173/logout"]
  explicit_auth_flows           = ["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  refresh_token_validity        = 60 # CONFIRMED via `aws cognito-idp describe-user-pool-client` on 2026-07-27. Note: infraestructura-desplegada.md's creation-command record said 30, but the live resource has been changed since to 60 — the .md log is a point-in-time creation record, not the current state. Always trust the live AWS value over the static log when they conflict.
  supported_identity_providers  = ["COGNITO"] # CONFIRMED via `aws cognito-idp describe-user-pool-client` on 2026-07-27: SupportedIdentityProviders=["COGNITO"], matches real creation command.
  # prevent_user_existence_errors intentionally OMITTED: `aws cognito-idp describe-user-pool-client`
  # confirmed the live value is null (never configured on this resource). Omitting the argument
  # here matches that null state and avoids Terraform attempting to set ENABLED/LEGACY on apply.
  enable_token_revocation       = true
}

resource "aws_cognito_user_pool_domain" "frontend" {
  user_pool_id = var.cognito_user_pool_id
  domain       = "job-search-assistant-mvp"
}
```

### Outputs (modules/cognito/outputs.tf)

```hcl
output "hosted_ui_domain" {
  description = "Cognito Hosted UI domain, without protocol"
  value       = aws_cognito_user_pool_domain.frontend.domain
}
```

## S3 + CloudFront Module (modules/s3-cloudfront/main.tf)

### S3 Bucket for Frontend

```hcl
resource "aws_s3_bucket" "frontend" {
  bucket = var.frontend_bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action = [
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.frontend.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
          }
        }
      }
    ]
  })
}
```

### CloudFront Distribution

```hcl
resource "aws_cloudfront_distribution" "frontend" {
  origin {
    domain_name = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id   = "s3-frontend"
    
    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.cloudfront_identity.cloudfront_access_identity_path
    }
  }
  
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Job Search Assistant Frontend"
  default_root_object = "index.html"
  
  default_cache_behavior {
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "s3-frontend"
    
    forwarded_values {
      query_string = true
      headers = ["*"]
      cookies {
        forward = "all"
      }
    }
    
    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
  }
  
  # SPA routing support - map 403 and 404 to index.html
  custom_error_response {
    error_code            = 403
    response_page_path    = "/index.html"
    response_code         = 200
    error_caching_min_ttl = 300
  }
  
  custom_error_response {
    error_code            = 404
    response_page_path    = "/index.html"
    response_code         = 200
    error_caching_min_ttl = 300
  }
  
  price_class = "PriceClass_100"
  
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
  
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

resource "aws_cloudfront_origin_access_identity" "cloudfront_identity" {
  comment = "Job Search Assistant CloudFront OAI"
}
```

## EventBridge Scheduler Module (modules/eventbridge/main.tf)

The IAM role used by the Scheduler to invoke the `orquestador` Lambda
(`eventbridge_scheduler_role`) is declared in `modules/iam/main.tf`, not here — this
module only consumes the role ARN as an input variable. This is why the IAM module must
be created before the EventBridge module (see "Resource Dependencies Order").

```hcl
# IAM role for EventBridge Scheduler (declared in modules/iam/main.tf, referenced here via var.eventbridge_scheduler_role_arn)
# resource "aws_iam_role" "eventbridge_scheduler_role" { ... }        -> lives in modules/iam
# resource "aws_iam_role_policy" "eventbridge_scheduler_policy" { ... } -> lives in modules/iam

# EventBridge Scheduler
resource "aws_scheduler_schedule" "orquestador" {
  name = "job-search-orquestador-schedule"
  
  flexible_time_window {
    mode = "OFF"
  }
  
  schedule_expression = var.orchestration_schedule_expression
  
  target {
    arn      = aws_lambda_function.orquestador.arn
    role_arn = var.eventbridge_scheduler_role_arn

    input = jsonencode({
      source = "scheduled"
    })
  }
}
```

For reference, the role and policy declared in `modules/iam/main.tf`:

```hcl
resource "aws_iam_role" "eventbridge_scheduler_role" {
  name = "job-search-eventbridge-scheduler-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_scheduler_policy" {
  name = "job-search-eventbridge-scheduler-policy"
  role = aws_iam_role.eventbridge_scheduler_role.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = aws_lambda_function.orquestador.arn
      }
    ]
  })
}
```

## SES Module (modules/ses/main.tf)

```hcl
# Email identity (must be manually verified by clicking link sent to email)
resource "aws_ses_email_identity" "team_emails" {
  for_each = toset(var.ses_team_emails)
  
  email = each.value
}

# Sandbox mode documentation
# - 200 emails/day
# - 1 message/second
# - Production access must be requested separately (approx 24h approval)
```

## CloudWatch Module (modules/cloudwatch/main.tf)

### Log Groups

```hcl
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/job-search-api"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "orquestador" {
  name              = "/aws/lambda/job-search-orquestador"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "scan_worker" {
  name              = "/aws/lambda/job-search-scan-worker"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "scoring_worker" {
  name              = "/aws/lambda/job-search-scoring-worker"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "notificador" {
  name              = "/aws/lambda/job-search-notificador"
  retention_in_days = 7
}
```

### Alarms

```hcl
# Lambda error alarm
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "job-search-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "This metric monitors Lambda function errors"
  
  dimensions = {
    FunctionName = aws_lambda_function.api.function_name
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# Lambda duration alarm (p95 > 50s)
resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  alarm_name          = "job-search-lambda-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = 50000
  alarm_description   = "This metric monitors Lambda function duration"
  
  dimensions = {
    FunctionName = aws_lambda_function.api.function_name
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# Billing alarm
resource "aws_cloudwatch_metric_alarm" "billing" {
  alarm_name          = "job-search-billing-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = 86400
  statistic           = "Maximum"
  threshold           = var.billing_alarm_threshold
  alarm_description   = "This metric monitors estimated AWS charges"
  
  dimensions = {
    Currency = "USD"
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}
```

## GitHub Actions OIDC Role (modules/iam/main.tf)

This role, together with its OIDC provider, is declared inside `modules/iam/main.tf`
alongside the 5 per-Lambda roles and the EventBridge Scheduler invoke role — not in the
root `main.tf`. Consolidating all IAM resources into a single module keeps role/policy
ownership consistent and avoids duplicate `aws_iam_openid_connect_provider` resources
if the OIDC provider is ever needed by another role.

```hcl
# OIDC provider for GitHub Actions (one per AWS account)
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# IAM role for GitHub Actions OIDC
resource "aws_iam_role" "github_actions" {
  name = "job-search-github-actions-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = "repo:organization/job-search-assistant:ref:refs/heads/main"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "github_actions_policy" {
  name = "job-search-github-actions-policy"
  role = aws_iam_role.github_actions.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3: state and code
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.terraform_state_bucket}",
          "arn:aws:s3:::${var.terraform_state_bucket}/*"
        ]
      },
      # Lambda
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction",
          "lambda:UpdateFunctionCode"
        ]
        Resource = [
          aws_lambda_function.api.arn,
          aws_lambda_function.orquestador.arn,
          aws_lambda_function.scan_worker.arn,
          aws_lambda_function.scoring_worker.arn,
          aws_lambda_function.notificador.arn
        ]
      },
      # DynamoDB
      {
        Effect = "Allow"
        Action = [
          "dynamodb:CreateTable",
          "dynamodb:DescribeTable",
          "dynamodb:DeleteTable",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = "*"
      },
      # SQS
      {
        Effect = "Allow"
        Action = [
          "sqs:CreateQueue",
          "sqs:DeleteQueue",
          "sqs:SetQueueAttributes",
          "sqs:GetQueueAttributes",
          "sqs:SendMessage",
          "sqs:ReceiveMessage"
        ]
        Resource = "*"
      },
      # Cognito
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminSetUserPassword",
          "cognito-idp:DescribeUserPool",
          "cognito-idp:CreateUserPoolClient"
        ]
        Resource = "*"
      },
      # API Gateway
      {
        Effect = "Allow"
        Action = [
          "apigateway:GET",
          "apigateway:POST",
          "apigateway:PUT",
          "apigateway:DELETE"
        ]
        Resource = "*"
      },
      # CloudFront
      {
        Effect = "Allow"
        Action = [
          "cloudfront:CreateDistribution",
          "cloudfront:UpdateDistribution",
          "cloudfront:CreateInvalidation"
        ]
        Resource = "*"
      },
      # IAM
      {
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:AttachRolePolicy",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:DeleteRole"
        ]
        Resource = "*"
      }
    ]
  })
}
```

## Outputs

```hcl
# Lambda function ARNs
output "api_lambda_arn" {
  value = aws_lambda_function.api.arn
}

output "orquestador_lambda_arn" {
  value = aws_lambda_function.orquestador.arn
}

output "scan_worker_lambda_arn" {
  value = aws_lambda_function.scan_worker.arn
}

output "scoring_worker_lambda_arn" {
  value = aws_lambda_function.scoring_worker.arn
}

output "notificador_lambda_arn" {
  value = aws_lambda_function.notificador.arn
}

# SQS queue URLs
output "scan_queue_url" {
  value = aws_sqs_queue.scan_queue.url
}

output "scoring_queue_url" {
  value = aws_sqs_queue.scoring_queue.url
}

# CloudFront distribution domain
output "cloudfront_domain" {
  value = aws_cloudfront_distribution.frontend.domain_name
}

# CloudFront distribution ID
output "cloudfront_id" {
  value = aws_cloudfront_distribution.frontend.id
}

# GitHub Actions role ARN
output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}

# S3 bucket name
output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

# Cognito Hosted UI domain (frontend needs this to build the login URL)
output "cognito_hosted_ui_domain" {
  value = "${module.cognito.hosted_ui_domain}.auth.${var.aws_region}.amazoncognito.com"
}
```

## Next Steps

After this design document is complete, the next phases are:

1. **Requirements Verification**: Review and validate all requirements are covered
2. **Design Review**: Get stakeholder approval on the design
3. **Task Breakdown**: Break down implementation into specific tasks with acceptance criteria
4. **Implementation**: Write Terraform code following the design
5. **Testing**: Run `terraform validate`, `terraform fmt`, and `terraform plan`
6. **Documentation**: Update README.md with setup instructions

## References

- AWS Terraform Provider Documentation: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- Terraform Best Practices: https://terraform.io/docs/configuration/best-practices/
- AWS Well-Architected Framework: https://aws.amazon.com/architecture/well-architected/
- Backend-Scan-Y-Scoring Design: `backend-scan-y-scoring/design.md`
