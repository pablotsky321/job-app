# Terraform Import Instructions

This document provides step-by-step instructions for importing 15 existing AWS resources into Terraform state.

## Overview

The job-search-assistant infrastructure consists of 15 existing manually-created resources that must be imported into Terraform state, plus 20+ new resources that will be created by Terraform.

### Resources to Import (15 total)

| Resource Type | Count | Names |
|---|---|---|
| DynamoDB Tables | 7 | Empresas, Vacantes, UsuarioVacante, Entradas, Perfiles, Suscripciones, ScanJobs |
| SQS Queues | 4 | scan-dlq, scan-queue, scoring-dlq, scoring-queue |
| Cognito User Pool | 1 | job-search-assistant |
| Cognito App Client | 1 | job-search-frontend |
| Cognito Hosted UI Domain | 1 | job-search-assistant-mvp |
| Resource Group | 1 | job-search-assistant |

## Prerequisites

Before running the import script, ensure the following:

1. **Terraform is initialized**
   ```bash
   cd terraform
   terraform init
   ```

2. **terraform.tfvars is configured**
   - Copy `terraform.tfvars.example` to `terraform.tfvars`
   - Fill in all required values:
     - `aws_region = "us-east-1"`
     - `environment = "hackathon"`
     - `project_name = "job-search-assistant"`
     - `terraform_state_bucket = "<your-s3-bucket-name>"`
     - `cognito_user_pool_id = "us-east-1_abcdefghi"`
     - `ses_email = "your-email@example.com"`
     - Bedrock model IDs (if running production scanning)

3. **AWS credentials are configured**
   - `aws configure` or set `AWS_PROFILE` environment variable
   - Verify with: `aws sts get-caller-identity`

4. **All 15 resources exist in AWS**
   - Verify DynamoDB tables exist
   - Verify SQS queues exist
   - Verify Cognito User Pool and App Client exist
   - Verify Resource Group exists

5. **Manual S3 bucket creation** (if not already done)
   - The S3 bucket for Terraform state must be created manually (Terraform cannot manage its own initial backend)
   - Create in us-east-1 with versioning enabled:
   ```bash
   aws s3api create-bucket \
     --bucket job-search-terraform-state \
     --region us-east-1
   
   aws s3api put-bucket-versioning \
     --bucket job-search-terraform-state \
     --versioning-configuration Status=Enabled
   ```

## Step-by-Step Import Process

### Option A: Automated Import (Recommended)

Run the automated import script:

```bash
cd terraform
bash scripts/import_resources.sh
```

The script will:
1. Verify prerequisites
2. Fetch AWS Account ID
3. Automatically discover resource IDs from AWS
4. Run terraform import commands for all 15 resources
5. Display results and next steps

### Option B: Manual Import

If you prefer to run commands manually:

#### 1. Get your AWS Account ID

```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo $AWS_ACCOUNT_ID
```

#### 2. Get Cognito User Pool ID

```bash
aws cognito-idp list-user-pools --max-results 10 --region us-east-1 | grep -i "job-search"
# Example output: "job-search-assistant"
export COGNITO_USER_POOL_ID="us-east-1_abcdefghi"
```

#### 3. Get Cognito App Client ID

```bash
aws cognito-idp list-user-pool-clients \
  --user-pool-id $COGNITO_USER_POOL_ID \
  --region us-east-1 \
  --query 'UserPoolClients[*].[ClientId,ClientName]' \
  --output table

# Example output: job-search-frontend
export COGNITO_APP_CLIENT_ID="c7dt8acog5t0ifssh05eq0gc4"
```

#### 4. Get Resource Group ARN

```bash
aws resource-groups list-groups --region us-east-1 | grep "job-search-assistant"
# Example: "arn:aws:resource-groups:us-east-1:123456789012:group/job-search-assistant"
export RESOURCE_GROUP_ARN="arn:aws:resource-groups:us-east-1:123456789012:group/job-search-assistant"
```

#### 5. Import DynamoDB Tables

