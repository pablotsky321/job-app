# Variables for SES Module

variable "ses_email" {
  description = "Primary sender email address for SES notifications (must be verified in SES)"
  type        = string
  validation {
    condition     = can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.ses_email))
    error_message = "ses_email must be a valid email address."
  }
}

variable "ses_team_emails" {
  description = "List of team email addresses for SES verification (must be verified before sending)"
  type        = list(string)
  default     = []
  validation {
    condition = alltrue([
      for email in var.ses_team_emails : can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", email))
    ])
    error_message = "All ses_team_emails must be valid email addresses."
  }
}

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"
}
