# S3 + CloudFront Module for Frontend Static Hosting
#
# This module creates:
# 1. S3 bucket for storing frontend assets (React SPA)
# 2. CloudFront distribution for serving the SPA with SPA-specific routing
#
# Features:
# - S3 versioning enabled
# - Public access blocked (all traffic goes through CloudFront)
# - CloudFront default certificate (no custom domain)
# - SPA routing support: 403/404 errors mapped to /index.html with 200 status
# - HTTPS enforcement: redirect HTTP to HTTPS
# - Headers forwarding for SPA routing
#
# Requirements: 9, 16

# S3 Bucket for Frontend Assets
# Purpose: Store React SPA static files (HTML, CSS, JS, images)
# Access: Private - all traffic must go through CloudFront
resource "aws_s3_bucket" "frontend" {
  bucket        = var.frontend_bucket_name
  force_destroy = true

  tags = {
    Purpose = "Frontend static assets for React SPA"
  }
}

# Enable Versioning on S3 bucket
# This allows recovery of previous versions of files if needed
resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Block All Public Access to S3 Bucket
# All traffic must go through CloudFront, never directly to S3
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudFront Origin Access Identity (OAI)
# Used to allow CloudFront to access the private S3 bucket
# without exposing the bucket to public access
resource "aws_cloudfront_origin_access_identity" "frontend" {
  comment = "Job Search Assistant CloudFront OAI"
}

# S3 Bucket Policy
# Allow CloudFront OAI to read objects from the bucket
resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAI"
        Effect = "Allow"
        Principal = {
          AWS = aws_cloudfront_origin_access_identity.frontend.iam_arn
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend.arn}/*"
      }
    ]
  })
}

# CloudFront Distribution
# Serves the React SPA with:
# - HTTPS enforcement
# - SPA routing support (404/403 → /index.html)
# - All headers forwarded for proper routing
resource "aws_cloudfront_distribution" "frontend" {
  origin {
    domain_name = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id   = "s3-frontend"

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.frontend.cloudfront_access_identity_path
    }
  }

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Job Search Assistant Frontend SPA"
  default_root_object = "index.html"

  # Default Cache Behavior
  # Forward all headers for SPA routing to work correctly
  default_cache_behavior {
    allowed_methods = [
      "DELETE",
      "GET",
      "HEAD",
      "OPTIONS",
      "PATCH",
      "POST",
      "PUT"
    ]
    cached_methods = [
      "GET",
      "HEAD"
    ]

    target_origin_id = "s3-frontend"

    # Forward all headers - necessary for SPA routing decisions
    forwarded_values {
      query_string = true
      headers      = ["*"]

      cookies {
        forward = "all"
      }
    }

    # Redirect HTTP to HTTPS (no unencrypted traffic allowed)
    viewer_protocol_policy = "redirect-to-https"

    # Cache settings
    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  # SPA Routing Support
  # Map 403 Forbidden to /index.html with status 200
  # This allows CloudFront to serve index.html for deep routes
  custom_error_response {
    error_code            = 403
    response_page_path    = "/index.html"
    response_code         = 200
    error_caching_min_ttl = 300
  }

  # SPA Routing Support
  # Map 404 Not Found to /index.html with status 200
  # This handles requests to routes that don't have physical files in S3
  custom_error_response {
    error_code            = 404
    response_page_path    = "/index.html"
    response_code         = 200
    error_caching_min_ttl = 300
  }

  # CloudFront default certificate
  # Uses CloudFront's built-in certificate (*.cloudfront.net domain)
  # No ACM certificate, no custom domain, no Route53 configuration needed
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  # Geo-restriction
  # No geo-restrictions - application is available worldwide
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Price class
  # PriceClass_100 covers only North America, Europe, and Israel (lowest cost)
  # Can be changed to PriceClass_All for worldwide edge locations
  price_class = "PriceClass_100"

  tags = {
    Purpose = "Frontend SPA distribution"
  }
}