```bash
terraform import aws_dynamodb_table.Empresas Empresas
terraform import aws_dynamodb_table.Vacantes Vacantes
terraform import aws_dynamodb_table.UsuarioVacante UsuarioVacante
terraform import aws_dynamodb_table.Entradas Entradas
terraform import aws_dynamodb_table.Perfiles Perfiles
terraform import aws_dynamodb_table.Suscripciones Suscripciones
terraform import aws_dynamodb_table.ScanJobs ScanJobs
```

#### 6. Import SQS Queues

```bash
terraform import aws_sqs_queue.scan_dlq "https://sqs.us-east-1.amazonaws.com/${AWS_ACCOUNT_ID}/scan-dlq"
terraform import aws_sqs_queue.scan_queue "https://sqs.us-east-1.amazonaws.com/${AWS_ACCOUNT_ID}/scan-queue"
terraform import aws_sqs_queue.scoring_dlq "https://sqs.us-east-1.amazonaws.com/${AWS_ACCOUNT_ID}/scoring-dlq"
terraform import aws_sqs_queue.scoring_queue "https://sqs.us-east-1.amazonaws.com/${AWS_ACCOUNT_ID}/scoring-queue"
```

#### 7. Import Cognito User Pool

```bash
terraform import aws_cognito_user_pool.user_pool "$COGNITO_USER_POOL_ID"
```

#### 8. Import Cognito App Client

```bash
terraform import aws_cognito_user_pool_client.frontend "$COGNITO_USER_POOL_ID/$COGNITO_APP_CLIENT_ID"
```

#### 9. Import Cognito Hosted UI Domain

```bash
terraform import aws_cognito_user_pool_domain.frontend "job-search-assistant-mvp"
```

#### 10. Import Resource Group

```bash
terraform import aws_resourcegroups_group.job_search_assistant "$RESOURCE_GROUP_ARN"
```

## Verification Steps

After running the import commands:

### 1. Verify all imports succeeded

```bash
terraform state list
```

Expected output (15 resources):
```
aws_cognito_user_pool.user_pool
aws_cognito_user_pool_client.frontend
aws_cognito_user_pool_domain.frontend
aws_dynamodb_table.Empresas
aws_dynamodb_table.Entradas
aws_dynamodb_table.Perfiles
aws_dynamodb_table.ScanJobs
aws_dynamodb_table.Suscripciones
aws_dynamodb_table.UsuarioVacante
aws_dynamodb_table.Vacantes
aws_resourcegroups_group.job_search_assistant
aws_sqs_queue.scan_dlq
aws_sqs_queue.scan_queue
aws_sqs_queue.scoring_dlq
aws_sqs_queue.scoring_queue
```

### 2. Check for any import errors

```bash
terraform state list | wc -l
# Should output: 15
```

### 3. Verify no changes needed for imported resources

```bash
terraform plan
```

Expected: `No changes. Infrastructure is up-to-date.` (for imported resources)
The plan should show new resources to be created (20+), but imported resources should show 0 changes.

### 4. Verify specific resource attributes

```bash
# Check DynamoDB table configuration
terraform state show aws_dynamodb_table.Empresas

# Check SQS queue configuration
terraform state show aws_sqs_queue.scan_queue

# Check Cognito User Pool
terraform state show aws_cognito_user_pool.user_pool
```

## Troubleshooting

### Issue: "Error: resource already exists in state"

**Solution:** The resource is already imported. Run `terraform plan` to verify it's in sync.

### Issue: "Error: resource not found in AWS"

**Cause:** The resource doesn't exist in AWS or the resource ID is incorrect.

**Solution:**
1. Verify the resource exists: `aws <service> describe-<resources>`
2. Get the correct resource ID/ARN
3. Try importing again with the correct ID

### Issue: "Error: No identity found"

**Cause:** AWS credentials are not configured correctly.

**Solution:**
1. Run: `aws sts get-caller-identity`
2. Configure credentials: `aws configure`
3. Or set environment variable: `export AWS_PROFILE=<profile-name>`

