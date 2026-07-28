# API Gateway Module - Input Variables
#
# These variables are passed from the root module's main.tf
# They define the configuration for the API Gateway REST API

variable "api_lambda_invoke_arn" {
  description = "ARN for Lambda invoke permission (api Lambda function)"
  type        = string
}

variable "api_lambda_function_name" {
  description = "Name of the api Lambda function"
  type        = string
}

variable "cognito_user_pool_arn" {
  description = "ARN of the Cognito User Pool for authorization"
  type        = string
}

variable "api_log_group_name" {
  description = "CloudWatch Log Group name for API Gateway"
  type        = string
}

variable "api_gateway_cloudwatch_role_arn" {
  description = "IAM role ARN for API Gateway to write to CloudWatch Logs"
  type        = string
}
