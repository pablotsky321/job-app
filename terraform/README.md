# Terraform Infrastructure for Job-Search-Assistant

Terraform infrastructure code for deploying the job-search-assistant application on AWS. This infrastructure includes DynamoDB tables, SQS queues, Lambda functions, API Gateway, Cognito authentication, S3/CloudFront hosting, EventBridge scheduling, SES email service, and CloudWatch monitoring.

## Overview

The infrastructure is deployed in **us-east-1** and consists of:
- **7 DynamoDB tables** for data persistence (companies, vacancies, users, profiles, scan jobs, etc.)
- **4 SQS queues** with dead-letter queues for asynchronous processing
- **5 Lambda functions** for API, orchestration, scanning, scoring, and notifications
- **API Gateway** with Cognito authentication
- **CloudFront + S3** for frontend static asset hosting with SPA routing
- **EventBridge Scheduler** for automated job orchestration
- **SES** for email notifications
- **CloudWatch** for monitoring and alarms

The infrastructure imports 15 existing manually-created resources while provisioning 20+ additional resources. See "Import Existing Resources" section below.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React SPA)                        │
│                    Hosted on S3 + CloudFront                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTPS
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        API Gateway                                  │
│                   (Cognito Authorizer)                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
      ┌─────────┐   ┌──────────────┐   ┌──────────┐
      │   API   │   │ Orquestador  │   │ Workers  │
      │ Lambda  │   │   Lambda     │   │ (2x)     │
      │(10s)    │   │  (60s)       │   │(90s/30s) │
      └────┬────┘   └──────┬───────┘   └────┬─────┘
           │                │               │
           └────────────────┼───────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
    ┌─────────┐         ┌────────┐         ┌──────────┐
    │  Scan   │         │Scoring │         │DynamoDB  │
    │  Queue  │         │ Queue  │         │ Tables   │
    │(540s VT)│         │(180s VT)│         │ (7x)    │
    └─────────┘         └────────┘         └──────────┘
        │ DLQ               │ DLQ
        ▼                   ▼
    ┌─────────┐         ┌────────┐
    │Scan DLQ │         │Score   │
    │         │         │DLQ     │
    └─────────┘         └────────┘
        │
        └──────────────────┬──────────────────┐
                           ▼
                      ┌──────────┐
                      │Notificador│
                      │ Lambda   │
                      └──────┬───┘
                             │
                             ▼
                          ┌─────┐
                          │ SES │
                          │(Email)
                          └─────┘

Cognito ← Identity & Auth
CloudWatch ← Metrics, Logs, Alarms
EventBridge Scheduler ← Triggers orquestador every 8/12/18 UTC
```

## Prerequisites

### Before Running Terraform

1. **Create S3 bucket for Terraform state** (cannot be automated)
   ```bash
   # Create bucket
   aws s3api create-bucket \
     --bucket my-terraform-state-bucket \
     --region us-east-1

   # Enable versioning
   aws s3api put-bucket-versioning \
     --bucket my-terraform-state-bucket \
     --versioning-configuration Status=Enabled

   # Block public access
   aws s3api put-public-access-block \
     --bucket my-terraform-state-bucket \
     --public-access-block-configuration \
     "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
   ```

2. **Verify existing AWS resources**
   - Cognito User Pool: `job-search-assistant` (us-east-1)
   - 7 DynamoDB tables: Empresas, Vacantes, UsuarioVacante, Entradas, Perfiles, Suscripciones, ScanJobs
   - 4 SQS queues: scan-queue, scan-dlq, scoring-queue, scoring-dlq
   - Resource Group: `job-search-assistant`

3. **Prepare Lambda function code**
   - Create S3 bucket for Lambda code
   - Upload Lambda function zip files to: `s3://lambda-code-bucket/lambda-code/{function_name}/code.zip`
   - Functions: api, orquestador, scan-worker, scoring-worker, notificador

4. **Prepare Bedrock model IDs**
   - List available models: `aws bedrock list-foundation-models --region us-east-1`
   - Get cross-region inference profile IDs (must have `us.` prefix in us-east-1)
   - Example: `us.anthropic.claude-3-5-haiku-20241022-v1:0`

