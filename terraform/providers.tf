# AWS Provider Configuration
#
# This file configures the AWS provider with:
# - Region configuration from variable (default: us-east-1)
# - Default tags applied to all resources for consistent resource identification
#   and cost allocation (Environment and Project tags)
#
# The default_tags are automatically applied to all AWS resources created by
# Terraform, reducing repetition and ensuring consistency across the infrastructure.
#
# References:
# - Requirements: 2 (Region and Environment Configuration), 16 (Structure and Organization), 21 (Documentation)
# - Region constraint: All resources must be deployed in us-east-1 (cheaper, better Bedrock availability)

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = var.project_name
    }
  }
}
