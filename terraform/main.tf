# Main Terraform Configuration for job-search-assistant
# 
# This file orchestrates all submodules and wires them together with proper dependencies.
# The infrastructure consists of 10 modules:
#   1. IAM - Roles and policies for Lambda functions, EventBridge Scheduler, and GitHub Actions
#   2. DynamoDB - 7 data tables for companies, vacancies, users, and scan jobs
#   3. SQS - 4 message queues (2 main queues + 2 DLQs) for async processing
#   4. Lambda - 5 serverless functions for API, orchestration, scanning, scoring, and notifications
#   5. API Gateway - REST API with Cognito authorization
#   6. Cognito - User Pool (import only) with App Client and Hosted UI Domain
#   7. S3 + CloudFront - Frontend static website hosting with SPA routing support
#   8. EventBridge Scheduler - Scheduled trigger for the orquestador Lambda
#   9. SES - Email service configuration for sending notifications
#   10. CloudWatch - Monitoring, logging, and billing alarms
#
# Module Dependency Graph (strict ordering required):
#   1. IAM module first (roles needed by other modules)
#   2. DynamoDB, SQS (no dependencies, needed by Lambda)
#   3. Lambda (depends on IAM, DynamoDB, SQS)
#   4. Cognito (import only, needed by API Gateway)
#   5. API Gateway (depends on Lambda, Cognito)
#   6. S3/CloudFront (independent)
#   7. EventBridge Scheduler (depends on Lambda, IAM)
#   8. SES (independent)
#   9. CloudWatch (depends on Lambda, S3)
#
# References:
#   - Requirements: 16 (Structure and Organization), 19 (Dependencies)
#   - Design: design.md sections "Module Structure", "Resource Dependencies Order", "Import Commands"

# ============================================================================
# 1. IAM MODULE - Create roles and policies for all AWS services
# ============================================================================
# This module MUST be created first since its outputs (role ARNs) are consumed
# by other modules (Lambda and EventBridge).
#
# Outputs from this module:
#   - api_role_arn
#   - orquestador_role_arn
#   - scan_worker_role_arn
#   - scoring_worker_role_arn
#   - notificador_role_arn
#   - eventbridge_scheduler_role_arn
#   - github_actions_role_arn

module "iam" {
  source = "./modules/iam"

  # No input variables - IAM module creates all roles with hardcoded names
}

# ============================================================================
# 2. DYNAMODB MODULE - Create 7 data tables
# ============================================================================
# DynamoDB tables have no dependencies (except IAM for lifecycle policies, which
# are handled internally by the module).
#
# Tables created:
#   - Empresas
#   - Vacantes
#   - UsuarioVacante
#   - Entradas
#   - Perfiles
#   - Suscripciones
#   - ScanJobs
#
# Outputs from this module:
#   - All table names and ARNs

module "dynamodb" {
  source = "./modules/dynamodb"

  # No input variables - DynamoDB module creates tables with hardcoded names
}

# ============================================================================
# 3. SQS MODULE - Create 4 message queues (2 main + 2 DLQs)
# ============================================================================
# SQS queues have no external dependencies.
# 
# Queues created:
#   - scan-dlq (Dead Letter Queue for scan-queue)
#   - scan-queue (Main processing queue for scan jobs)
#     - Visibility timeout: 540s (6 × 90s Lambda timeout for scan-worker)
#   - scoring-dlq (Dead Letter Queue for scoring-queue)
#   - scoring-queue (Main processing queue for scoring jobs)
#     - Visibility timeout: 180s (6 × 30s Lambda timeout for scoring-worker)
#
# Outputs from this module:
#   - scan_dlq_arn
#   - scan_dlq_url
#   - scan_queue_arn
#   - scan_queue_url
#   - scoring_dlq_arn
#   - scoring_dlq_url
#   - scoring_queue_arn
#   - scoring_queue_url

module "sqs" {
  source = "./modules/sqs"