5. **AWS CLI configuration**
   - Configure AWS credentials: `aws configure`
   - Ensure credentials have permissions for Terraform operations
   - Or use IAM role with GitHub Actions OIDC (see CI/CD section)

### Software Requirements

- Terraform >= 1.5.0
- AWS CLI >= 2.0
- AWS account with appropriate permissions
- Bash shell (for import script)

## Quick Start

### 1. Initialize Terraform

```bash
cd terraform

# Copy example variables file
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values
nano terraform.tfvars

# Initialize Terraform (downloads AWS provider, sets up backend)
terraform init
```

### 2. Review Configuration

```bash
# Format check
terraform fmt -check

# Validate syntax
terraform validate

# Review planned changes
terraform plan
```

### 3. Apply Terraform

```bash
# Apply infrastructure changes
terraform apply

# Review and confirm with 'yes'
```

### 4. Import Existing Resources

```bash
# Run import script to import 15 existing resources
bash scripts/import_resources.sh

# Verify import success
terraform state list
terraform plan  # Should show 0 changes
```

### 5. Post-Deployment Steps

```bash
# Get outputs
terraform output

# Get CloudFront domain
terraform output cloudfront_domain

# Get Cognito Hosted UI domain
terraform output cognito_hosted_ui_domain

# Manually update Cognito App Client callback URLs to point to real CloudFront domain
```

## Directory Structure

```
terraform/
├── README.md                    # This file
├── terraform.tf               # Terraform version constraints
├── providers.tf               # AWS provider configuration
├── backend.tf                 # S3 backend for state management
├── variables.tf               # All input variables
├── terraform.tfvars           # Actual values (gitignored)
├── terraform.tfvars.example   # Template for variables
├── outputs.tf                 # Terraform outputs
├── main.tf                    # Root module, calls submodules
│
├── modules/                   # Terraform submodules (one per AWS service)
│   ├── iam/
│   │   └── main.tf           # 5 Lambda IAM roles + EventBridge role + GitHub Actions OIDC
│   ├── dynamodb/
│   │   └── main.tf           # 7 DynamoDB tables
│   ├── sqs/
│   │   └── main.tf           # 4 SQS queues + DLQs
│   ├── lambda/
│   │   └── main.tf           # 5 Lambda functions
│   ├── api-gateway/
│   │   └── main.tf           # REST API with Cognito authorizer
│   ├── cognito/
│   │   ├── main.tf           # Cognito User Pool (import only)
│   │   └── outputs.tf        # Cognito outputs
│   ├── s3-cloudfront/
│   │   └── main.tf           # S3 + CloudFront distribution
│   ├── eventbridge/
│   │   └── main.tf           # EventBridge Scheduler
│   ├── ses/
│   │   └── main.tf           # SES email configuration
│   └── cloudwatch/
│       └── main.tf           # CloudWatch logs and alarms
│
└── scripts/
    └── import_resources.sh    # Import commands for 15 existing resources
```

## Module Documentation

### IAM Module (`modules/iam/main.tf`)

Creates minimal-privilege IAM roles for each Lambda function plus EventBridge and GitHub Actions:

- **api-role**: API Gateway, DynamoDB (read/write), Bedrock, SQS
- **orquestador-role**: DynamoDB (read/write), SQS (scan queue)
- **scan-worker-role**: DynamoDB (read/write), SQS (scan + scoring), Bedrock
- **scoring-worker-role**: DynamoDB (read/write), SQS (scoring), Bedrock
- **notificador-role**: SES (send email)
- **eventbridge-scheduler-role**: Lambda (invoke orquestador)
- **github-actions-role**: OIDC provider + role for CI/CD

Each role follows **principle of least privilege** — permissions are scoped to specific resources.

### DynamoDB Module (`modules/dynamodb/main.tf`)

Creates 7 DynamoDB tables with on-demand billing:

