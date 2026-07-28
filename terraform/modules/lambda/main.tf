# Lambda Module - job-search-assistant
#
# This module creates 5 Lambda functions:
# 1. api: FastAPI + Mangum for synchronous API endpoints (API Gateway)
# 2. orquestador: Orchestrator triggered by EventBridge Scheduler
# 3. scan-worker: Async scan job processor (SQS consumer, reserved concurrency=5)
# 4. scoring-worker: Async scoring job processor (SQS consumer, reserved concurrency=3)
# 5. notificador: Email notification sender (SES)
#
# All functions run Python 3.12 and reference IAM roles from the iam module.
# Code is packaged as .zip files from S3 bucket.
#
# References:
# - Requirements: 5, 15, 16
# - Design: backend-scan-y-scoring (Lambda timeouts, reserved concurrency, environment variables)

# ============================================================================
# Lambda Code Deployment Strategy
# ============================================================================
# 
# Lambda function code is deployed as .zip files in an S3 bucket.
# Terraform references these pre-uploaded .zip files:
# - s3://{lambda_code_bucket}/{lambda_code_key_prefix}/{function_name}/code.zip
#
# The source_code_hash is derived from the S3 object ETag to detect code changes
# and trigger Lambda redeployment automatically.
#
# Note: The actual Lambda code .zip files must be uploaded to S3 before 
# Terraform apply. This is done by the CI/CD pipeline (GitHub Actions).
# The packaging logic (Python code → .zip) is outside this Terraform module.

# ============================================================================
# Lambda 1: API (FastAPI + Mangum)
# ============================================================================
#
# Purpose: Synchronous API endpoint for user requests (via API Gateway)
# Integration: API Gateway → AWS_PROXY → Lambda → FastAPI + Mangum
# Timeout: 10 seconds (API endpoints should respond quickly)
# Memory: 512 MB
# Concurrency: Not reserved (can autoscale)
# Environment Variables: All 7 DynamoDB tables, Bedrock models, SQS queues
#
# Reference: Design document - Lambda function specifications

resource "aws_lambda_function" "api" {
  function_name = "job-search-api"
  role          = var.api_role_arn
  handler       = "main.handler"
  runtime       = "python3.12"
  timeout       = 10
  memory_size   = 512

  # Code packaging: reference S3 object
  # The .zip file is expected to be at:
  # s3://{lambda_code_bucket}/{lambda_code_key_prefix}/api/code.zip
  s3_bucket = var.lambda_code_bucket
  s3_key    = "${var.lambda_code_key_prefix}/api/code.zip"

  environment {
    variables = {
      # Bedrock configuration
      BEDROCK_REGION      = var.bedrock_region
      BEDROCK_MODEL_SMALL = var.bedrock_model_small
      BEDROCK_MODEL_MID   = var.bedrock_model_mid

      # DynamoDB table names for API endpoints
      DYNAMODB_TABLE_EMPRESA         = var.empresas_table_name
      DYNAMODB_TABLE_VACANTE         = var.vacantes_table_name
      DYNAMODB_TABLE_USUARIO_VACANTE = var.usuario_vacante_table_name
      DYNAMODB_TABLE_SCAN_JOB        = var.scan_jobs_table_name
      DYNAMODB_TABLE_SUSCRIPCIONES   = var.suscripciones_table_name
      DYNAMODB_TABLE_PERFIL          = var.perfiles_table_name

      # Cognito for authentication
      COGNITO_USER_POOL_ID = var.cognito_user_pool_id

      # SQS queue URLs for triggering scans and rescoring
      SQS_QUEUE_SCAN_URL    = var.scan_queue_url
      SQS_QUEUE_SCORING_URL = var.scoring_queue_url

      # SES for email
      SES_EMAIL = var.ses_email

      # CORS configuration
      CORS_ORIGINS = var.cors_origins

      # Logging
      LOG_LEVEL = var.log_level
    }
  }

  # Trigger redeployment when code changes
  # Using base64sha256 of the S3 key as a simple hash; in production, use the S3 object ETag
  source_code_hash = base64sha256("${var.lambda_code_bucket}/${var.lambda_code_key_prefix}/api/code.zip")

  tags = {
    Name = "job-search-api"
  }
}

