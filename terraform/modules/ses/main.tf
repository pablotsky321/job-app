# SES Module for Email Configuration
# This module configures Amazon SES for sending email notifications
# Note: Email identities must be manually verified by clicking a verification link sent to the email address

# Create SES email identities for sending emails
# These identities will be in "Pending" status until manually verified
resource "aws_ses_email_identity" "sender_emails" {
  for_each = toset(var.ses_team_emails)

  email = each.value
}

# Get AWS account ID for ARN construction (used by outputs.tf)
data "aws_caller_identity" "current" {}

/*
SANDBOX MODE LIMITATIONS:
- Maximum send rate: 1 email per second
- Maximum daily sending limit: 200 emails per day
- Can only send TO verified addresses (not just FROM verified addresses)

MOVING TO PRODUCTION:
1. Request production access via the AWS SES Console:
   - Go to: https://console.aws.amazon.com/sesv2/home#/account
   - Click "Get sending limits"
   - Follow the prompts to request production access
2. AWS will review the request (usually within 24 hours)
3. Once approved, sandbox restrictions are lifted

MANUAL VERIFICATION STEPS:
1. After terraform apply, check AWS Console: SES > Verified Identities
2. Each email in "Pending" status needs manual verification:
   - AWS sends a verification email to the address
   - Click the verification link in the email
   - Status changes to "Verified"
3. Only verified email addresses can be used as sender addresses in SES
*/