| Table | PK | SK | GSI | TTL | Purpose |
|-------|----|----|-----|-----|---------|
| Empresas | companyId (S) | — | — | — | Company metadata |
| Vacantes | companyId (S) | vacancyId (S) | — | ttl | Job vacancies |
| UsuarioVacante | userId (S) | sk (S) | — | — | User-vacancy relationships |
| Entradas | pk (S) | entryId (S) | — | — | Interview question bank |
| Perfiles | userId (S) | — | — | — | Parsed user CVs |
| Suscripciones | userId (S) | companyId (S) | porEmpresa | — | User subscriptions |
| ScanJobs | jobId (S) | — | — | ttl | Scan job metadata |

**Lifecycle Protection**: `prevent_destroy = true` on all tables (including Entradas and Perfiles) — no principled reason to protect some tables and not others.

### SQS Module (`modules/sqs/main.tf`)

Creates 4 SQS queues with dead-letter queues (DLQs):

| Queue | Visibility Timeout | maxReceiveCount | DLQ |
|-------|--------------------|-----------------|-----|
| scan-queue | 540s (6×90s) | 3 | scan-dlq |
| scan-dlq | — | — | — |
| scoring-queue | 180s (6×30s) | 3 | scoring-dlq |
| scoring-dlq | — | — | — |

**Visibility Timeout Formula**: 6 × Lambda timeout ensures messages aren't re-delivered while Lambda is still processing. Values sourced from `backend-scan-y-scoring/design.md`.

### Lambda Module (`modules/lambda/main.tf`)

Creates 5 Lambda functions:

| Function | Runtime | Memory | Timeout | Reserved Concurrency | Trigger |
|----------|---------|--------|---------|----------------------|---------|
| api | Python 3.12 | 512MB | 10s | — | API Gateway |
| orquestador | Python 3.12 | 512MB | 60s | — | EventBridge Scheduler |
| scan-worker | Python 3.12 | 1024MB | 90s | 5 | SQS (scan-queue) |
| scoring-worker | Python 3.12 | 1024MB | 30s | 3 | SQS (scoring-queue) |
| notificador | Python 3.12 | 512MB | 30s | — | SQS or Lambda async |

**Environment Variables**: Each function receives table names, queue URLs, and Bedrock model IDs from Terraform variables (never hardcoded).

**Concurrency Reservation**: Required to prevent quota exhaustion on Bedrock tokens-per-minute limits.

### API Gateway Module (`modules/api-gateway/main.tf`)

REST API with Cognito authentication:

- Root resource + proxy path (`{proxy+}`)
- AWS_PROXY integration to `api` Lambda
- COGNITO authorizer pointing to existing User Pool
- CORS configuration
- CloudWatch metrics and logging

### Cognito Module (`modules/cognito/main.tf`)

**Import-only** — existing Cognito resources are imported, not created:

- **User Pool**: `job-search-assistant` (us-east-1)
- **App Client**: `job-search-frontend` (PKCE-only OAuth, no client secret)
- **Hosted UI Domain**: `job-search-assistant-mvp`

**Callback URLs** (must be updated post-deploy to point to real CloudFront domain):
- Login: `https://{cloudfront-domain}/callback`
- Logout: `https://{cloudfront-domain}/logout`

### S3 + CloudFront Module (`modules/s3-cloudfront/main.tf`)

Static website hosting with SPA routing:

- **S3 bucket**: Versioned, public access blocked, private
- **CloudFront distribution**: Default certificate (`*.cloudfront.net`), no custom domain
- **SPA routing**: 403/404 errors → `/index.html` (200 OK)
- **Viewer protocol**: Redirect HTTP → HTTPS
- **Cache behavior**: Forwards all headers for SPA routing

### EventBridge Scheduler Module (`modules/eventbridge/main.tf`)

Triggers `orquestador` Lambda on schedule:

- **Schedule expression** (default): `cron(0 8,12,18 * * ? *)` (8 AM, 12 PM, 6 PM UTC daily)
- **Configurable** via `orchestration_schedule_expression` variable
- Uses EventBridge Scheduler IAM role to invoke Lambda

### SES Module (`modules/ses/main.tf`)

Email service configuration:

