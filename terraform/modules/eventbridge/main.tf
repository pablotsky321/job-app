# EventBridge Scheduler Module - job-search-assistant
#
# This module creates an EventBridge Scheduler schedule to trigger the orquestador
# Lambda function periodically for scanning companies and finding new vacancies.
#
# Purpose: Automate the job scanning process on a fixed schedule (default: every 6 hours)
# Trigger: EventBridge Scheduler (cron expression)
# Target: Invoke orquestador Lambda function
# Execution Role: EventBridge Scheduler role from the IAM module
#
# References:
# - Requirements: 10, 14, 16
# - Design: "EventBridge Scheduler Module", "Resource Dependencies Order"
# - Backend-Scan-Y-Scoring: Orquestador orchestrates scan job creation

# ============================================================================
# EventBridge Scheduler Schedule for Orquestador
# ============================================================================
#
# This schedule invokes the orquestador Lambda function on a periodic basis.
# The schedule expression uses AWS Scheduler cron syntax:
#   - cron(minute hour day month weekday year)
#   - cron(0 8,12,18 * * ? *) = every day at 8 AM, 12 PM, 6 PM UTC
#   - The default expression can be overridden via variable
#
# The Scheduler uses a flexible time window set to OFF for strict execution time
# (no flexibility - execute at exactly the scheduled time).
#
# The target is the orquestador Lambda function ARN, which must be passed via
# variable from the lambda module output.
#
# The execution role (passed via variable from the iam module output) grants
# the EventBridge Scheduler service permission to invoke the orquestador Lambda.

resource "aws_scheduler_schedule" "orquestador" {
  # Schedule name
  name = "job-search-orquestador-schedule"

  # Schedule expression - cron format (default: every 6 hours)
  # Can be overridden via variable
  schedule_expression = var.schedule_expression

  # Timezone for the cron expression
  schedule_expression_timezone = var.timezone

  # Flexible time window - set to OFF for strict execution time
  # OFF means execute at exactly the scheduled time, no flexibility
  flexible_time_window {
    mode = "OFF"
  }

  # Enable the schedule by default
  state = var.orquestador_schedule_state

  # Target Lambda function
  target {
    # ARN of the orquestador Lambda function
    arn = var.orquestador_lambda_arn

    # IAM role for the Scheduler to assume when invoking the Lambda
    # This role must have permissions to invoke the Lambda function
    role_arn = var.eventbridge_scheduler_role_arn

    # Input payload to pass to the Lambda function
    # Sent as a JSON string representing the event
    input = jsonencode({
      source = "scheduled"
      detail = {
        trigger = "eventbridge-scheduler"
      }
    })
  }

  # Tags are applied via provider default_tags - direct tags argument not supported
}
