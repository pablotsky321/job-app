# Cognito User Pool - Imported from existing resource
resource "aws_cognito_user_pool" "user_pool" {
  name = "job-search-assistant"

  # Valores reales confirmados
  username_attributes       = ["email"]
  auto_verified_attributes  = ["email"]

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  schema {
    name                     = "email"
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = true
    required                 = true

    string_attribute_constraints {
      min_length = "0"
      max_length = "2048"
    }
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
    recovery_mechanism {
      name     = "verified_phone_number"
      priority = 2
    }
  }

  tags = {
    Entorno  = "hackathon"
    Proyecto = "job-search-assistant"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Cognito App Client - job-search-frontend
resource "aws_cognito_user_pool_client" "frontend" {
  user_pool_id                         = var.cognito_user_pool_id
  name                                 = "job-search-frontend"
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  callback_urls                        = [
                                            "http://localhost:5173/callback",
                                            "https://do3z0o80ae5xj.cloudfront.net/callback"
                                          ]
  logout_urls                          = [
                                            "http://localhost:5173/logout",
                                            "https://do3z0o80ae5xj.cloudfront.net/logout"
                                          ]
  explicit_auth_flows                  = ["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  refresh_token_validity               = 60
  access_token_validity                = 60
  id_token_validity                    = 60
  supported_identity_providers         = ["COGNITO"]
  enable_token_revocation              = true

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "minutes"
  }

  lifecycle {
    ignore_changes = [generate_secret]
  }
}

# Cognito Hosted UI Domain
resource "aws_cognito_user_pool_domain" "frontend" {
  domain       = "job-search-assistant-mvp"
  user_pool_id = var.cognito_user_pool_id
}