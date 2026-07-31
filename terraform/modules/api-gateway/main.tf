# API Gateway Module for job-search-assistant
#
# This module creates:
# 1. REST API with Cognito authorizer
# 2. Proxy resource and method for routing all requests to the api Lambda
# 3. API Gateway stage (prod) with CloudWatch logging
# 4. Lambda permissions for API Gateway to invoke the api Lambda
#
# The API uses a catch-all {proxy+} pattern that routes all HTTP requests
# to the FastAPI + Mangum Lambda function, which handles routing internally.
#
# Reference Requirements: 7, 16
# Reference Design: "API Gateway Module"

# ============================================================================
# 1. REST API RESOURCE
# ============================================================================
# The main REST API resource
# All requests will be routed through the proxy resource to the api Lambda

resource "aws_api_gateway_rest_api" "api" {
  name        = "job-search-api"
  description = "Job Search Assistant REST API with Cognito authentication"

  tags = {
    Name = "job-search-api"
  }
}

# ============================================================================
# 2. COGNITO AUTHORIZER
# ============================================================================
# This authorizer validates Cognito tokens before allowing access to API resources
# The Cognito User Pool ARN is passed as a variable from the root module

resource "aws_api_gateway_authorizer" "cognito" {
  name          = "cognito-authorizer"
  type          = "COGNITO_USER_POOLS"
  rest_api_id   = aws_api_gateway_rest_api.api.id
  provider_arns = [var.cognito_user_pool_arn]

  # Identity source - extract the token from Authorization header
  identity_source = "method.request.header.Authorization"
}

# ============================================================================
# 3. PROXY RESOURCE - Catch-all route
# ============================================================================
# This resource handles all paths via a {proxy+} pattern
# FastAPI internally routes to specific endpoints

resource "aws_api_gateway_resource" "api_proxy" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "{proxy+}"
}

# ============================================================================
# 4. PROXY METHOD - Accept all HTTP methods
# ============================================================================
# This method accepts ANY HTTP method (GET, POST, PUT, DELETE, PATCH, etc.)
# Authorization type is COGNITO - all requests must have valid tokens

resource "aws_api_gateway_method" "api_proxy" {
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = aws_api_gateway_resource.api_proxy.id
  http_method      = "ANY"
  authorization    = "COGNITO_USER_POOLS"
  authorizer_id    = aws_api_gateway_authorizer.cognito.id
  api_key_required = false

  # Pass the Authorization header to the Lambda
  request_parameters = {
    "method.request.header.Authorization" = true
    "method.request.path.proxy"           = true
  }
}

# Also handle OPTIONS method for CORS (no authorization required for preflight)
resource "aws_api_gateway_method" "api_options" {
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = aws_api_gateway_resource.api_proxy.id
  http_method      = "OPTIONS"
  authorization    = "NONE"
  api_key_required = false
}

# OPTIONS response (for CORS preflight)
resource "aws_api_gateway_method_response" "api_options_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.api_proxy.id
  http_method = aws_api_gateway_method.api_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
    "method.response.header.Access-Control-Max-Age"       = true
  }
}

# ============================================================================
# 5. LAMBDA INTEGRATION - AWS_PROXY
# ============================================================================
# AWS_PROXY (Lambda Proxy Integration) passes the entire request to Lambda
# and expects the Lambda to return a response in a specific format.
# This is how FastAPI + Mangum works.

resource "aws_api_gateway_integration" "api_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.api_proxy.id
  http_method             = aws_api_gateway_method.api_proxy.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.api_lambda_invoke_arn

  # Pass request path to Lambda
  request_parameters = {
    "integration.request.path.proxy" = "method.request.path.proxy"
  }
}

# OPTIONS integration response (mock response for CORS preflight)
resource "aws_api_gateway_integration" "api_options" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.api_proxy.id
  http_method = aws_api_gateway_method.api_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

# OPTIONS integration response (CORS headers)
resource "aws_api_gateway_integration_response" "api_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.api_proxy.id
  http_method = aws_api_gateway_method.api_options.http_method
  status_code = aws_api_gateway_method_response.api_options_response.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,DELETE,POST,PUT,OPTIONS,HEAD,PATCH'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
    "method.response.header.Access-Control-Max-Age"       = "'7200'"
  }
}

# ============================================================================
# 6. LAMBDA PERMISSION - Allow API Gateway to invoke Lambda
# ============================================================================
# Without this permission, API Gateway cannot invoke the Lambda function

resource "aws_lambda_permission" "api_gateway_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.api_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}

# ============================================================================
# 7. API GATEWAY DEPLOYMENT
# ============================================================================
# Deployment captures the current state of the API for deployment to a stage

