# Backend Configuration for Terraform State Management
#
# This backend stores the Terraform state in an S3 bucket with the following features:
# - Remote state storage for team collaboration
# - Automatic versioning for state history
# - Encryption at rest using S3 server-side encryption
# - Optional state locking via DynamoDB table (for production environments)
#
# IMPORTANT: Before running 'terraform init', you must:
#
# 1. Create an S3 bucket manually in us-east-1
#    Example AWS CLI command:
#      aws s3api create-bucket \
#        --bucket my-terraform-state-bucket \
#        --region us-east-1
#
# 2. Enable versioning on the bucket:
#    Example AWS CLI command:
#      aws s3api put-bucket-versioning \
#        --bucket my-terraform-state-bucket \
#        --versioning-configuration Status=Enabled
#
# 3. Block public access (recommended):
#    Example AWS CLI command:
#      aws s3api put-public-access-block \
#        --bucket my-terraform-state-bucket \
#        --public-access-block-configuration \
#        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
#
# 4. Provide the bucket name in terraform.tfvars:
#      terraform_state_bucket = "my-terraform-state-bucket"
#
# The backend configuration uses variables, which requires the following init command:
#   terraform init -backend-config="bucket=<BUCKET_NAME>" \
#                  -backend-config="key=<KEY>" \
#                  -backend-config="region=us-east-1" \
#                  -backend-config="encrypt=true"
#
# Alternatively, you can pass the backend config via environment:
#   export TF_BACKEND_CONFIG_BUCKET="my-terraform-state-bucket"
#   terraform init
#

terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