- **Email identities**: Team emails (manually verified)
- **Sandbox mode**: 200 emails/day, 1 msg/sec (default)
- **Production mode**: Request via AWS Support (approval ~24h)

### CloudWatch Module (`modules/cloudwatch/main.tf`)

Monitoring and alarms:

- **Log groups**: 7-day retention (default is never expire)
- **Lambda error alarm**: Triggers when error count > 0 in 5 minutes
- **Lambda duration alarm**: Triggers when p95 > threshold (default 50s)
- **Billing alarm**: Triggers when estimated charges > threshold

## Variables

All variables are defined in `variables.tf`. Key variables:

### Required Variables (must be set in terraform.tfvars)

- `terraform_state_bucket`: S3 bucket for Terraform state (must exist)
- `cognito_user_pool_id`: Cognito User Pool ID (must already exist)
- `ses_email`: Email address for SES (must be verified)
- `lambda_code_bucket`: S3 bucket with Lambda function code
- `bedrock_model_small`: Bedrock small model ID (cross-region inference profile with `us.` prefix)
- `bedrock_model_mid`: Bedrock mid model ID (cross-region inference profile with `us.` prefix)
- IAM role ARNs from iam module

### Optional Variables (have sensible defaults)

- `aws_region`: AWS region (default: `us-east-1`, must be `us-east-1`)
- `environment`: Environment name (default: `hackathon`)
- `project_name`: Project name (default: `job-search-assistant`)
- `scan_worker_timeout`: Scan timeout (default: `90`s)
- `scoring_worker_timeout`: Scoring timeout (default: `30`s)
- `cors_origins`: CORS allowed origins (default: `http://localhost:5173`)
- `billing_alarm_threshold`: Billing threshold (default: `$500`)
- `orchestration_schedule_expression`: Cron schedule (default: `cron(0 8,12,18 * * ? *)`)

### Sensitive Variables

The following variables should NOT be printed in logs:

- `terraform_state_bucket`
- `cognito_user_pool_id`
- `ses_email`
- `lambda_code_bucket`
- `bedrock_model_small`
- `bedrock_model_mid`

## Outputs

Key outputs after `terraform apply`:

```bash
terraform output

# API and Lambda ARNs
terraform output -raw api_lambda_arn
terraform output -raw orquestador_lambda_arn
terraform output -raw scan_worker_lambda_arn
terraform output -raw scoring_worker_lambda_arn
terraform output -raw notificador_lambda_arn

# Queue URLs
terraform output -raw scan_queue_url
terraform output -raw scoring_queue_url

# Frontend hosting
terraform output -raw cloudfront_domain
terraform output -raw cloudfront_id

# Cognito
terraform output -raw cognito_hosted_ui_domain

# GitHub Actions CI/CD
terraform output -raw github_actions_role_arn
```

## Deployment Steps

### Step 1: Prepare Configuration

```bash
cd terraform

# Copy template
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
nano terraform.tfvars

# Set required values:
# - terraform_state_bucket: (your S3 bucket name)
# - cognito_user_pool_id: (output from manual Cognito setup)
# - ses_email: (your team email)
# - lambda_code_bucket: (S3 bucket with Lambda code)
# - bedrock_model_small: (e.g., us.anthropic.claude-3-5-haiku-...)
# - bedrock_model_mid: (e.g., us.anthropic.claude-3-5-sonnet-...)
```

### Step 2: Initialize Terraform

```bash
terraform init

# Output should show:
# - AWS provider downloaded
# - Backend configured (S3)
# - Modules downloaded
```

### Step 3: Validate and Format

```bash
terraform validate
# Should output: Success!

terraform fmt -check
# Should output with no errors

# If formatting issues:
terraform fmt -write
```

### Step 4: Review Plan

```bash
terraform plan -out=tfplan

# Review output:
# - Should show ~20+ resources to create
# - Should show 0 resources to destroy
# - Save plan to file for later apply
```

### Step 5: Apply Infrastructure

```bash
terraform apply tfplan

# Confirm with 'yes' when prompted
# Wait for all resources to create (5-10 minutes)
```

### Step 6: Import Existing Resources

