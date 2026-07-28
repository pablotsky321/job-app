# Outputs for EventBridge Scheduler Module
#
# These outputs export the EventBridge Scheduler schedule configuration
# for monitoring and integration with other resources.
#
# References:
# - Requirements: 10, 16
# - Design: "EventBridge Scheduler Module"

# ============================================================================
# EventBridge Scheduler Schedule Outputs
# ============================================================================

output "schedule_arn" {
  description = "ARN of the EventBridge Scheduler schedule"
  value       = aws_scheduler_schedule.orquestador.arn
}

output "schedule_name" {
  description = "Name of the EventBridge Scheduler schedule"
  value       = aws_scheduler_schedule.orquestador.name
}

output "schedule_state" {
  description = "State of the EventBridge Scheduler schedule (ENABLED or DISABLED)"
  value       = aws_scheduler_schedule.orquestador.state
}

output "schedule_expression" {
  description = "Cron expression for the schedule"
  value       = aws_scheduler_schedule.orquestador.schedule_expression
}

output "schedule_timezone" {
  description = "Timezone for the schedule"
  value       = aws_scheduler_schedule.orquestador.schedule_expression_timezone
}

# ============================================================================
# Target Lambda Function Information
# ============================================================================

output "target_lambda_arn" {
  description = "ARN of the target Lambda function (orquestador)"
  value       = aws_scheduler_schedule.orquestador.target[0].arn
}

output "target_role_arn" {
  description = "ARN of the IAM role used by the Scheduler to invoke the Lambda function"
  value       = aws_scheduler_schedule.orquestador.target[0].role_arn
}