  # SQS module has hardcoded visibility timeouts:
  # - scan-queue visibility timeout: 540s (6 × 90s Lambda timeout for scan-worker)
  # - scoring-queue visibility timeout: 180s (6 × 30s Lambda timeout for scoring-worker)
  # Source: backend-scan-y-scoring design.md "SQS Queue Configuration & Visibility Timeout Formulas"
}

# ============================================================================
# 4. LAMBDA MODULE - Create 5 serverless functions
# ============================================================================
# Lambda functions depend on:
#   - IAM module (role ARNs)
#   - DynamoDB module (table names)
#   - SQS module (queue URLs)
#   - Cognito User Pool ID (from variables)
#   - SES email (from variables)
#
# Functions created:
#   1. api - FastAPI + Mangum, 512MB, 10s timeout, monolithic REST API
#   2. orquestador - EventBridge Scheduler trigger, 512MB, 60s timeout
#   3. scan-worker - SQS consumer for scan-queue, 1024MB, 90s timeout, reserved concurrency = 5
#   4. scoring-worker - SQS consumer for scoring-queue, 1024MB, 30s timeout, reserved concurrency = 3
#   5. notificador - Email notifications via SES, 512MB, 30s timeout
#
# Outputs from this module:
#   - api_lambda_arn
#   - api_lambda_name
#   - orquestador_lambda_arn
#   - orquestador_lambda_name
#   - scan_worker_lambda_arn
#   - scan_worker_lambda_name
#   - scoring_worker_lambda_arn
#   - scoring_worker_lambda_name
#   - notificador_lambda_arn
#   - notificador_lambda_name

module "lambda" {
  source = "./modules/lambda"

  # IAM role ARNs (from iam module)
  api_role_arn            = module.iam.api_role_arn
  orquestador_role_arn    = module.iam.orquestador_role_arn
  scan_worker_role_arn    = module.iam.scan_worker_role_arn
  scoring_worker_role_arn = module.iam.scoring_worker_role_arn
  notificador_role_arn    = module.iam.notificador_role_arn

  # DynamoDB table names (from dynamodb module)
  empresas_table_name        = module.dynamodb.empresas_table_name
  vacantes_table_name        = module.dynamodb.vacantes_table_name
  usuario_vacante_table_name = module.dynamodb.usuario_vacante_table_name
  scan_jobs_table_name       = module.dynamodb.scan_jobs_table_name
  scan_jobs_table_stream_arn = module.dynamodb.scan_jobs_table_stream_arn
  suscripciones_table_name   = module.dynamodb.suscripciones_table_name
  perfiles_table_name        = module.dynamodb.perfiles_table_name
  entradas_table_name        = module.dynamodb.entradas_table_name

  # SQS queue URLs and ARNs (from sqs module)
  scan_queue_url    = module.sqs.scan_queue_url
  scan_queue_arn    = module.sqs.scan_queue_arn
  scoring_queue_url = module.sqs.scoring_queue_url
  scoring_queue_arn = module.sqs.scoring_queue_arn

  # Cognito configuration (from variables)
  cognito_user_pool_id = var.cognito_user_pool_id

  # SES email (from variables)
  ses_email = var.ses_email

  # Bedrock configuration (from variables)
  bedrock_model_small = var.bedrock_model_small
  bedrock_model_mid   = var.bedrock_model_mid
  bedrock_region      = var.bedrock_region

  # Lambda configuration (from variables)
  lambda_code_bucket     = var.lambda_code_bucket
  lambda_code_key_prefix = var.lambda_code_key_prefix

  # Additional environment variables (from variables)
  cors_origins              = var.cors_origins
  prefiltro_token_threshold = var.prefiltro_token_threshold
  html_clean_max_kb         = var.html_clean_max_kb
  log_level                 = var.log_level

  depends_on = [
    module.iam,
    module.dynamodb,
    module.sqs
  ]
}