# ============================================================================
# Lambda 2: Orquestador (Orchestrator)
# ============================================================================
#
# Purpose: Triggered by EventBridge Scheduler to initiate scan jobs
# Integration: EventBridge Scheduler → Lambda
# Timeout: 60 seconds
# Memory: 512 MB
# Concurrency: Not reserved (runs on schedule, not expected to be heavily parallelized)
# Environment Variables: Empresas, Vacantes, ScanJobs, Suscripciones, Perfiles tables, scan-queue
#
# Note: Does NOT have event source mapping (triggered by EventBridge directly)

resource "aws_lambda_function" "orquestador" {
  function_name = "job-search-orquestador"
  role          = var.orquestador_role_arn
  handler       = "main.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 512

  # Code packaging: reference S3 object
  s3_bucket = var.lambda_code_bucket
  s3_key    = "${var.lambda_code_key_prefix}/orquestador/code.zip"

  environment {
    variables = {
      # Bedrock configuration
      BEDROCK_REGION      = var.bedrock_region
      BEDROCK_MODEL_SMALL = var.bedrock_model_small
      BEDROCK_MODEL_MID   = var.bedrock_model_mid

      # DynamoDB tables: companies, vacancies, scan jobs, subscriptions
      DYNAMODB_TABLE_EMPRESA       = var.empresas_table_name
      DYNAMODB_TABLE_VACANTE       = var.vacantes_table_name
      DYNAMODB_TABLE_SCAN_JOB      = var.scan_jobs_table_name
      DYNAMODB_TABLE_SUSCRIPCIONES = var.suscripciones_table_name
      DYNAMODB_TABLE_PERFIL        = var.perfiles_table_name

      # SQS queue for publishing scan jobs
      SQS_QUEUE_SCAN_URL = var.scan_queue_url

      # Logging
      LOG_LEVEL = var.log_level
    }
  }

  source_code_hash = base64sha256("${var.lambda_code_bucket}/${var.lambda_code_key_prefix}/orquestador/code.zip")

  tags = {
    Name = "job-search-orquestador"
  }
}

# ============================================================================
# Lambda 3: Scan Worker (SQS Consumer)
# ============================================================================
#
# Purpose: Process scan jobs from scan-queue (crawl company websites)
# Integration: SQS event source mapping for scan-queue
# Timeout: 90 seconds (from backend-scan-y-scoring design)
# Memory: 1024 MB (from backend-scan-y-scoring design)
# Reserved Concurrency: 5 (prevents Bedrock token limit overload)
# Environment Variables: Empresas, Vacantes, ScanJobs tables, scan-queue, scoring-queue
#
# Note: Reserved concurrency is CRITICAL to prevent overwhelming Bedrock API
# with too many concurrent requests. Bedrock has strict token-per-minute limits.

resource "aws_lambda_function" "scan_worker" {
  function_name = "job-search-scan-worker"
  role          = var.scan_worker_role_arn
  handler       = "main.handler"
  runtime       = "python3.12"
  timeout       = 90
  memory_size   = 1024

  # Reserved concurrency: 5 concurrent executions max
  # This prevents overwhelming Bedrock's token limits
  # Source: backend-scan-y-scoring design spec
  reserved_concurrent_executions = 5

  # Code packaging: reference S3 object
  s3_bucket = var.lambda_code_bucket
  s3_key    = "${var.lambda_code_key_prefix}/scan_worker/code.zip"

  environment {
    variables = {
      # Bedrock configuration
      BEDROCK_REGION      = var.bedrock_region
      BEDROCK_MODEL_SMALL = var.bedrock_model_small
      BEDROCK_MODEL_MID   = var.bedrock_model_mid

      # DynamoDB tables for storing scan results
      DYNAMODB_TABLE_EMPRESA  = var.empresas_table_name
      DYNAMODB_TABLE_VACANTE  = var.vacantes_table_name
      DYNAMODB_TABLE_SCAN_JOB = var.scan_jobs_table_name

      # SQS queues: consume from scan-queue, publish to scoring-queue
      SQS_QUEUE_SCAN_URL    = var.scan_queue_url
      SQS_QUEUE_SCORING_URL = var.scoring_queue_url

      # Configuration for URL processing and HTML cleaning
      PREFILTRO_TOKEN_THRESHOLD = var.prefiltro_token_threshold
      HTML_CLEAN_MAX_KB         = var.html_clean_max_kb

      # Logging
      LOG_LEVEL = var.log_level
    }
  }

  source_code_hash = base64sha256("${var.lambda_code_bucket}/${var.lambda_code_key_prefix}/scan_worker/code.zip")

  tags = {
    Name = "job-search-scan-worker"
  }
}

