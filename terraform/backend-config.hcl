# Backend configuration for Terraform state management
# This file is used by: terraform init -backend-config=backend-config.hcl

bucket         = "job-search-terraform-state-5543569870"
key            = "terraform.tfstate"
region         = "us-east-1"
encrypt        = true

# Optional: Enable state locking (requires DynamoDB table)
# dynamodb_table = "terraform-state-lock"
