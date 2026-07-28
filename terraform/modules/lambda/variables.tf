# Variables for Lambda Module
#
# This module creates 5 Lambda functions: api, orquestador, scan-worker, 
# scoring-worker, and notificador. All functions use Python 3.12 runtime
# and require:
# - IAM role ARNs (from iam module)
# - DynamoDB table names (from dynamodb module)
# - SQS queue URLs (from sqs module)
# - Environment configuration from root module

# ============================================================================
# IAM Role ARNs (from iam module)
# ============================================================================

variable "api_role_arn" {
  description = "ARN of the IAM role for the API Lambda function"
  type        = string
}

variable "orquestador_role_arn" {
  description = "ARN of the IAM role for the Orquestador Lambda function"
  type        = string
}

variable "scan_worker_role_arn" {
  description = "ARN of the IAM role for the Scan Worker Lambda function"
  type        = string
}

variable "scoring_worker_role_arn" {
  description = "ARN of the IAM role for the Scoring Worker Lambda function"
  type        = string
}

variable "notificador_role_arn" {
  description = "ARN of the IAM role for the Notificador Lambda function"
  type        = string
}

# ============================================================================
# DynamoDB Table Names (from dynamodb module)
# ============================================================================

variable "empresas_table_name" {
  description = "Name of the Empresas DynamoDB table"
  type        = string
}

variable "vacantes_table_name" {
  description = "Name of the Vacantes DynamoDB table"
  type        = string
}

variable "usuario_vacante_table_name" {
  description = "Name of the UsuarioVacante DynamoDB table"
  type        = string
}

variable "entradas_table_name" {
  description = "Name of the Entradas DynamoDB table"
  type        = string
}

variable "perfiles_table_name" {
  description = "Name of the Perfiles DynamoDB table"
  type        = string
}

variable "suscripciones_table_name" {
  description = "Name of the Suscripciones DynamoDB table"
  type        = string
}

variable "scan_jobs_table_name" {
  description = "Name of the ScanJobs DynamoDB table"
  type        = string
}

# ============================================================================
# SQS Queue URLs (from sqs module)
# ============================================================================

variable "scan_queue_url" {
  description = "URL of the scan-queue SQS queue"
  type        = string
}

variable "scan_queue_arn" {
  description = "ARN of the scan-queue SQS queue"
  type        = string
}

variable "scoring_queue_url" {
  description = "URL of the scoring-queue SQS queue"
  type        = string
}

variable "scoring_queue_arn" {
  description = "ARN of the scoring-queue SQS queue"
  type        = string
}

# ============================================================================
# Bedrock Configuration
# ============================================================================

variable "bedrock_model_small" {
  description = "Bedrock model ID for small model (Claude Haiku). Must use the us.-prefixed cross-region inference profile ID in us-east-1, not the bare base model ID."
  type        = string
}

variable "bedrock_model_mid" {
  description = "Bedrock model ID for mid model (Claude Sonnet). Must use the us.-prefixed cross-region inference profile ID in us-east-1, not the bare base model ID."
  type        = string
}

# ============================================================================
# Configuration Parameters
# ============================================================================

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

# ============================================================================
# SES and Cognito Configuration
# ============================================================================

variable "ses_email" {
  description = "Source email for SES email sending"
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID for the API Lambda"
  type        = string
}

# ============================================================================
# CORS Configuration
# ============================================================================

variable "cors_origins" {
  description = "Comma-separated list of CORS allowed origins"
  type        = string
  default     = "http://localhost:5173"
}

# ============================================================================
# Bedrock Region (fixed to us-east-1)
# ============================================================================

variable "bedrock_region" {
  description = "AWS region for Bedrock inference"
  type        = string
  default     = "us-east-1"
}

# ============================================================================
# Lambda Code S3 Bucket Configuration
# ============================================================================

variable "lambda_code_bucket" {
  description = "S3 bucket where Lambda function code is stored"
  type        = string
}

variable "lambda_code_key_prefix" {
  description = "S3 key prefix for Lambda function code"
  type        = string
  default     = "lambda-code"
}

# ============================================================================
# Environment Name (for naming resources)
# ============================================================================

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod, hackathon)"
  type        = string
  default     = "hackathon"
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}