# ============================================================================
# 5. COGNITO MODULE - Import existing User Pool, App Client, and Hosted UI Domain
# ============================================================================
# This module imports existing Cognito resources (not creating new ones).
# This is critical to preserve existing user data and configuration.
#
# Resources imported:
#   1. Cognito User Pool (job-search-assistant) - already exists in AWS
#   2. Cognito App Client (job-search-frontend) - already exists in AWS
#   3. Cognito Hosted UI Domain (job-search-assistant-mvp) - already exists in AWS
#
# Outputs from this module:
#   - user_pool_arn
#   - user_pool_id
#   - app_client_id
#   - hosted_ui_domain

module "cognito" {
  source = "./modules/cognito"

  cognito_user_pool_id = var.cognito_user_pool_id

  depends_on = [
    module.iam
  ]
}

# ============================================================================
# 6. API GATEWAY MODULE - REST API with Cognito authorization
# ============================================================================
# API Gateway depends on:
#   - Lambda module (api Lambda ARN for integration)
#   - Cognito module (User Pool ARN for authorizer)
#
# Creates:
#   - REST API with {proxy+} path matching all routes
#   - COGNITO authorizer pointing to Cognito User Pool
#   - AWS_PROXY integration to api Lambda function
#   - API Gateway stage (prod) with metrics and logging
#
# Outputs from this module:
#   - rest_api_id
#   - rest_api_invoke_url

module "api_gateway" {
  source = "./modules/api-gateway"

  # Lambda function details for integration (from lambda module)
  api_lambda_invoke_arn    = module.lambda.api_lambda_invoke_arn
  api_lambda_function_name = module.lambda.api_lambda_name

  # CloudWatch log group for API Gateway logging (from cloudwatch module)
  api_log_group_name = module.cloudwatch.api_log_group_name

  # IAM role for API Gateway to write CloudWatch logs (from iam module)
  api_gateway_cloudwatch_role_arn = module.iam.api_gateway_cloudwatch_role_arn

  # Cognito User Pool ARN for authorizer (from cognito module)
  cognito_user_pool_arn = module.cognito.user_pool_arn

  depends_on = [
    module.lambda,
    module.cognito,
    module.cloudwatch,
    module.iam
  ]
}

# ============================================================================
# 7. S3 + CLOUDFRONT MODULE - Frontend static website hosting with SPA routing
# ============================================================================
# S3 and CloudFront have no external dependencies and can be created in parallel.
#
# Creates:
#   - S3 bucket for frontend static assets
#   - CloudFront distribution with SPA routing (403/404 → /index.html with 200)
#   - CloudFront Origin Access Identity (OAI) for secure S3 access
#   - S3 bucket policy allowing CloudFront to read objects
#
# Outputs from this module:
#   - s3_bucket_name
#   - s3_bucket_arn
#   - cloudfront_distribution_domain_name
#   - cloudfront_distribution_id

module "s3_cloudfront" {
  source = "./modules/s3-cloudfront"

  # Frontend bucket name (auto-generated if not specified)
  # Override in terraform.tfvars if you want a specific bucket name
  frontend_bucket_name = (
    var.frontend_bucket_name != "" ?
    var.frontend_bucket_name :
    "job-search-assistant-frontend-${data.aws_caller_identity.current.account_id}"
  )

  depends_on = [
    module.iam
  ]
}

# ============================================================================
# 8. EVENTBRIDGE SCHEDULER MODULE - Scheduled trigger for orquestador Lambda
# ============================================================================
# EventBridge Scheduler depends on:
#   - Lambda module (orquestador Lambda ARN)
#   - IAM module (EventBridge Scheduler invoke role ARN)
#
# Creates:
#   - EventBridge Scheduler schedule that triggers the orquestador Lambda
#   - Schedule expression (default: 8 AM, 12 PM, 6 PM UTC daily)
#
# Outputs from this module:
#   - schedule_arn

module "eventbridge" {
  source = "./modules/eventbridge"

