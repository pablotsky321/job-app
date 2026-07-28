terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend configuration is managed in backend.tf
  # The backend.tf file should be configured with S3 state storage
  # S3 bucket must be created manually before Terraform initialization
}