### Issue: Cognito App Client import fails

**Common mistake:** Using just the App Client ID instead of the format `<user_pool_id>/<client_id>`

**Solution:**
```bash
terraform import aws_cognito_user_pool_client.frontend "$COGNITO_USER_POOL_ID/$COGNITO_APP_CLIENT_ID"
```

### Issue: Resource Group import fails

**Solution:** Verify the Resource Group exists:
```bash
aws resource-groups list-groups --region us-east-1 --query 'Groups[*].[Name,GroupArn]' --output table
```

## Manual Post-Deploy Steps

After `terraform apply` completes:

### 1. Update Cognito Callback URLs

The Cognito App Client's Callback URLs need to be updated to point to the real CloudFront domain:

1. Get the CloudFront domain from Terraform outputs:
   ```bash
   terraform output cloudfront_domain
   ```

2. Update the App Client in AWS Console:
   - Go to Cognito > User Pools > job-search-assistant > App Clients
   - Edit the `job-search-frontend` App Client
   - Update Callback URL(s):
     - Remove: `http://localhost:5173/callback`
     - Add: `https://<cloudfront-domain>/callback`

OR use AWS CLI:
```bash
CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain)
COGNITO_USER_POOL_ID=$(grep cognito_user_pool_id terraform.tfvars | grep -o '"[^"]*"' | head -1 | tr -d '"')
COGNITO_APP_CLIENT_ID=$(aws cognito-idp list-user-pool-clients --user-pool-id $COGNITO_USER_POOL_ID --region us-east-1 --query 'UserPoolClients[0].ClientId' --output text)

aws cognito-idp update-user-pool-client \
  --user-pool-id $COGNITO_USER_POOL_ID \
  --client-id $COGNITO_APP_CLIENT_ID \
  --callback-urls "https://${CLOUDFRONT_DOMAIN}/callback" \
  --region us-east-1
```

### 2. Verify SES Email Identities

Check that SES email identities are verified:
```bash
aws ses list-verified-email-addresses --region us-east-1
```

Expected: All email addresses should have VerificationStatus = "Success"

If not verified:
1. You'll receive verification emails
2. Click the verification link in each email
3. Or manually verify in AWS Console: SES > Email Addresses > Verify Email Address

### 3. Test API Gateway

Test the API Gateway endpoint with a valid JWT token:
```bash
curl -X GET "https://$(terraform output -raw api_gateway_domain)/health" \
  -H "Authorization: Bearer <valid-jwt-token>"
```

### 4. Test CloudFront Distribution

Wait ~10-15 minutes for CloudFront to fully deploy, then test:
```bash
curl -I https://$(terraform output -raw cloudfront_domain)
```

Expected: HTTP 200 (or 404 if frontend assets not uploaded yet)

## Rollback Steps

If something goes wrong, you can rollback imports:

```bash
# Remove a single imported resource from state (doesn't delete from AWS)
terraform state rm aws_dynamodb_table.Empresas

# Or completely refresh state
terraform state list | xargs -I {} terraform state rm {}
```

## Next Steps

After import is complete:

1. **Deploy new infrastructure**
   ```bash
   terraform plan
   terraform apply
   ```

2. **Upload frontend assets to S3**
   ```bash
   aws s3 cp ../frontend/dist/* s3://$(terraform output -raw frontend_bucket_name)/ --recursive
   ```

3. **Invalidate CloudFront cache**
   ```bash
   aws cloudfront create-invalidation \
     --distribution-id $(terraform output -raw cloudfront_id) \
     --paths "/*"
   ```

4. **Update application configuration**
   - Update frontend environment variables to point to new API Gateway URL
   - Update backend environment variables with new resource ARNs

## References

- [Terraform AWS Provider - Import](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS CLI Documentation](https://docs.aws.amazon.com/cli/latest/userguide/)
- [Design Document](../design.md)
- [Requirements Document](../requirements.md)