```bash
# Run import script
bash scripts/import_resources.sh

# Verify imports
terraform state list

# Should show 15 imported resources
```

### Step 7: Verify No Changes

```bash
terraform plan

# Should output: No changes. Infrastructure is up-to-date.
```

### Step 8: Post-Deployment Configuration

```bash
# Get CloudFront domain
CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain)
echo "CloudFront Domain: $CLOUDFRONT_DOMAIN"

# Get Cognito domain
COGNITO_DOMAIN=$(terraform output -raw cognito_hosted_ui_domain)
echo "Cognito Domain: $COGNITO_DOMAIN"

# Manually update Cognito App Client in AWS Console:
# 1. Go to Cognito > User Pools > job-search-assistant > App Clients
# 2. Select "job-search-frontend"
# 3. Update Callback URLs: https://$CLOUDFRONT_DOMAIN/callback
# 4. Update Logout URLs: https://$CLOUDFRONT_DOMAIN/logout
# 5. Save changes
```

## Troubleshooting

### Issue: Terraform init fails with S3 backend error

**Cause**: S3 bucket for state doesn't exist or versioning not enabled.

**Solution**:
```bash
# Create bucket (if it doesn't exist)
aws s3api create-bucket \
  --bucket my-terraform-state-bucket \
  --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket my-terraform-state-bucket \
  --versioning-configuration Status=Enabled
```

### Issue: Lambda function code not found

**Cause**: Lambda code zip files not uploaded to S3.

**Solution**:
```bash
# Upload Lambda code to S3
aws s3 cp lambda-code.zip \
  s3://my-lambda-code-bucket/lambda-code/api/code.zip

# Do this for all 5 functions
```

### Issue: Bedrock model ID invalid or not found

**Cause**: Using bare model ID instead of `us.` prefixed cross-region inference profile ID.

**Solution**:
```bash
# List available models in us-east-1
aws bedrock list-foundation-models --region us-east-1

# Use models with us. prefix (e.g., us.anthropic.claude-3-5-...)
# Update terraform.tfvars with correct model IDs
terraform apply
```

### Issue: Import fails with "resource already exists in state"

**Cause**: Resource was already imported or created by Terraform.

**Solution**:
```bash
# Remove from state
terraform state rm 'aws_dynamodb_table.empresas'

# Re-import
terraform import aws_dynamodb_table.empresas arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/Empresas
```

### Issue: Cognito callback URLs causing login failure

**Cause**: Callback URLs not updated to real CloudFront domain.

**Solution**:
```bash
# Get CloudFront domain
terraform output -raw cloudfront_domain

# Manually update in AWS Cognito Console:
# 1. User Pools > job-search-assistant > App Clients > job-search-frontend
# 2. Update callback URLs
# 3. Save
```

## Cost Estimation

### Monthly Cost Estimate (Hackathon Environment)

Based on on-demand pricing in us-east-1:

| Service | Usage | Monthly Cost |
|---------|-------|---|
| DynamoDB | 1GB storage, on-demand | ~$5-10 |
| SQS | 1M messages/month | ~$0.40 |
| Lambda | 1M invocations, 512MB avg | ~$1-5 |
| Bedrock | 1M tokens via Bedrock API | ~$0.01-5 (varies by model) |
| S3 (frontend) | 100MB storage, 10k requests | ~$0.50 |
| CloudFront | 10GB/month transfer | ~$0.85 |
| API Gateway | 1M requests | ~$3.50 |
| SES (sandbox) | 100 emails/day | free |
| CloudWatch | Logs (7-day retention) | ~$1-2 |
| **Total** | — | **~$15-35/month** |

**Cost optimization tips**:
- Use Lambda reserved concurrency wisely (trade-off between throughput and cost)
- Set CloudWatch log retention to 7 days (this is configured)
- Use SQS batch operations where possible
- Monitor CloudWatch billing alarms closely

## Maintenance

### Regular Tasks

**Weekly**:
- Monitor CloudWatch alarms
- Check Lambda error logs
- Review SQS dead-letter queues