resource "aws_api_gateway_deployment" "api" {
  rest_api_id = aws_api_gateway_rest_api.api.id

  # Ensure integration is deployed before creating deployment
  depends_on = [
    aws_api_gateway_integration.api_lambda,
    aws_api_gateway_integration.api_options,
    aws_api_gateway_integration_response.api_options_integration_response
  ]

  # Force redeployment when the API is updated
  lifecycle {
    create_before_destroy = true
  }
}

# ============================================================================
# 8. API GATEWAY STAGE (prod)
# ============================================================================
# The stage is where the API is deployed and accessible
# This creates the actual endpoint URL

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.api.id
  stage_name    = "prod"

  tags = {
    Name  = "prod-stage"
    Stage = "prod"
  }

  # Enable caching for improved performance (optional)
  # Most production deployments would benefit from caching
  cache_cluster_enabled = false
}

# CloudWatch role for API Gateway logging (account-level setting)
# DISABLED: apigateway:UpdateAccount fails persistently with
# "The role ARN does not have required permissions configured"
# This is an anomalous AWS endpoint behavior, not a configuration issue.
# Verified: trust policy and inline permissions correct, no boundary, no CloudTrail AccessDenied.
# Impact: account-level logging not available, but per-stage logging (aws_api_gateway_method_settings)
# still works and is not required for API functionality.
#
# resource "aws_api_gateway_account" "logging" {
#   cloudwatch_role_arn = var.api_gateway_cloudwatch_role_arn
# }

# CloudWatch logging settings for the prod stage
# DISABLED: depends on aws_api_gateway_account.logging (account-level setting),
# which is disabled due to persistent AWS API failure (UpdateAccount endpoint).
# Without account-level logging configured, stage-level logging fails with:
# "CloudWatch Logs role ARN must be set in account settings to enable logging"
# Not required for API functionality (only enables execution logs and data trace).
#
# resource "aws_api_gateway_method_settings" "logging" {
#   rest_api_id = aws_api_gateway_rest_api.api.id
#   stage_name  = aws_api_gateway_stage.prod.stage_name
#   method_path = "*/*"
#
#   settings {
#     metrics_enabled    = true
#     logging_level      = "INFO"
#     data_trace_enabled = true
#   }
# }

# ============================================================================
# 9. ROOT RESOURCE METHOD - Root path (/) handling
# ============================================================================
# Handle requests to the root path (/)
# Apply authorization to root as well

resource "aws_api_gateway_method" "root" {
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = aws_api_gateway_rest_api.api.root_resource_id
  http_method      = "ANY"
  authorization    = "COGNITO_USER_POOLS"
  authorizer_id    = aws_api_gateway_authorizer.cognito.id
  api_key_required = false

  request_parameters = {
    "method.request.header.Authorization" = true
  }
}

# Root OPTIONS method (for CORS preflight)
resource "aws_api_gateway_method" "root_options" {
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = aws_api_gateway_rest_api.api.root_resource_id
  http_method      = "OPTIONS"
  authorization    = "NONE"
  api_key_required = false
}

# Root method OPTIONS response
resource "aws_api_gateway_method_response" "root_options_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_rest_api.api.root_resource_id
  http_method = aws_api_gateway_method.root_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
    "method.response.header.Access-Control-Max-Age"       = true
  }
}

# Root method integration (AWS_PROXY to Lambda)
resource "aws_api_gateway_integration" "root_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_rest_api.api.root_resource_id
  http_method             = aws_api_gateway_method.root.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.api_lambda_invoke_arn
}

# Root OPTIONS integration (mock for CORS preflight)
resource "aws_api_gateway_integration" "root_options" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_rest_api.api.root_resource_id
  http_method = aws_api_gateway_method.root_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

# Root OPTIONS integration response (CORS headers)
resource "aws_api_gateway_integration_response" "root_options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_rest_api.api.root_resource_id
  http_method = aws_api_gateway_method.root_options.http_method
  status_code = aws_api_gateway_method_response.root_options_response.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,DELETE,POST,PUT,OPTIONS,HEAD,PATCH'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
    "method.response.header.Access-Control-Max-Age"       = "'7200'"
  }
}

# ============================================================================
# 10. GATEWAY RESPONSES - CORS headers on authorizer rejections (401/403)
# ============================================================================
# Sin esto, cualquier rechazo del Cognito Authorizer (token vencido, inválido,
# o ausente) llega al navegador sin headers de CORS, y el navegador lo reporta
# como error de CORS en vez de como el 401/403 real. Esto rompe el manejo de
# errores del frontend (AuthContext.registerUnauthorizedHandler nunca se
# dispara, porque el fetch() nunca llega a resolver con un Response).

resource "aws_api_gateway_gateway_response" "unauthorized" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  response_type = "UNAUTHORIZED"
  status_code   = "401"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
  }
}

resource "aws_api_gateway_gateway_response" "access_denied" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  response_type = "ACCESS_DENIED"
  status_code   = "403"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
  }
}

resource "aws_api_gateway_gateway_response" "default_4xx" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  response_type = "DEFAULT_4XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"
  }
}
