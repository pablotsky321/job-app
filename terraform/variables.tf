# Variables for job-search-assistant Terraform Infrastructure
#
# This file aggregates all input variables from all modules into a single location.
# Variables are grouped logically for easier navigation and maintenance.
#
# Sensitive variables (marked with sensitive = true) should never be printed in logs.
# Required variables (marked with required = true) must be provided by the user.
#
# References:
# - Requirements: 15 (Variables and Configuration), 16 (Structure and Organization), 21 (Documentation)
# - Design: terraform/design.md

# ============================================================================
# AWS Configuration
# ============================================================================

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"

  validation {
    condition     = var.aws_region == "us-east-1"
    error_message = "Region must be us-east-1 (all Bedrock models are in this region)."
  }
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod, hackathon). Used for tagging and resource naming."
  type        = string
  default     = "hackathon"
}

variable "project_name" {
  description = "Project name for resource tagging and identification"
  type        = string
  default     = "job-search-assistant"
}

# ============================================================================
# Terraform State Management
# ============================================================================

variable "terraform_state_bucket" {
  description = "S3 bucket name for Terraform state storage (required). This bucket must be created manually before running terraform init."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.terraform_state_bucket))
    error_message = "Bucket name must be a valid S3 bucket name (lowercase alphanumeric and hyphens, 3-63 characters)."
  }
}

variable "terraform_state_key" {
  description = "S3 key path for Terraform state file"
  type        = string
  default     = "terraform.tfstate"
}

# ============================================================================
# Cognito Configuration
# ============================================================================

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID for authentication (required). This User Pool must already exist in AWS and will be imported into Terraform state."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^us-east-1_[a-zA-Z0-9]+$", var.cognito_user_pool_id))
    error_message = "User Pool ID must be in format: us-east-1_xxxxxxxxx"
  }
}

variable "frontend_domain" {
  description = "Frontend domain name for CloudFront and CORS (used for constructing Cognito callback URLs)"
  type        = string
  default     = "job-search-assistant.mvp"
}

# ============================================================================
# Bedrock Configuration
# ============================================================================
# 
# IMPORTANT: Several current Bedrock models in us-east-1 are only invocable via
# inference profiles (cross-region inference), which requires the region-prefixed
# model ID (e.g., "us.anthropic.claude-..."), NOT the bare base model ID
# (e.g., "anthropic.claude-..." alone). Using the bare ID fails with a
# non-obvious error.
#
# PLACEHOLDER: Exact model IDs pending confirmation from AWS console/Bedrock
# model catalog before finalization.

variable "bedrock_model_small" {
  description = "Bedrock model ID for small model (Claude Haiku or equivalent). Must use the us.-prefixed cross-region inference profile ID in us-east-1, not the bare base model ID. Example: us.anthropic.claude-3-5-haiku-20241022"
  type        = string
  sensitive   = true
}

variable "bedrock_model_mid" {
  description = "Bedrock model ID for mid-tier model (Claude Sonnet or equivalent). Must use the us.-prefixed cross-region inference profile ID in us-east-1, not the bare base model ID. Example: us.anthropic.claude-3-5-sonnet-20241022"
  type        = string
  sensitive   = true
}

variable "bedrock_region" {
  description = "AWS region for Bedrock service (all models must be in us-east-1)"
  type        = string
  default     = "us-east-1"
}

# ============================================================================
# SES Email Configuration
# ============================================================================

variable "ses_email" {
  description = "Source email address for SES (required). This email address must be manually verified in AWS SES before sending emails. Leave in sandbox mode or request production access separately."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.ses_email))
    error_message = "SES email must be a valid email address format."
  }
}

variable "ses_team_emails" {
  description = "List of team email addresses to verify in SES (for notifications). Each email must be manually verified by clicking the verification link sent to the email address."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for email in var.ses_team_emails : can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", email))
    ])
    error_message = "All team emails must be valid email addresses."
  }
}

