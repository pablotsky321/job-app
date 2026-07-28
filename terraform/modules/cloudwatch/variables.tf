variable "lambda_function_names" {
  description = "Map of Lambda function names for creating log groups"
  type = object({
    api            = string
    orquestador    = string
    scan_worker    = string
    scoring_worker = string
    notificador    = string
  })
}

variable "retention_in_days" {
  description = "CloudWatch log group retention period in days"
  type        = number
  default     = 7

  validation {
    condition     = var.retention_in_days > 0
    error_message = "Retention period must be positive."
  }
}

variable "api_function_name" {
  description = "API Lambda function name for alarms"
  type        = string
}

variable "lambda_duration_threshold_ms" {
  description = "Lambda duration threshold in milliseconds for alarms (default: 50 seconds = 50000ms)"
  type        = number
  default     = 50000

  validation {
    condition     = var.lambda_duration_threshold_ms > 0
    error_message = "Duration threshold must be positive."
  }
}

variable "billing_alarm_threshold" {
  description = "Monthly billing threshold in USD for billing alarm"
  type        = number
  default     = 500

  validation {
    condition     = var.billing_alarm_threshold > 0
    error_message = "Billing threshold must be positive."
  }
}
