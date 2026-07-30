# Variables for EventBridge Scheduler Module
#
# This module creates an EventBridge Scheduler schedule to trigger the
# orquestador Lambda function periodically.
#
# The schedule can be customized via the following variables:
# - schedule_expression: Cron expression for the schedule (default: every 6 hours)
# - timezone: Timezone for interpreting the cron expression (default: UTC)
# - orquestador_lambda_arn: ARN of the orquestador Lambda function (required)
# - eventbridge_scheduler_role_arn: ARN of the IAM role for Scheduler to invoke Lambda (required)

# ============================================================================
# Lambda Function Configuration
# ============================================================================

variable "orquestador_lambda_arn" {
  description = "ARN of the orquestador Lambda function to be invoked by the schedule"
  type        = string
}

variable "orquestador_lambda_invoke_arn" {
  description = "Invoke ARN of the orquestador Lambda function (from Lambda module output)"
  type        = string
}

# ============================================================================
# EventBridge Scheduler Execution Role
# ============================================================================

variable "eventbridge_scheduler_role_arn" {
  description = "ARN of the IAM role for EventBridge Scheduler to invoke Lambda functions"
  type        = string
}

# ============================================================================
# Schedule Configuration
# ============================================================================

variable "schedule_expression" {
  description = "Cron expression for the schedule (e.g., 'cron(0 */6 * * ? *)')"
  type        = string
  default     = "cron(0 8,12,18 * * ? *)"

  validation {
    condition     = can(regex("^cron\\(", var.schedule_expression))
    error_message = "Schedule expression must be a valid AWS EventBridge Scheduler cron expression (e.g., 'cron(0 8,12,18 * * ? *)')"
  }
}

variable "timezone" {
  description = "Timezone for interpreting the cron expression (e.g., 'UTC', 'America/New_York')"
  type        = string
  default     = "UTC"

  validation {
    condition     = can(regex("^[A-Z]", var.timezone)) # Simple validation - must start with uppercase letter
    error_message = "Timezone must be a valid IANA timezone identifier (e.g., 'UTC', 'America/New_York')"
  }
}

variable "orquestador_schedule_state" {
  description = "State of the EventBridge Scheduler schedule (ENABLED or DISABLED). Default is DISABLED to prevent automatic triggering until manual testing is confirmed against AWS real services."
  type        = string
  default     = "DISABLED"

  validation {
    condition     = contains(["ENABLED", "DISABLED"], var.orquestador_schedule_state)
    error_message = "Schedule state must be either 'ENABLED' or 'DISABLED'"
  }
}

# ============================================================================
# Environment Configuration
# ============================================================================

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod, hackathon)"
  type        = string
  default     = "hackathon"
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
  default     = "job-search-assistant"
}