# ============================================================================
# Lambda Configuration
# ============================================================================

variable "lambda_code_bucket" {
  description = "S3 bucket name where Lambda function .zip files are stored (required). Function code must be pre-uploaded to this bucket before terraform apply."
  type        = string
  sensitive   = true
}

variable "lambda_code_key_prefix" {
  description = "S3 key prefix for Lambda function code. Each Lambda's code is expected at: s3://{lambda_code_bucket}/{lambda_code_key_prefix}/{function_name}/code.zip"
  type        = string
  default     = "lambda-code"
}

variable "scan_worker_timeout" {
  description = "Lambda timeout for scan-worker function (seconds). Source: backend-scan-y-scoring design document. This timeout affects SQS visibility timeout calculation (visibility = 6 × timeout)."
  type        = number
  default     = 90

  validation {
    condition     = var.scan_worker_timeout > 0 && var.scan_worker_timeout <= 900
    error_message = "Scan worker timeout must be between 1 and 900 seconds."
  }
}

variable "scoring_worker_timeout" {
  description = "Lambda timeout for scoring-worker function (seconds). Source: backend-scan-y-scoring design document. This timeout affects SQS visibility timeout calculation (visibility = 6 × timeout)."
  type        = number
  default     = 30

  validation {
    condition     = var.scoring_worker_timeout > 0 && var.scoring_worker_timeout <= 900
    error_message = "Scoring worker timeout must be between 1 and 900 seconds."
  }
}

# ============================================================================
# API Gateway Configuration
# ============================================================================

variable "cors_origins" {
  description = "Comma-separated list of CORS allowed origins for API requests. Example: 'http://localhost:5173,https://example.com'"
  type        = string
  default     = "http://localhost:5173"
}

# ============================================================================
# EventBridge Scheduler Configuration
# ============================================================================

variable "orchestration_schedule_expression" {
  description = "EventBridge Scheduler cron expression for triggering the orquestador Lambda. Format: cron(minute hour day month ? year). Default: 8 AM, 12 PM (noon), 6 PM UTC daily"
  type        = string
  default     = "cron(0 8,12,18 * * ? *)"
}

# ============================================================================
# CloudWatch Configuration
# ============================================================================

variable "cloudwatch_log_retention" {
  description = "CloudWatch log retention period in days for Lambda log groups. Requirement 12 specifies 7 days (default AWS retention is never expire, which causes cost issues)."
  type        = number
  default     = 7

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.cloudwatch_log_retention)
    error_message = "CloudWatch log retention must be one of AWS's supported values: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653"
  }
}

variable "billing_alarm_threshold" {
  description = "Monthly billing threshold in USD for triggering CloudWatch alarm. Alert fires when estimated charges exceed this amount."
  type        = number
  default     = 500

  validation {
    condition     = var.billing_alarm_threshold > 0
    error_message = "Billing alarm threshold must be greater than 0."
  }
}

variable "lambda_error_threshold" {
  description = "CloudWatch alarm threshold for Lambda errors (error count over 5-minute period)"
  type        = number
  default     = 0

  validation {
    condition     = var.lambda_error_threshold >= 0
    error_message = "Lambda error threshold must be non-negative."
  }
}

variable "lambda_duration_threshold" {
  description = "CloudWatch alarm threshold for Lambda duration in milliseconds (p95 duration exceeding this value triggers alarm)"
  type        = number
  default     = 50000

  validation {
    condition     = var.lambda_duration_threshold > 0
    error_message = "Lambda duration threshold must be greater than 0."
  }
}

# ============================================================================
# Bedrock Request Processing Configuration
# ============================================================================

variable "prefiltro_token_threshold" {
  description = "Token overlap threshold for prefiltro_cargos (job title filtering). Shared with scan-worker and scoring-worker Lambda environment variables."
  type        = number
  default     = 1

  validation {
    condition     = var.prefiltro_token_threshold >= 0
    error_message = "Prefiltro token threshold must be non-negative."
  }
}