# ============================================================================
# Lambda 4: Scoring Worker (SQS Consumer)
# ============================================================================
#
# Purpose: Process scoring jobs from scoring-queue (rank vacancies by user relevance)
# Integration: SQS event source mapping for scoring-queue
# Timeout: 30 seconds (from backend-scan-y-scoring design)
# Memory: 1024 MB (from backend-scan-y-scoring design)
# Reserved Concurrency: 3 (prevents Bedrock token limit overload)
# Environment Variables: Perfiles, UsuarioVacante, Vacantes, Empresas tables, scoring-queue
#
# Note: Reserved concurrency is CRITICAL to prevent overwhelming Bedrock API
# with too many concurrent requests.

resource "aws_lambda_function" "scoring_worker" {
  function_name = "job-search-scoring-worker"
  role          = var.scoring_worker_role_arn
  handler       = "main.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 1024

  # Reserved concurrency: 3 concurrent executions max
  # This prevents overwhelming Bedrock's token limits
  # Source: backend-scan-y-scoring design spec
  reserved_concurrent_executions = 3

  # Code packaging: reference S3 object
  s3_bucket = var.lambda_code_bucket
  s3_key    = "${var.lambda_code_key_prefix}/scoring_worker/code.zip"

  environment {
    variables = {
      # Bedrock configuration
      BEDROCK_REGION      = var.bedrock_region
      BEDROCK_MODEL_SMALL = var.bedrock_model_small
      BEDROCK_MODEL_MID   = var.bedrock_model_mid

      # DynamoDB tables for user profiles and vacancy relationships
      DYNAMODB_TABLE_PERFIL          = var.perfiles_table_name
      DYNAMODB_TABLE_USUARIO_VACANTE = var.usuario_vacante_table_name
      DYNAMODB_TABLE_VACANTE         = var.vacantes_table_name
      DYNAMODB_TABLE_EMPRESA         = var.empresas_table_name

      # SQS queue: consume from scoring-queue only
      SQS_QUEUE_SCORING_URL = var.scoring_queue_url

      # Configuration for token processing
      PREFILTRO_TOKEN_THRESHOLD = var.prefiltro_token_threshold

      # Logging
      LOG_LEVEL = var.log_level
    }
  }

  source_code_hash = base64sha256("${var.lambda_code_bucket}/${var.lambda_code_key_prefix}/scoring_worker/code.zip")

  tags = {
    Name = "job-search-scoring-worker"
  }
}

# ============================================================================
# Lambda 5: Notificador (Email Notifications)
# ============================================================================
#
# Purpose: Send email notifications to users
# Integration: Triggered by API endpoints or other services
# Timeout: 30 seconds
# Memory: 512 MB
# Concurrency: Not reserved (triggered on-demand)
# Environment Variables: SES email address, optional DynamoDB tables
#
# Note: Does NOT have event source mapping (triggered by other services)

resource "aws_lambda_function" "notificador" {
  function_name = "job-search-notificador"
  role          = var.notificador_role_arn
  handler       = "main.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 512

  # Code packaging: reference S3 object
  s3_bucket = var.lambda_code_bucket
  s3_key    = "${var.lambda_code_key_prefix}/notificador/code.zip"

  environment {
    variables = {
      # SES configuration for email sending
      SES_EMAIL = var.ses_email

      # Logging
      LOG_LEVEL = var.log_level
    }
  }

  source_code_hash = base64sha256("${var.lambda_code_bucket}/${var.lambda_code_key_prefix}/notificador/code.zip")

  tags = {
    Name = "job-search-notificador"
  }
}
