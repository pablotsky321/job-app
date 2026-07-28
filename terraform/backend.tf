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
# 4. Provide the actual bucket/key/region/encrypt values in backend-config.hcl
#    (this file is gitignored — see terraform/backend-config.hcl for the real values)
#
# The block below is intentionally empty. All backend settings (bucket, key,
# region, encrypt) are supplied at init time via the -backend-config flag:
#
#   terraform init -backend-config=backend-config.hcl
#
# This keeps real deployment values (bucket name, etc.) out of committed files,
# consistent with how terraform.tfvars is handled.

terraform {
  backend "s3" {}
}
