# Cognito Module Outputs

output "user_pool_arn" {
  description = "Cognito User Pool ARN (required for API Gateway authorizer)"
  value       = aws_cognito_user_pool.user_pool.arn
}

output "user_pool_id" {
  description = "Cognito User Pool ID"
  value       = var.cognito_user_pool_id
}

output "app_client_id" {
  description = "Cognito App Client ID for frontend"
  value       = aws_cognito_user_pool_client.frontend.id
}

output "hosted_ui_domain" {
  description = "Cognito Hosted UI domain name (without protocol or region)"
  value       = aws_cognito_user_pool_domain.frontend.domain
}

output "hosted_ui_domain_url" {
  description = "Complete Hosted UI domain URL for frontend login construction"
  value       = "https://${aws_cognito_user_pool_domain.frontend.domain}.auth.${data.aws_region.current.name}.amazoncognito.com"
}

# Data source to get the current AWS region
data "aws_region" "current" {}
