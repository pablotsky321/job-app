# Cognito Module Variables

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID to import (required)"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]+_[a-zA-Z0-9]+$", var.cognito_user_pool_id))
    error_message = "User Pool ID must be in the format 'region_id' (e.g., 'us-east-1_abc123')."
  }
}
