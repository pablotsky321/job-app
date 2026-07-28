# Cognito User Pool - Imported from existing resource
# This module imports an existing Cognito User Pool and its associated resources
# The User Pool itself is not managed by Terraform to avoid disrupting existing users

resource "aws_cognito_user_pool" "user_pool" {
  name = "job-search-assistant"

  # This resource is imported, not created by Terraform
  # See import command in scripts/import_resources.sh
  # format: terraform import aws_cognito_user_pool.user_pool <user_pool_id>
  # All attributes are managed by existing AWS console setup.
  # Terraform will adopt the existing configuration during import.
}

# Cognito App Client - job-search-frontend
# IMPORTED, not created: this App Client already exists in AWS
# Attributes must match the real client exactly or Terraform will attempt to
# modify/recreate it on the first plan after import.
resource "aws_cognito_user_pool_client" "frontend" {
  user_pool_id = var.cognito_user_pool_id

  name                                 = "job-search-frontend"
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  callback_urls                        = ["http://localhost:5173/callback"]
  logout_urls                          = ["http://localhost:5173/logout"]
  explicit_auth_flows                  = ["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  refresh_token_validity               = 60
  supported_identity_providers         = ["COGNITO"]
  enable_token_revocation              = true

  # prevent_user_existence_errors intentionally OMITTED:
  # AWS describe-user-pool-client confirmed the live value is null (never configured).
  # Omitting the argument matches that null state and avoids Terraform attempting
  # to set ENABLED/LEGACY on apply.
}

# Cognito Hosted UI Domain
# This domain is used for the hosted UI login page
resource "aws_cognito_user_pool_domain" "frontend" {
  domain       = "job-search-assistant-mvp"
  user_pool_id = var.cognito_user_pool_id
}
