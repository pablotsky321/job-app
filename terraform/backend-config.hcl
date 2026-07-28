# Backend configuration for Terraform state management
# This file is used by: terraform init -backend-config=backend-config.hcl

bucket         = "job-search-terraform-state"
key            = "terraform.tfstate"
region         = "us-east-1"
encrypt        = true

# Optional: Enable state locking (requires DynamoDB table)
# dynamodb_table = "terraform-state-lock"
