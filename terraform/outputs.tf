# Root Module Outputs
#
# This file exports key infrastructure information from all modules.
# These outputs provide critical endpoints, identifiers, and resource information
# needed for deployment, monitoring, configuration, and operations.
#
# Reference: Requirement 21 - Documentation
# The outputs are organized by category for clarity and ease of navigation.

# ============================================================================
# API Endpoint & Gateway Configuration
# ============================================================================

output "api_endpoint_url" {
  description = "URL of the API Gateway endpoint for the backend API (frontend uses this for API calls)"
  value       = module.api_gateway.api_endpoint_url
  sensitive   = false
}

output "api_gateway_rest_api_id" {
  description = "REST API ID for API Gateway configuration"
  value       = module.api_gateway.rest_api_id
  sensitive   = false
}

output "api_gateway_stage_name" {
  description = "Stage name of the deployed API Gateway (used for monitoring and logs)"
  value       = module.api_gateway.api_gateway_stage_name
  sensitive   = false
}

output "api_execution_arn" {
  description = "Execution ARN for API Gateway (used for resource-based policies)"
  value       = module.api_gateway.api_execution_arn
  sensitive   = false
}

# ============================================================================
# Cognito Authentication Configuration
# ============================================================================

output "cognito_hosted_ui_domain_url" {
  description = "Complete Cognito Hosted UI domain URL for frontend login construction (e.g., https://job-search-assistant-mvp.auth.us-east-1.amazoncognito.com)"
  value       = module.cognito.hosted_ui_domain_url
  sensitive   = false
}

output "cognito_hosted_ui_domain_name" {
  description = "Cognito Hosted UI domain name without protocol or region (e.g., job-search-assistant-mvp)"
  value       = module.cognito.hosted_ui_domain
  sensitive   = false
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID (imported, used for user management and authentication)"
  value       = module.cognito.user_pool_id
  sensitive   = true
}

output "cognito_app_client_id" {
  description = "Cognito App Client ID for frontend OAuth flow (frontend uses this for login)"
  value       = module.cognito.app_client_id
  sensitive   = false
}

# ============================================================================
# Frontend Hosting (S3 + CloudFront)
# ============================================================================

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name (*.cloudfront.net, where frontend is served). Configure this in Cognito Callback URLs after deployment."
  value       = module.s3_cloudfront.cloudfront_domain_name
  sensitive   = false
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (used for creating cache invalidations after deploying frontend)"
  value       = module.s3_cloudfront.cloudfront_distribution_id
  sensitive   = false
}

output "s3_frontend_bucket_name" {
  description = "S3 bucket name for frontend assets (use to upload built frontend from CI/CD)"
  value       = module.s3_cloudfront.s3_bucket_name
  sensitive   = false
}

# ============================================================================
# Lambda Function Information
# ============================================================================

# API Lambda
output "api_lambda_arn" {
  description = "ARN of the API Lambda function (FastAPI + Mangum, monolithic)"
  value       = module.lambda.api_lambda_arn
  sensitive   = false
}

output "api_lambda_name" {
  description = "Name of the API Lambda function"
  value       = module.lambda.api_lambda_name
  sensitive   = false
}

# Orquestador Lambda
output "orquestador_lambda_arn" {
  description = "ARN of the Orquestador Lambda function (triggered by EventBridge Scheduler)"
  value       = module.lambda.orquestador_lambda_arn
  sensitive   = false
}

output "orquestador_lambda_name" {
  description = "Name of the Orquestador Lambda function"
  value       = module.lambda.orquestador_lambda_name
  sensitive   = false
}

# Scan Worker Lambda
output "scan_worker_lambda_arn" {
  description = "ARN of the Scan Worker Lambda function (processes scan jobs from SQS)"
  value       = module.lambda.scan_worker_lambda_arn
  sensitive   = false
}

output "scan_worker_lambda_name" {
  description = "Name of the Scan Worker Lambda function"
  value       = module.lambda.scan_worker_lambda_name
  sensitive   = false
}

# Scoring Worker Lambda
output "scoring_worker_lambda_arn" {
  description = "ARN of the Scoring Worker Lambda function (processes scoring jobs from SQS)"
  value       = module.lambda.scoring_worker_lambda_arn
  sensitive   = false
}

