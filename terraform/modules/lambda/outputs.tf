# Outputs for Lambda Module
#
# These outputs export Lambda function ARNs, names, and other identifiers
# for use by other modules (API Gateway, EventBridge, CloudWatch, etc.)
#
# References:
# - Requirements: 5, 16
# - Design: Lambda functions integration with API Gateway, SQS, EventBridge

# ============================================================================
# API Lambda Function
# ============================================================================

output "api_lambda_arn" {
  description = "ARN of the API Lambda function"
  value       = aws_lambda_function.api.arn
}

output "api_lambda_name" {
  description = "Name of the API Lambda function"
  value       = aws_lambda_function.api.function_name
}

output "api_lambda_invoke_arn" {
  description = "Invoke ARN of the API Lambda function (for API Gateway integration)"
  value       = aws_lambda_function.api.invoke_arn
}

# ============================================================================
# Orquestador Lambda Function
# ============================================================================

output "orquestador_lambda_arn" {
  description = "ARN of the Orquestador Lambda function"
  value       = aws_lambda_function.orquestador.arn
}

output "orquestador_lambda_name" {
  description = "Name of the Orquestador Lambda function"
  value       = aws_lambda_function.orquestador.function_name
}

output "orquestador_lambda_invoke_arn" {
  description = "Invoke ARN of the Orquestador Lambda function (for EventBridge integration)"
  value       = aws_lambda_function.orquestador.invoke_arn
}

# ============================================================================
# Scan Worker Lambda Function
# ============================================================================

output "scan_worker_lambda_arn" {
  description = "ARN of the Scan Worker Lambda function"
  value       = aws_lambda_function.scan_worker.arn
}

output "scan_worker_lambda_name" {
  description = "Name of the Scan Worker Lambda function"
  value       = aws_lambda_function.scan_worker.function_name
}

# ============================================================================
# Scoring Worker Lambda Function
# ============================================================================

output "scoring_worker_lambda_arn" {
  description = "ARN of the Scoring Worker Lambda function"
  value       = aws_lambda_function.scoring_worker.arn
}

output "scoring_worker_lambda_name" {
  description = "Name of the Scoring Worker Lambda function"
  value       = aws_lambda_function.scoring_worker.function_name
}

# ============================================================================
# Notificador Lambda Function
# ============================================================================

output "notificador_lambda_arn" {
  description = "ARN of the Notificador Lambda function"
  value       = aws_lambda_function.notificador.arn
}

output "notificador_lambda_name" {
  description = "Name of the Notificador Lambda function"
  value       = aws_lambda_function.notificador.function_name
}

# ============================================================================
# All Lambda ARNs (for convenience)
# ============================================================================

output "all_lambda_arns" {
  description = "Map of all Lambda function ARNs"
  value = {
    api            = aws_lambda_function.api.arn
    orquestador    = aws_lambda_function.orquestador.arn
    scan_worker    = aws_lambda_function.scan_worker.arn
    scoring_worker = aws_lambda_function.scoring_worker.arn
    notificador    = aws_lambda_function.notificador.arn
  }
}

# ============================================================================
# All Lambda Names (for convenience)
# ============================================================================

output "all_lambda_names" {
  description = "Map of all Lambda function names"
  value = {
    api            = aws_lambda_function.api.function_name
    orquestador    = aws_lambda_function.orquestador.function_name
    scan_worker    = aws_lambda_function.scan_worker.function_name
    scoring_worker = aws_lambda_function.scoring_worker.function_name
    notificador    = aws_lambda_function.notificador.function_name
  }
}

# ============================================================================
# All Lambda Invoke ARNs (for API Gateway and EventBridge integration)
# ============================================================================

output "all_lambda_invoke_arns" {
  description = "Map of all Lambda function invoke ARNs"
  value = {
    api            = aws_lambda_function.api.invoke_arn
    orquestador    = aws_lambda_function.orquestador.invoke_arn
    scan_worker    = aws_lambda_function.scan_worker.invoke_arn
    scoring_worker = aws_lambda_function.scoring_worker.invoke_arn
    notificador    = aws_lambda_function.notificador.invoke_arn
  }
}
