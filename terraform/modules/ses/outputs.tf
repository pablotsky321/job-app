# Outputs for SES Module

output "sender_email" {
  description = "Primary sender email address for SES (Lambda environment variable)"
  value       = var.ses_email
  sensitive   = true
}

output "sender_email_arn" {
  description = "ARN of the primary sender email identity (for IAM policies if needed)"
  value       = "arn:aws:ses:${var.aws_region}:${data.aws_caller_identity.current.account_id}:identity/${var.ses_email}"
  sensitive   = true
}

output "sender_email_verification_status" {
  description = "Status of sender email verification (requires manual verification from email link)"
  value       = "Check AWS SES Console > Verified Identities for actual status"
}

output "team_emails_created" {
  description = "List of team email identities created (all require manual verification)"
  value       = var.ses_team_emails
  sensitive   = true
}