output "scoring_worker_lambda_name" {
  description = "Name of the Scoring Worker Lambda function"
  value       = module.lambda.scoring_worker_lambda_name
  sensitive   = false
}

# Notificador Lambda
output "notificador_lambda_arn" {
  description = "ARN of the Notificador Lambda function (sends notifications via SES)"
  value       = module.lambda.notificador_lambda_arn
  sensitive   = false
}

output "notificador_lambda_name" {
  description = "Name of the Notificador Lambda function"
  value       = module.lambda.notificador_lambda_name
  sensitive   = false
}

# All Lambda Functions (convenience map)
output "all_lambda_arns" {
  description = "Map of all Lambda function ARNs for easy reference"
  value       = module.lambda.all_lambda_arns
  sensitive   = false
}

output "all_lambda_names" {
  description = "Map of all Lambda function names for monitoring and logs"
  value       = module.lambda.all_lambda_names
  sensitive   = false
}

# ============================================================================
# DynamoDB Table Configuration
# ============================================================================

output "empresas_table_name" {
  description = "DynamoDB Empresas table name (companies data)"
  value       = module.dynamodb.empresas_table_name
  sensitive   = false
}

output "empresas_table_arn" {
  description = "DynamoDB Empresas table ARN"
  value       = module.dynamodb.empresas_table_arn
  sensitive   = false
}

output "vacantes_table_name" {
  description = "DynamoDB Vacantes table name (job vacancies)"
  value       = module.dynamodb.vacantes_table_name
  sensitive   = false
}

output "vacantes_table_arn" {
  description = "DynamoDB Vacantes table ARN"
  value       = module.dynamodb.vacantes_table_arn
  sensitive   = false
}

output "usuario_vacante_table_name" {
  description = "DynamoDB UsuarioVacante table name (user-vacancy relationships)"
  value       = module.dynamodb.usuario_vacante_table_name
  sensitive   = false
}

output "usuario_vacante_table_arn" {
  description = "DynamoDB UsuarioVacante table ARN"
  value       = module.dynamodb.usuario_vacante_table_arn
  sensitive   = false
}

output "entradas_table_name" {
  description = "DynamoDB Entradas table name (interview questions bank)"
  value       = module.dynamodb.entradas_table_name
  sensitive   = false
}

output "entradas_table_arn" {
  description = "DynamoDB Entradas table ARN"
  value       = module.dynamodb.entradas_table_arn
  sensitive   = false
}

output "perfiles_table_name" {
  description = "DynamoDB Perfiles table name (user profiles from CV)"
  value       = module.dynamodb.perfiles_table_name
  sensitive   = false
}

output "perfiles_table_arn" {
  description = "DynamoDB Perfiles table ARN"
  value       = module.dynamodb.perfiles_table_arn
  sensitive   = false
}

output "suscripciones_table_name" {
  description = "DynamoDB Suscripciones table name (user subscriptions to companies)"
  value       = module.dynamodb.suscripciones_table_name
  sensitive   = false
}

output "suscripciones_table_arn" {
  description = "DynamoDB Suscripciones table ARN"
  value       = module.dynamodb.suscripciones_table_arn
  sensitive   = false
}

output "scan_jobs_table_name" {
  description = "DynamoDB ScanJobs table name (scan job tracking)"
  value       = module.dynamodb.scan_jobs_table_name
  sensitive   = false
}

output "scan_jobs_table_arn" {
  description = "DynamoDB ScanJobs table ARN"
  value       = module.dynamodb.scan_jobs_table_arn
  sensitive   = false
}

# All DynamoDB Tables (convenience maps)
output "all_dynamodb_table_names" {
  description = "Map of all DynamoDB table names for Lambda environment variables and monitoring"
  value       = module.dynamodb.all_table_names
  sensitive   = false
}

output "all_dynamodb_table_arns" {
  description = "Map of all DynamoDB table ARNs for IAM policies"
  value       = module.dynamodb.all_table_arns
  sensitive   = false
}

# ============================================================================
# SQS Queue Configuration
# ============================================================================

output "scan_queue_url" {
  description = "URL of the scan-queue (orquestador publishes, scan-worker consumes)"
  value       = module.sqs.scan_queue_url
  sensitive   = false
}

output "scan_queue_arn" {
  description = "ARN of the scan-queue (used for IAM policies)"
  value       = module.sqs.scan_queue_arn
  sensitive   = false
}