**Monthly**:
- Run `terraform plan` to detect drift
- Review billing in AWS Cost Explorer
- Verify backup SQS messages are being processed

**Quarterly**:
- Update Lambda function code
- Review and update Bedrock model IDs (models are frequently updated)
- Run `terraform validate` and `terraform fmt`
- Update documentation

### Updating Resources

To update any resource (e.g., Lambda timeout, memory, etc.):

```bash
# Update variables in terraform.tfvars
nano terraform.tfvars

# Review changes
terraform plan

# Apply
terraform apply
```

### Backing Up State

Terraform state is backed up to S3 with versioning enabled:

```bash
# List state versions
aws s3api list-object-versions \
  --bucket my-terraform-state-bucket \
  --prefix terraform.tfstate

# Recover previous state (if needed)
aws s3api get-object \
  --bucket my-terraform-state-bucket \
  --key terraform.tfstate \
  --version-id <VERSION_ID> \
  terraform.tfstate.backup
```

## Security Considerations

### 1. State File Protection

- **S3 versioning**: Enabled (can recover previous versions)
- **Encryption**: S3 default encryption (AES-256)
- **Public access**: Blocked
- **Backup**: Automatic via S3 versioning

### 2. Secrets Management

- **Never commit secrets**: `terraform.tfvars` is gitignored
- **Sensitive variables**: Marked with `sensitive = true` in code
- **IAM policies**: Minimal privilege (per-Lambda roles)
- **API credentials**: Never hardcoded

### 3. IAM Security

- **Least privilege**: Each Lambda has its own minimal role
- **Resource scoping**: Policies limited to specific DynamoDB tables, SQS queues
- **GitHub Actions OIDC**: No long-lived credentials

### 4. Network Security

- **No VPC**: Lambda runs in default VPC (for this MVP)
- **CORS**: Configured to specific origins
- **CloudFront HTTPS**: Enforced (redirect HTTP → HTTPS)
- **API authentication**: Cognito + JWT tokens

### 5. Data Protection

- **DynamoDB encryption**: Enabled at rest
- **SQS encryption**: Optional (not configured)
- **S3 versioning**: Enabled (recovery from accidental deletion)
- **prevent_destroy**: Lifecycle protection on all critical resources

## References

- **Design Document**: `terraform/design.md` (detailed design and architecture)
- **Backend Design**: `../../backend-scan-y-scoring/design.md` (Lambda specs, timeouts, concurrency)
- **AWS Documentation**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- **Terraform Best Practices**: https://www.terraform.io/docs/configuration/best-practices.html
- **Bedrock Model IDs**: https://docs.aws.amazon.com/bedrock/latest/userguide/getting-started-models.html
- **EventBridge Scheduler**: https://docs.aws.amazon.com/scheduler/latest/UserguideScheduleExpressions.html

## Support & Debugging

### Enable Debug Logging

```bash
# Enable Terraform debug mode
export TF_LOG=DEBUG

# Run terraform command
terraform plan

# Disable debug mode
unset TF_LOG
```

### View Resource Details

```bash
# Show current state of a resource
terraform state show 'aws_lambda_function.api'

# Show all resources
terraform state list

# Export state to JSON
terraform state pull > state.json
```

### Common Terraform Commands

```bash
# Format code
terraform fmt -recursive

# Validate syntax
terraform validate

# Plan changes (dry-run)
terraform plan

# Apply changes
terraform apply

# Apply with auto-approval (use with caution)
terraform apply -auto-approve

# Destroy all resources (use with caution!)
terraform destroy

# Target specific resource
terraform apply -target aws_lambda_function.api
```

## Contributing

When making changes to Terraform infrastructure:

1. **Update design.md** if architecture changes
2. **Run terraform validate** and **terraform fmt** before committing
3. **Use meaningful commit messages**: "Add SQS visibility timeout validation" vs. "fix terraform"
4. **Create PR** and have someone review the `terraform plan` output
5. **Document breaking changes** in commit message
6. **Update variables.tf** if adding new variables
7. **Update this README** if documentation changes

## License

This infrastructure code is part of the job-search-assistant project and follows the project's license terms.
