variable "lambda_code_bucket" {
  description = "S3 bucket name where Lambda function .zip files are stored"
  type        = string
}

variable "terraform_state_bucket" {
  description = "S3 bucket name for Terraform state storage"
  type        = string
}