output "scan_dlq_arn" {
  description = "ARN of the scan-dlq (Dead Letter Queue for failed scan messages)"
  value       = module.sqs.scan_dlq_arn
  sensitive   = false
}

output "scoring_queue_url" {
  description = "URL of the scoring-queue (scan-worker publishes, scoring-worker consumes)"
  value       = module.sqs.scoring_queue_url
  sensitive   = false
}

output "scoring_queue_arn" {
  description = "ARN of the scoring-queue (used for IAM policies)"
  value       = module.sqs.scoring_queue_arn
  sensitive   = false
}

output "scoring_dlq_arn" {
  description = "ARN of the scoring-dlq (Dead Letter Queue for failed scoring messages)"
  value       = module.sqs.scoring_dlq_arn
  sensitive   = false
}

# ============================================================================
# EventBridge Scheduler Configuration
# ============================================================================

output "eventbridge_scheduler_name" {
  description = "Name of the EventBridge Scheduler schedule for orquestador"
  value       = module.eventbridge.schedule_name
  sensitive   = false
}

output "eventbridge_scheduler_arn" {
  description = "ARN of the EventBridge Scheduler schedule"
  value       = module.eventbridge.schedule_arn
  sensitive   = false
}

output "eventbridge_scheduler_expression" {
  description = "Cron expression for the EventBridge Scheduler (when orquestador is triggered)"
  value       = module.eventbridge.schedule_expression
  sensitive   = false
}

output "eventbridge_scheduler_state" {
  description = "State of the EventBridge Scheduler (ENABLED or DISABLED)"
  value       = module.eventbridge.schedule_state
  sensitive   = false
}

# ============================================================================
# CloudWatch Logging & Monitoring
# ============================================================================

# API Lambda Logs
output "api_log_group_name" {
  description = "CloudWatch log group name for API Lambda (7-day retention)"
  value       = module.cloudwatch.api_log_group_name
  sensitive   = false
}

output "api_log_group_arn" {
  description = "CloudWatch log group ARN for API Lambda"
  value       = module.cloudwatch.api_log_group_arn
  sensitive   = false
}

# Orquestador Lambda Logs
output "orquestador_log_group_name" {
  description = "CloudWatch log group name for Orquestador Lambda (7-day retention)"
  value       = module.cloudwatch.orquestador_log_group_name
  sensitive   = false
}

output "orquestador_log_group_arn" {
  description = "CloudWatch log group ARN for Orquestador Lambda"
  value       = module.cloudwatch.orquestador_log_group_arn
  sensitive   = false
}

# Scan Worker Lambda Logs
output "scan_worker_log_group_name" {
  description = "CloudWatch log group name for Scan Worker Lambda (7-day retention)"
  value       = module.cloudwatch.scan_worker_log_group_name
  sensitive   = false
}

output "scan_worker_log_group_arn" {
  description = "CloudWatch log group ARN for Scan Worker Lambda"
  value       = module.cloudwatch.scan_worker_log_group_arn
  sensitive   = false
}

# Scoring Worker Lambda Logs
output "scoring_worker_log_group_name" {
  description = "CloudWatch log group name for Scoring Worker Lambda (7-day retention)"
  value       = module.cloudwatch.scoring_worker_log_group_name
  sensitive   = false
}

output "scoring_worker_log_group_arn" {
  description = "CloudWatch log group ARN for Scoring Worker Lambda"
  value       = module.cloudwatch.scoring_worker_log_group_arn
  sensitive   = false
}

# Notificador Lambda Logs
output "notificador_log_group_name" {
  description = "CloudWatch log group name for Notificador Lambda (7-day retention)"
  value       = module.cloudwatch.notificador_log_group_name
  sensitive   = false
}

output "notificador_log_group_arn" {
  description = "CloudWatch log group ARN for Notificador Lambda"
  value       = module.cloudwatch.notificador_log_group_arn
  sensitive   = false
}

# SNS Topic for Alarms
output "alerts_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarms notifications"
  value       = module.cloudwatch.alerts_topic_arn
  sensitive   = false
}

output "alerts_topic_name" {
  description = "SNS topic name for CloudWatch alarms notifications"
  value       = module.cloudwatch.alerts_topic_name
  sensitive   = false
}

