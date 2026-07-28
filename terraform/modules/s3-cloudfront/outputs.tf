# S3 + CloudFront Module Outputs
#
# Exports the following outputs for use by the root module:
# - s3_bucket_name: Name of the S3 bucket for frontend assets
# - cloudfront_domain_name: CloudFront distribution domain (used by frontend)
# - cloudfront_distribution_id: CloudFront distribution ID (used for invalidations)

# S3 Bucket Name
# Used by deployment processes to upload frontend assets
output "s3_bucket_name" {
  description = "S3 bucket name for frontend assets"
  value       = aws_s3_bucket.frontend.id
}

# CloudFront Distribution Domain Name
# This is the domain where the frontend is served
# Format: d123456789.cloudfront.net
# Used by the frontend to construct absolute URLs or by DNS configuration
output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name (*.cloudfront.net)"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

# CloudFront Distribution ID
# Used for creating cache invalidations after deploying new frontend versions
# Example: terraform import aws_cloudfront_distribution.frontend <distribution_id>
output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID for cache invalidations"
  value       = aws_cloudfront_distribution.frontend.id
}

