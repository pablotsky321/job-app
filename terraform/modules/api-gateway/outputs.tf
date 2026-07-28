# API Gateway Module - Outputs
#
# These outputs are exported for use by the root module
# and for display to users

output "rest_api_id" {
  description = "ID of the REST API"
  value       = aws_api_gateway_rest_api.api.id
}

output "rest_api_arn" {
  description = "ARN of the REST API"
  value       = aws_api_gateway_rest_api.api.arn
}

output "rest_api_root_resource_id" {
  description = "Root resource ID of the REST API"
  value       = aws_api_gateway_rest_api.api.root_resource_id
}

output "api_gateway_stage_name" {
  description = "Name of the deployed stage (prod)"
  value       = aws_api_gateway_stage.prod.stage_name
}

output "api_endpoint_url" {
  description = "URL of the API Gateway endpoint"
  value       = aws_api_gateway_stage.prod.invoke_url
}

output "api_execution_arn" {
  description = "Execution ARN for the API"
  value       = aws_api_gateway_rest_api.api.execution_arn
}

output "cognito_authorizer_id" {
  description = "ID of the Cognito authorizer"
  value       = aws_api_gateway_authorizer.cognito.id
}