# CloudWatch Alarms
output "lambda_errors_alarm_arn" {
  description = "Lambda errors alarm ARN (triggers when error count > 0 in 5 minutes)"
  value       = module.cloudwatch.lambda_errors_alarm_arn
  sensitive   = false
}

output "lambda_duration_alarm_arn" {
  description = "Lambda duration alarm ARN (triggers when average duration exceeds threshold)"
  value       = module.cloudwatch.lambda_duration_alarm_arn
  sensitive   = false
}

output "billing_alarm_arn" {
  description = "Billing alarm ARN (triggers when estimated charges exceed threshold)"
  value       = module.cloudwatch.billing_alarm_arn
  sensitive   = false
}

# ============================================================================
# SES Email Configuration
# ============================================================================

output "ses_sender_email" {
  description = "Primary SES sender email address (must be manually verified via email link)"
  value       = module.ses.sender_email
  sensitive   = true
}

output "ses_sender_email_arn" {
  description = "ARN of the SES sender email identity (for IAM policies)"
  value       = module.ses.sender_email_arn
  sensitive   = true
}

output "ses_verification_status" {
  description = "Note: SES sender emails must be manually verified. Check AWS SES Console > Verified Identities for actual status."
  value       = "Check AWS SES Console for verification status"
  sensitive   = false
}

# ============================================================================
# IAM Roles & GitHub Actions OIDC
# ============================================================================

output "api_role_arn" {
  description = "ARN of the API Lambda execution role"
  value       = module.iam.api_role_arn
  sensitive   = false
}

output "orquestador_role_arn" {
  description = "ARN of the Orquestador Lambda execution role"
  value       = module.iam.orquestador_role_arn
  sensitive   = false
}

output "scan_worker_role_arn" {
  description = "ARN of the Scan Worker Lambda execution role"
  value       = module.iam.scan_worker_role_arn
  sensitive   = false
}

output "scoring_worker_role_arn" {
  description = "ARN of the Scoring Worker Lambda execution role"
  value       = module.iam.scoring_worker_role_arn
  sensitive   = false
}

output "notificador_role_arn" {
  description = "ARN of the Notificador Lambda execution role"
  value       = module.iam.notificador_role_arn
  sensitive   = false
}

output "github_actions_role_arn" {
  description = "ARN of the GitHub Actions OIDC role for CI/CD (use in GitHub Actions workflow)"
  value       = module.iam.github_actions_role_arn
  sensitive   = false
}

output "github_oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider (configured for GitHub Actions authentication)"
  value       = module.iam.github_oidc_provider_arn
  sensitive   = false
}

# ============================================================================
# Summary Information & Next Steps
# ============================================================================

output "deployment_summary" {
  description = "Summary of deployed infrastructure endpoints and configuration"
  value = {
    api_endpoint         = module.api_gateway.api_endpoint_url
    frontend_url         = "https://${module.s3_cloudfront.cloudfront_domain_name}"
    cognito_login_url    = module.cognito.hosted_ui_domain_url
    lambda_functions     = module.lambda.all_lambda_names
    dynamodb_tables      = module.dynamodb.all_table_names
    sqs_queues           = { scan = module.sqs.scan_queue_url, scoring = module.sqs.scoring_queue_url }
    eventbridge_schedule = module.eventbridge.schedule_expression
    github_actions_role  = module.iam.github_actions_role_arn
  }
  sensitive = false
}

output "post_deployment_steps" {
  description = "Manual steps required after Terraform deployment"
  value = {
    cognito_callback_url = "Update Cognito App Client callback URLs to: https://${module.s3_cloudfront.cloudfront_domain_name}/callback"
    cognito_logout_url   = "Update Cognito App Client logout URLs to: https://${module.s3_cloudfront.cloudfront_domain_name}/logout"
    ses_verification     = "Manually verify each SES sender email identity by clicking the verification link (check inbox)"
    frontend_deployment  = "Upload built frontend to S3: ${module.s3_cloudfront.s3_bucket_name}"
    cloudfront_cache     = "After frontend deployment, invalidate CloudFront cache: distribution ID ${module.s3_cloudfront.cloudfront_distribution_id}"
    github_actions       = "Use GitHub Actions role ARN ${module.iam.github_actions_role_arn} in CI/CD workflows"
  }
  sensitive = false
}
