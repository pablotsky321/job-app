# Outputs for IAM Module
#
# These outputs export the IAM role ARNs and resource identifiers
# for use by other modules (Lambda, EventBridge, etc.)

# ============================================================================
# Lambda Execution Role ARNs
# ============================================================================

output "api_role_arn" {
  description = "ARN of the API Lambda execution role"
  value       = aws_iam_role.api_role.arn
}

output "orquestador_role_arn" {
  description = "ARN of the Orquestador Lambda execution role"
  value       = aws_iam_role.orquestador_role.arn
}

output "scan_worker_role_arn" {
  description = "ARN of the Scan Worker Lambda execution role"
  value       = aws_iam_role.scan_worker_role.arn
}

output "scoring_worker_role_arn" {
  description = "ARN of the Scoring Worker Lambda execution role"
  value       = aws_iam_role.scoring_worker_role.arn
}

output "notificador_role_arn" {
  description = "ARN of the Notificador Lambda execution role"
  value       = aws_iam_role.notificador_role.arn
}

# ============================================================================
# EventBridge Scheduler Invoke Role ARN
# ============================================================================

output "eventbridge_scheduler_role_arn" {
  description = "ARN of the EventBridge Scheduler role for invoking Lambda functions"
  value       = aws_iam_role.eventbridge_scheduler_role.arn
}

# ============================================================================
# GitHub Actions OIDC Role ARN
# ============================================================================

output "github_actions_role_arn" {
  description = "ARN of the GitHub Actions OIDC role for CI/CD deployments"
  value       = aws_iam_role.github_actions.arn
}

# ============================================================================
# GitHub OIDC Provider ARN
# ============================================================================

output "github_oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider"
  value       = aws_iam_openid_connect_provider.github.arn
}


# ============================================================================
# API Gateway CloudWatch Logging Role ARN
# ============================================================================

output "api_gateway_cloudwatch_role_arn" {
  description = "ARN of the API Gateway CloudWatch logging role"
  value       = aws_iam_role.api_gateway_cloudwatch_role.arn
}