  # Lambda function ARNs (from lambda module)
  orquestador_lambda_arn        = module.lambda.orquestador_lambda_arn
  orquestador_lambda_invoke_arn = module.lambda.orquestador_lambda_invoke_arn

  # IAM role ARN for the Scheduler (from iam module)
  eventbridge_scheduler_role_arn = module.iam.eventbridge_scheduler_role_arn

  # Schedule configuration (from variables)
  schedule_expression = var.orchestration_schedule_expression
  timezone            = "UTC"

  # Environment configuration
  environment  = var.environment
  project_name = var.project_name
  aws_region   = var.aws_region

  depends_on = [
    module.lambda,
    module.iam
  ]
}

# ============================================================================
# 9. SES MODULE - Email service configuration
# ============================================================================
# SES has no external dependencies and can be created in parallel.
#
# Creates:
#   - SES email identity for source email (var.ses_email)
#   - SES email identities for team members (var.ses_team_emails)
#
# Note: Email verification is manual - each recipient must click the
# verification link sent to their email address.
#
# Sandbox Mode Notes:
#   - 200 emails/day limit
#   - 1 email/second limit
#   - Production access must be requested separately (approx 24h approval)
#
# Outputs from this module:
#   - source_email

module "ses" {
  source = "./modules/ses"

  # SES email configuration (from variables)
  ses_email       = var.ses_email
  ses_team_emails = var.ses_team_emails
  aws_region      = var.aws_region
}

# ============================================================================
# 10. CLOUDWATCH MODULE - Monitoring, logging, and billing alarms
# ============================================================================
# CloudWatch module depends on:
#   - Lambda module (Lambda function names for log groups)
#   - S3 + CloudFront module (S3 bucket for dashboard references, optional)
#
# Creates:
#   - CloudWatch log groups for all 5 Lambda functions (7-day retention)
#   - CloudWatch metric alarms:
#     * Lambda error alarm (threshold: error count > 0 in 5 minutes)
#     * Lambda duration alarm (threshold: p95 duration > 50s)
#     * Billing alarm (threshold: estimated charges > $500/month)
#
# Outputs from this module:
#   - log_group_api
#   - log_group_orquestador
#   - log_group_scan_worker
#   - log_group_scoring_worker
#   - log_group_notificador

module "cloudwatch" {
  source = "./modules/cloudwatch"

  # Lambda function names for log groups (from lambda module)
  lambda_function_names = {
    api            = module.lambda.api_lambda_name
    orquestador    = module.lambda.orquestador_lambda_name
    scan_worker    = module.lambda.scan_worker_lambda_name
    scoring_worker = module.lambda.scoring_worker_lambda_name
    notificador    = module.lambda.notificador_lambda_name
  }

  # API Lambda function name specifically for alarms
  api_function_name = module.lambda.api_lambda_name

  # CloudWatch configuration
  retention_in_days            = var.cloudwatch_log_retention
  lambda_duration_threshold_ms = var.lambda_duration_threshold
  billing_alarm_threshold      = var.billing_alarm_threshold

  depends_on = [
    module.lambda
  ]
}

# ============================================================================
# AWS RESOURCE GROUP - For resource organization and management
# ============================================================================
# This resource must be declared at root level before it can be imported
# via terraform import. The import command uses this resource address:
#   terraform import aws_resourcegroups_group.job_search_assistant \
#     arn:aws:resource-groups:us-east-1:<ACCOUNT_ID>:group/job-search-assistant

resource "aws_resourcegroups_group" "job_search_assistant" {
  name = "job-search-assistant"

  # Query for all resources tagged with this project
  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [
        {
          Key    = "Project"
          Values = [var.project_name]
        }
      ]
    })
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# ============================================================================
# DATA SOURCE - AWS Account ID for resource naming
# ============================================================================
# Used in resource naming (e.g., S3 bucket names that must be globally unique)

data "aws_caller_identity" "current" {}

# ============================================================================
# DATA SOURCE - AWS Region (for reference)
# ============================================================================

data "aws_region" "current" {}