variable "html_clean_max_kb" {
  description = "Maximum HTML content size in KB before truncation (for cleaning before sending to Bedrock). Shared with Lambda environment variables."
  type        = number
  default     = 100

  validation {
    condition     = var.html_clean_max_kb > 0
    error_message = "HTML clean max KB must be greater than 0."
  }
}

variable "log_level" {
  description = "Logging level for all Lambda functions. Valid values: DEBUG, INFO, WARN, ERROR. Shared with all Lambda environment variables."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARN", "ERROR"], var.log_level)
    error_message = "Log level must be one of: DEBUG, INFO, WARN, ERROR"
  }
}

# ============================================================================
# DynamoDB Table Names (passed to Lambda modules)
# ============================================================================
# These are typically outputs from the dynamodb module, but can be overridden
# if importing existing tables with different names.

variable "dynamodb_table_empresas" {
  description = "Name of DynamoDB table for companies"
  type        = string
  default     = "Empresas"
}

variable "dynamodb_table_vacantes" {
  description = "Name of DynamoDB table for job vacancies"
  type        = string
  default     = "Vacantes"
}

variable "dynamodb_table_usuario_vacante" {
  description = "Name of DynamoDB table for user-vacancy relationships"
  type        = string
  default     = "UsuarioVacante"
}

variable "dynamodb_table_scan_jobs" {
  description = "Name of DynamoDB table for scan job metadata"
  type        = string
  default     = "ScanJobs"
}

variable "dynamodb_table_suscripciones" {
  description = "Name of DynamoDB table for user subscriptions"
  type        = string
  default     = "Suscripciones"
}

variable "dynamodb_table_perfiles" {
  description = "Name of DynamoDB table for user profiles"
  type        = string
  default     = "Perfiles"
}

variable "dynamodb_table_entradas" {
  description = "Name of DynamoDB table for interview entries (project's innovation differentiator)"
  type        = string
  default     = "Entradas"
}

# ============================================================================
# SQS Queue URLs (passed to Lambda modules)
# ============================================================================
# These are typically outputs from the sqs module, but can be overridden
# if importing existing queues with different names.

variable "scan_queue_url" {
  description = "URL of the scan-queue SQS queue (for scan job processing)"
  type        = string
}

variable "scoring_queue_url" {
  description = "URL of the scoring-queue SQS queue (for scoring job processing)"
  type        = string
}

# ============================================================================
# Frontend Configuration
# ============================================================================

variable "frontend_bucket_name" {
  description = "S3 bucket name for frontend static assets. Must be globally unique. If not specified, a default name is used."
  type        = string
  default     = ""

  validation {
    condition = (
      var.frontend_bucket_name == "" ||
      can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.frontend_bucket_name))
    )
    error_message = "Frontend bucket name must be empty or a valid S3 bucket name (lowercase alphanumeric and hyphens, 3-63 characters)."
  }
}

# ============================================================================
# IAM Role ARNs (from iam module)
# ============================================================================
# These variables allow the lambda and eventbridge modules to reference
# pre-created IAM roles without declaring them directly.

variable "api_role_arn" {
  description = "ARN of the IAM role for the API Lambda function (created in iam module)"
  type        = string
}

variable "orquestador_role_arn" {
  description = "ARN of the IAM role for the orquestador Lambda function (created in iam module)"
  type        = string
}

variable "scan_worker_role_arn" {
  description = "ARN of the IAM role for the scan-worker Lambda function (created in iam module)"
  type        = string
}

variable "scoring_worker_role_arn" {
  description = "ARN of the IAM role for the scoring-worker Lambda function (created in iam module)"
  type        = string
}

variable "notificador_role_arn" {
  description = "ARN of the IAM role for the notificador Lambda function (created in iam module)"
  type        = string
}

variable "eventbridge_scheduler_role_arn" {
  description = "ARN of the IAM role for EventBridge Scheduler to invoke Lambda functions (created in iam module)"
  type        = string
}

