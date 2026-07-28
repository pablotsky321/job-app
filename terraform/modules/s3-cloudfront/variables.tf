# S3 + CloudFront Module Variables
#
# Variables required for S3 bucket and CloudFront distribution configuration

# Frontend S3 Bucket Name
# Must be globally unique across all AWS accounts
# This bucket will store all frontend React SPA assets
variable "frontend_bucket_name" {
  description = "S3 bucket name for frontend assets (must be globally unique)"
  type        = string
  # No default - must be provided by root module
}

