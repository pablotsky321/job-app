# Job Search Assistant - Manual AWS Setup Instructions

## Overview

This document provides step-by-step instructions for all manual AWS setup that cannot be automated with Terraform. These steps must be completed **before** and **after** running `terraform apply`.

**Important**: Terraform can automate resource provisioning, but some AWS operations require manual intervention for compliance, verification, or security reasons.

---

## Pre-Deployment Manual Setup

### 1. Create S3 Backend Bucket for Terraform State

Terraform cannot manage its own backend bucket, so you must create this manually.

#### Prerequisites

- AWS credentials configured with `aws-cli` installed
- Sufficient permissions to create S3 buckets

#### Steps

1. **Create the S3 bucket** (replace `YOUR_ACCOUNT_ID` with your 12-digit AWS account ID):

   ```bash
   aws s3api create-bucket \
     --bucket job-search-terraform-state-YOUR_ACCOUNT_ID \
     --region us-east-1
   ```

2. **Enable versioning** on the bucket:

   ```bash
   aws s3api put-bucket-versioning \
     --bucket job-search-terraform-state-YOUR_ACCOUNT_ID \
     --versioning-configuration Status=Enabled
   ```

3. **Block all public access** (security best practice):

   ```bash
   aws s3api put-public-access-block \
     --bucket job-search-terraform-state-YOUR_ACCOUNT_ID \
     --public-access-block-configuration \
       BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
   ```

4. **Enable default encryption** (protects state file at rest):

   ```bash
   aws s3api put-bucket-encryption \
     --bucket job-search-terraform-state-YOUR_ACCOUNT_ID \
     --server-side-encryption-configuration '{
       "Rules": [{
         "ApplyServerSideEncryptionByDefault": {
           "SSEAlgorithm": "AES256"
         }
       }]
     }'
   ```

5. **Note the bucket name** for use in `terraform.tfvars`:

   ```
   terraform_state_bucket = "job-search-terraform-state-YOUR_ACCOUNT_ID"
   ```

---

### 2. Verify Existing Cognito User Pool

The existing Cognito User Pool contains user accounts and cannot be recreated without data loss.

#### Steps

1. **Get the User Pool ID** from AWS Console:

   ```bash
   aws cognito-idp list-user-pools --max-results 10 --query 'UserPools[?Name==`job-search-assistant`].Id' --output text
   ```

   Example output: `us-east-1_LreFyDA2b`

2. **Verify the User Pool exists**:

   ```bash
   aws cognito-idp describe-user-pool --user-pool-id us-east-1_LreFyDA2b
   ```

3. **Note the User Pool ID** for use in `terraform.tfvars`:

   ```
   cognito_user_pool_id = "us-east-1_LreFyDA2b"
   ```

---

### 3. Verify Existing SQS Queues

These queues already exist and will be imported by Terraform.

#### Steps

1. **List all SQS queues**:

   ```bash
   aws sqs list-queues --region us-east-1
   ```

2. **Verify all 4 queues exist**:

   - `scan-dlq`
   - `scan-queue`
   - `scoring-dlq`
   - `scoring-queue`

3. **Get queue URLs** (needed for verification):

   ```bash
   aws sqs get-queue-url --queue-name scan-queue --region us-east-1
   aws sqs get-queue-url --queue-name scan-dlq --region us-east-1
   aws sqs get-queue-url --queue-name scoring-queue --region us-east-1
   aws sqs get-queue-url --queue-name scoring-dlq --region us-east-1
   ```

**Note**: Do not modify queue settings manually — Terraform will import and manage them.

---

### 4. Verify Existing DynamoDB Tables

All 7 DynamoDB tables already exist and will be imported by Terraform.

#### Steps

1. **List all DynamoDB tables**:

   ```bash
   aws dynamodb list-tables --region us-east-1
   ```

2. **Verify all 7 tables exist**:

   - `Empresas`
   - `Vacantes`
   - `UsuarioVacante`
   - `Entradas`
   - `Perfiles`
   - `Suscripciones`
   - `ScanJobs`

3. **Verify table schemas** (example for Empresas):

   ```bash
   aws dynamodb describe-table --table-name Empresas --region us-east-1
   ```

**Warning**: Do NOT modify table schemas manually. Terraform will import these tables as-is. Any manual changes may conflict with Terraform's state.

---

### 5. Verify Existing Resource Group

The Resource Group tags resources for cost allocation and cleanup.

#### Steps

1. **Verify the Resource Group exists**:

   ```bash
   aws resource-groups list-groups --region us-east-1 --query 'GroupIdentifiers[?Name==`job-search-assistant`]'
   ```

2. **Get the Resource Group ARN** (you'll need it for import):

   ```bash
   aws resource-groups get-group --group-name job-search-assistant --region us-east-1 --query 'Group.GroupArn' --output text
   ```

   Example: `arn:aws:resource-groups:us-east-1:123456789012:group/job-search-assistant`

---

### 6. Prepare Bedrock Model IDs

Bedrock models are accessed via cross-region inference profiles in us-east-1.

#### Important Note

Several current Bedrock models are **only** invocable via cross-region inference profiles (prefixed with `us.`), not the bare base model ID. Using the bare model ID fails with a non-descriptive error.

#### Steps

1. **Check available Bedrock models** in us-east-1:

   ```bash
   aws bedrock --region us-east-1 list-foundation-models
   ```

2. **Identify the model IDs** (they will look like `us.anthropic.claude-...`):

   - For small model (Haiku): `us.anthropic.claude-3-5-haiku-20241022`
   - For mid-tier model (Sonnet): `us.anthropic.claude-3-5-sonnet-20241022`

3. **Note the model IDs** for use in `terraform.tfvars`:

   ```
   bedrock_model_small = "us.anthropic.claude-3-5-haiku-20241022"
   bedrock_model_mid   = "us.anthropic.claude-3-5-sonnet-20241022"
   ```

**Important**: Always use the `us.` prefixed inference profile ID, never the bare base model ID like `anthropic.claude-3-5-haiku-20241022`.

---

### 7. Set Up SES Email Identity (Sandbox or Production)

SES must be configured for email notifications. Choose one path:

#### Option A: Sandbox Mode (Quick Start, Limited)

**Use this if you need to get started quickly.** Sandbox mode is free but limited to 200 emails/day and 1 email/second.

1. **Find your AWS account ID**:

   ```bash
   aws sts get-caller-identity --query 'Account' --output text
   ```

2. **Verify SES is in Sandbox mode**:

   ```bash
   aws ses get-account-sending-enabled --region us-east-1
   ```

3. **Add email identities** in the AWS Console:

   - Navigate to: **SES → Verified identities → Create identity**
   - Select: **Email address**
   - Enter: Team email address (e.g., `team@example.com`)
   - Click: **Create identity**

4. **Verify each email**:

   - AWS sends a verification email to each address
   - Click the link in the email
   - Email is now verified

5. **Note your email address** for use in `terraform.tfvars`:

   ```
   ses_email = "team@example.com"
   ```

**Limitations of Sandbox Mode**:
- Max 200 emails/day (combined across all verified identities)
- Max 1 email/second
- Can only send to verified email addresses
- Not suitable for production

#### Option B: Request Production Access (Production Recommended)

**Use this for production deployments.** Request approval from AWS (approval typically takes 24 hours).

1. **Prepare your request**:

   - Business purpose: "Job search assistant application"
   - Website URL: Your application URL
   - Use case: Automated job matching notifications

2. **Submit request in AWS Console**:

   - Navigate to: **SES → Account dashboard → Edit account details**
   - Scroll to: **Production access request**
   - Fill form and submit

3. **Wait for approval** (typically 24 hours)

4. **Once approved**:

   - Email limit increases to 50 emails/second
   - Can send to any verified email address
   - No daily sending limit

---

## Post-Deployment Manual Steps

After running `terraform apply`, perform these manual steps to complete the deployment.

### 1. Update Cognito Callback URLs

The Cognito App Client callback URLs must point to your real CloudFront domain (not localhost).

#### Steps

1. **Get the CloudFront domain** from Terraform outputs:

   ```bash
   terraform output cloudfront_domain
   ```

   Example output: `d1234567890.cloudfront.net`

2. **Update Cognito Callback URLs**:

   ```bash
   aws cognito-idp update-user-pool-client \
     --user-pool-id us-east-1_LreFyDA2b \
     --client-id c7dt8acog5t0ifssh05eq0gc4 \
     --callback-urls \
       "http://localhost:5173/callback" \
       "https://d1234567890.cloudfront.net/callback" \
     --logout-urls \
       "http://localhost:5173/logout" \
       "https://d1234567890.cloudfront.net/logout" \
     --region us-east-1
   ```

   Replace `d1234567890.cloudfront.net` with your actual CloudFront domain.

3. **Verify the update**:

   ```bash
   aws cognito-idp describe-user-pool-client \
     --user-pool-id us-east-1_LreFyDA2b \
     --client-id c7dt8acog5t0ifssh05eq0gc4 \
     --region us-east-1 | grep -A 2 "CallbackURLs"
   ```

**Why this is manual**: The CloudFront domain is not known until after Terraform creates the distribution. A future automation could read it from Terraform outputs.

---

### 2. Deploy Lambda Function Code to S3

Lambda functions reference code in S3. Upload the packaged Lambda code.

#### Steps

1. **Get the Lambda code bucket** from Terraform outputs:

   ```bash
   terraform output frontend_bucket_name
   ```

2. **Build and package Lambda functions**:

   ```bash
   cd backend
   
   # Package each Lambda function as a .zip file
   zip api.zip -r . -x "tests/*" "__pycache__/*" "*.pyc"
   zip orquestador.zip -r . -x "tests/*" "__pycache__/*" "*.pyc"
   zip scan-worker.zip -r . -x "tests/*" "__pycache__/*" "*.pyc"
   zip scoring-worker.zip -r . -x "tests/*" "__pycache__/*" "*.pyc"
   zip notificador.zip -r . -x "tests/*" "__pycache__/*" "*.pyc"
   ```

3. **Upload to S3**:

   ```bash
   aws s3 cp api.zip s3://YOUR_LAMBDA_CODE_BUCKET/lambda-code/api.zip
   aws s3 cp orquestador.zip s3://YOUR_LAMBDA_CODE_BUCKET/lambda-code/orquestador.zip
   aws s3 cp scan-worker.zip s3://YOUR_LAMBDA_CODE_BUCKET/lambda-code/scan-worker.zip
   aws s3 cp scoring-worker.zip s3://YOUR_LAMBDA_CODE_BUCKET/lambda-code/scoring-worker.zip
   aws s3 cp notificador.zip s3://YOUR_LAMBDA_CODE_BUCKET/lambda-code/notificador.zip
   ```

4. **Update Lambda functions** to use the new code:

   ```bash
   # Get the S3 object version IDs
   aws s3api head-object --bucket YOUR_LAMBDA_CODE_BUCKET --key lambda-code/api.zip --query 'VersionId' --output text
   
   # Update each Lambda function
   aws lambda update-function-code \
     --function-name job-search-api \
     --s3-bucket YOUR_LAMBDA_CODE_BUCKET \
     --s3-key lambda-code/api.zip \
     --region us-east-1
   ```

**Note**: This can be automated in GitHub Actions CI/CD pipeline for continuous deployment.

---

### 3. Deploy Frontend Code to S3

The React SPA must be built and deployed to the frontend S3 bucket.

#### Steps

1. **Get the frontend bucket name** from Terraform outputs:

   ```bash
   terraform output frontend_bucket_name
   ```

2. **Build the frontend**:

   ```bash
   cd frontend
   npm install
   npm run build
   ```

3. **Upload built assets to S3**:

   ```bash
   aws s3 sync dist/ s3://YOUR_FRONTEND_BUCKET/ \
     --delete \
     --cache-control "max-age=3600" \
     --region us-east-1
   ```

4. **Invalidate CloudFront cache** to deploy immediately:

   ```bash
   aws cloudfront create-invalidation \
     --distribution-id $(terraform output cloudfront_id | tr -d '"') \
     --paths "/*" \
     --region us-east-1
   ```

**Wait time**: CloudFront invalidation typically takes 5-10 minutes to propagate globally.

---

### 4. Verify SES Email Identities Are Verified

Ensure all email identities in `terraform.tfvars` are verified.

#### Steps

1. **List verified identities**:

   ```bash
   aws ses list-verified-email-addresses --region us-east-1
   ```

2. **Verify each identity**:

   If any identity is missing:

   ```bash
   aws ses verify-email-identity \
     --email-address your-email@example.com \
     --region us-east-1
   ```

3. **Verify email**:

   - Check your inbox for verification email from AWS
   - Click the verification link
   - Email is now verified

---

### 5. Test Lambda Functions

Manually test each Lambda function to ensure environment variables and IAM permissions are correct.

#### Steps

1. **Test the API Lambda**:

   ```bash
   aws lambda invoke \
     --function-name job-search-api \
     --payload '{"httpMethod":"GET","path":"/health"}' \
     --region us-east-1 \
     response.json && cat response.json
   ```

2. **Test the orquestador Lambda**:

   ```bash
   aws lambda invoke \
     --function-name job-search-orquestador \
     --payload '{"source":"manual-test"}' \
     --region us-east-1 \
     response.json && cat response.json
   ```

3. **Check CloudWatch Logs** for any errors:

   ```bash
   aws logs tail /aws/lambda/job-search-api --follow --region us-east-1
   ```

---

## Account Quotas and Limits

AWS accounts have quotas on resources. Understand and monitor these limits to prevent service disruptions.

### 1. DynamoDB On-Demand Limits

On-demand billing is unlimited, but throughput is subject to account-level quotas.

#### Key Limits

| Metric | Limit | Impact |
|--------|-------|--------|
| Read capacity (per table) | 40,000 RCU/sec | Requests exceeding limit are throttled |
| Write capacity (per table) | 40,000 WCU/sec | Requests exceeding limit are throttled |
| Maximum item size | 400 KB | Larger items fail |
| Maximum batch size | 25 items (BatchWriteItem) | Larger batches must be split |
| Query result size | 1 MB max | Must paginate if larger |
| Scan result size | 1 MB max | Must paginate if larger |

#### Monitoring

```bash
# View account-level metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedWriteCapacityUnits \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum \
  --region us-east-1
```

#### If You Hit the Limit

- Request a quota increase: AWS Console → Service Quotas → DynamoDB
- Optimize queries to reduce capacity usage
- Batch operations to improve efficiency
- Distribute writes across multiple range keys (shard writes)

---

### 2. Lambda Concurrency Limits

Lambda has two concurrency types: **unreserved** (shared pool) and **reserved** (dedicated).

#### Key Limits

| Setting | Limit | Your Config |
|---------|-------|------------|
| Account unreserved concurrency | 1,000 | Shared by all functions |
| Reserved concurrency per function | Variable | Deducted from account pool |
| Burst capacity (temporary spike) | 3,000 | Short-lived burst handling |

#### Your Current Configuration

```
scan-worker: 5 reserved concurrent executions
scoring-worker: 3 reserved concurrent executions
Total reserved: 8 out of 1,000 available
```

#### Monitoring

```bash
# View Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Throttles \
  --dimensions Name=FunctionName,Value=job-search-scan-worker \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum \
  --region us-east-1
```

#### If You Hit the Limit

- Increase reserved concurrency: `aws lambda put-function-concurrency --function-name job-search-scan-worker --reserved-concurrent-executions 10`
- Request account concurrency increase: AWS Console → Service Quotas → Lambda
- Optimize function duration to reduce overall concurrency need

#### Why These Numbers Matter for Bedrock

**Critical**: Even though you only have 8 concurrent Lambdas reserved, Bedrock has token-per-minute (TPM) limits. Multiple Lambdas calling Bedrock in parallel can exhaust TPM quota before hitting Lambda concurrency limits.

---

### 3. Bedrock Token-Per-Minute (TPM) Limits

Bedrock limits requests based on tokens per minute, not concurrency.

#### Key Limits (us-east-1)

| Model | Input TPM | Output TPM |
|-------|-----------|-----------|
| Claude 3.5 Haiku | 200,000 | 150,000 |
| Claude 3.5 Sonnet | 200,000 | 150,000 |

#### Your Usage Pattern

- Scan-worker: ~500-2000 tokens per request, 5 concurrent
- Scoring-worker: ~1000-3000 tokens per request, 3 concurrent

#### Monitoring

```bash
# Check Bedrock metrics (if CloudWatch metrics are available)
aws cloudwatch list-metrics \
  --namespace AWS/Bedrock \
  --region us-east-1
```

#### Calculating Your TPM Usage

Example:

```
Scan-worker: 5 concurrent × 1000 tokens/sec × 60 = 300,000 tokens/min (EXCEEDS 200k limit!)
```

#### If You Hit the Limit

1. **Reduce request size**: Shorten prompts or use smaller models
2. **Request quota increase**: Contact AWS Support → Service Quotas → Bedrock
3. **Implement request batching**: Batch multiple items into single Bedrock call
4. **Use smaller model**: Switch from Sonnet to Haiku for some operations
5. **Reduce concurrency**: Lower `reserved_concurrent_executions` temporarily

---

### 4. SES Email Sending Limits

SES has different limits depending on sandbox vs. production mode.

#### Sandbox Mode Limits

| Metric | Limit |
|--------|-------|
| Daily sending quota | 200 emails/day |
| Max send rate | 1 email/second |
| Verified email addresses | Unlimited |
| Recipient verification | Must verify each recipient |

#### Production Mode Limits

| Metric | Limit |
|--------|-------|
| Daily sending quota | Unlimited (no daily limit) |
| Max send rate | 14 emails/second (default) |
| Verified email addresses | Unlimited |
| Recipient verification | No verification required |

#### Your Configuration

Default: **Sandbox mode** (200 emails/day, 1 email/second)

#### Monitoring

```bash
# View SES sending statistics
aws ses get-send-statistics --region us-east-1

# Check daily quota
aws ses get-account-sending-enabled --region us-east-1
```

#### If You Hit the Limit (Sandbox)

1. **Request production access**: Takes ~24 hours
2. **Add more verified email addresses**: Distribute sending across multiple addresses
3. **Implement rate limiting**: Space out email sending in your notificador Lambda

#### If You Hit the Limit (Production)

- Request increased sending rate: AWS Support → Service Quotas → SES

---

### 5. API Gateway Throttling

API Gateway throttles requests at the account and stage level.

#### Key Limits

| Metric | Limit |
|--------|-------|
| Account-level RPS | 10,000 requests/second |
| Stage-level RPS | 10,000 requests/second (default) |
| Burst capacity | 5,000 requests |

#### Your Configuration (from Terraform)

```hcl
throttling_burst_limit = 500
throttling_rate_limit  = 1000
```

This means: 1,000 requests/second sustained, 500 request burst capacity.

#### Monitoring

```bash
# View API Gateway metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Count \
  --dimensions Name=ApiName,Value=job-search-api Name=Stage,Value=prod \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 300 \
  --statistics Sum \
  --region us-east-1
```

---

### 6. CloudWatch Logs Retention

Logs are retained for 7 days by default per Terraform configuration.

#### Cost Impact

Each GB of ingested logs costs ~$0.50/month. With 7 days retention:

- 100 MB/day × 7 days = ~0.7 GB = ~$0.35/month
- 1 GB/day × 7 days = ~7 GB = ~$3.50/month

#### Adjusting Retention

If costs are high, reduce retention:

```bash
aws logs put-retention-policy \
  --log-group-name /aws/lambda/job-search-api \
  --retention-in-days 3 \
  --region us-east-1
```

---

## Troubleshooting Common Issues

### 1. Terraform Import Errors

#### Error: "Resource already exists in state"

**Cause**: Trying to import a resource that's already in Terraform state.

**Solution**:

```bash
# Check if resource is already imported
terraform state list | grep aws_dynamodb_table.empresas

# If it exists, skip the import
terraform import aws_dynamodb_table.empresas Empresas  # This will error
```

**Fix**: Remove from state first, then import:

```bash
terraform state rm aws_dynamodb_table.empresas
terraform import aws_dynamodb_table.empresas Empresas
```

---

#### Error: "Error importing resource: ResourceNotFoundException"

**Cause**: The resource doesn't exist in AWS, or the ARN/ID is incorrect.

**Solution**:

1. Verify the resource exists:

   ```bash
   # For DynamoDB
   aws dynamodb describe-table --table-name Empresas --region us-east-1
   
   # For SQS
   aws sqs get-queue-url --queue-name scan-queue --region us-east-1
   ```

2. Use the correct ARN or ID format:

   ```bash
   # DynamoDB tables can be imported by table name or ARN
   terraform import aws_dynamodb_table.empresas Empresas
   
   # SQS queues must use full URL
   terraform import aws_sqs_queue.scan_queue https://sqs.us-east-1.amazonaws.com/123456789012/scan-queue
   ```

---

### 2. Lambda Execution Failures

#### Error: "Unable to parse request body"

**Cause**: Lambda environment variables not set correctly, or handler expects different input format.

**Solution**:

1. Check environment variables:

   ```bash
   aws lambda get-function-configuration \
     --function-name job-search-api \
     --region us-east-1 | grep -A 20 "Environment"
   ```

2. Verify all required variables are present:

   - `BEDROCK_REGION`
   - `BEDROCK_MODEL_SMALL`
   - `BEDROCK_MODEL_MID`
   - `DYNAMODB_TABLE_*`
   - `SQS_QUEUE_*`

3. Check logs:

   ```bash
   aws logs tail /aws/lambda/job-search-api --follow --region us-east-1
   ```

---

#### Error: "AccessDenied when calling the InvokeModel operation"

**Cause**: Lambda IAM role doesn't have permission to invoke Bedrock.

**Solution**:

1. Verify IAM role has `bedrock:InvokeModel` permission:

   ```bash
   aws iam get-role-policy \
     --role-name job-search-scan-worker-role \
     --policy-name job-search-scan-worker-policy \
     --region us-east-1
   ```

2. Ensure Bedrock model ID is correct (must use `us.` prefix for inference profiles):

   ```bash
   echo $BEDROCK_MODEL_SMALL  # Should output: us.anthropic.claude-3-5-haiku-20241022
   ```

---

#### Error: "Database request failed: ResourceNotFoundException"

**Cause**: Lambda can't access DynamoDB table.

**Solution**:

1. Check Lambda IAM role has DynamoDB permissions:

   ```bash
   aws iam get-role-policy --role-name job-search-api-role --policy-name job-search-api-policy --region us-east-1
   ```

2. Verify DynamoDB table name in environment variable:

   ```bash
   aws lambda get-function-configuration \
     --function-name job-search-api \
     --region us-east-1 | grep DYNAMODB
   ```

3. Verify table exists:

   ```bash
   aws dynamodb describe-table --table-name Empresas --region us-east-1
   ```

---

### 3. SQS Visibility Timeout Problems

#### Error: "Message is being processed multiple times"

**Cause**: Visibility timeout is too short; message becomes visible before Lambda finishes processing.

**Formula**: Visibility Timeout = 6 × Lambda Timeout

**Check your configuration**:

```bash
# Get current visibility timeout
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/scan-queue \
  --attribute-names VisibilityTimeout \
  --region us-east-1
```

**Expected values**:

- `scan-queue`: 540 seconds (6 × 90s)
- `scoring-queue`: 180 seconds (6 × 30s)

**If incorrect**:

```bash
aws sqs set-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/scan-queue \
  --attributes VisibilityTimeout=540 \
  --region us-east-1
```

---

#### Error: "Message moved to Dead Letter Queue"

**Cause**: Message was received 3 times without successful deletion (DLQ `maxReceiveCount=3`).

**Resolution**:

1. **Check Dead Letter Queue**:

   ```bash
   aws sqs receive-message \
     --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/scan-dlq \
     --region us-east-1
   ```

2. **Examine message content** to understand why processing failed

3. **Fix the underlying issue** in your Lambda function

4. **Optional: Re-drive message** back to main queue:

   ```bash
   # Move message from DLQ back to main queue
   aws sqs send-message \
     --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/scan-queue \
     --message-body "$(message-content)" \
     --region us-east-1
   ```

---

### 4. Bedrock Model ID Format Issues

#### Error: "Could not validate the request with the given model 'anthropic.claude-3-5-haiku-20241022'"

**Cause**: Using bare model ID instead of `us.` prefixed cross-region inference profile.

**In us-east-1**, some Bedrock models must use the inference profile ID with `us.` prefix.

**Solution**:

1. **Verify model ID in environment variable**:

   ```bash
   aws lambda get-function-configuration --function-name job-search-scan-worker --region us-east-1 | grep BEDROCK
   ```

2. **Fix the model ID** to use `us.` prefix:

   ```
   BEDROCK_MODEL_SMALL = "us.anthropic.claude-3-5-haiku-20241022"
   BEDROCK_MODEL_MID = "us.anthropic.claude-3-5-sonnet-20241022"
   ```

3. **Update in terraform.tfvars**:

   ```hcl
   bedrock_model_small = "us.anthropic.claude-3-5-haiku-20241022"
   bedrock_model_mid   = "us.anthropic.claude-3-5-sonnet-20241022"
   ```

4. **Redeploy Lambda functions**:

   ```bash
   terraform apply -target=module.lambda
   ```

---

### 5. CloudFront 403/404 Errors

#### Error: "AccessDenied" from CloudFront when accessing S3 directly

**Cause**: Origin Access Identity (OAI) not configured correctly.

**Solution**:

1. Verify OAI exists:

   ```bash
   aws cloudfront list-cloud-front-origins-by-distribution-id \
     --distribution-id $(terraform output cloudfront_id | tr -d '"') \
     --region us-east-1
   ```

2. Verify S3 bucket policy includes CloudFront OAI:

   ```bash
   aws s3api get-bucket-policy --bucket YOUR_FRONTEND_BUCKET --region us-east-1
   ```

---

#### Error: "SPA routing not working; page not found after refresh"

**Cause**: CloudFront error responses for 403/404 not configured for SPA routing.

**Solution**:

Verify CloudFront custom error responses are set:

```bash
aws cloudfront get-distribution \
  --id $(terraform output cloudfront_id | tr -d '"') \
  --region us-east-1 | grep -A 10 "CustomErrorResponses"
```

Should show:

```
{
  "ErrorCode": 403,
  "ResponsePagePath": "/index.html",
  "ResponseCode": "200"
},
{
  "ErrorCode": 404,
  "ResponsePagePath": "/index.html",
  "ResponseCode": "200"
}
```

If not set correctly, update via Terraform:

```bash
terraform apply -target=module.s3_cloudfront
```

---

### 6. Cognito Authentication Issues

#### Error: "Invalid client id" or "Client does not exist"

**Cause**: App Client ID in Cognito callback URLs doesn't match the actual client.

**Solution**:

1. Get the correct App Client ID:

   ```bash
   aws cognito-idp list-user-pool-clients \
     --user-pool-id us-east-1_LreFyDA2b \
     --region us-east-1
   ```

2. Get the full client configuration:

   ```bash
   aws cognito-idp describe-user-pool-client \
     --user-pool-id us-east-1_LreFyDA2b \
     --client-id c7dt8acog5t0ifssh05eq0gc4 \
     --region us-east-1
   ```

3. Verify callback URLs match CloudFront domain:

   ```bash
   aws cognito-idp describe-user-pool-client \
     --user-pool-id us-east-1_LreFyDA2b \
     --client-id c7dt8acog5t0ifssh05eq0gc4 \
     --region us-east-1 | grep -A 2 "CallbackURLs"
   ```

---

#### Error: "Redirect URI mismatch" after Cognito login

**Cause**: Callback URL in Cognito doesn't match the frontend's redirect URL.

**Example mismatch**:

- Cognito config: `https://d1234567890.cloudfront.net/callback`
- Frontend redirect: `https://d1234567890.cloudfront.net/auth/callback`

**Solution**:

1. Update Cognito callback URLs to match frontend:

   ```bash
   aws cognito-idp update-user-pool-client \
     --user-pool-id us-east-1_LreFyDA2b \
     --client-id c7dt8acog5t0ifssh05eq0gc4 \
     --callback-urls "https://d1234567890.cloudfront.net/callback" \
     --region us-east-1
   ```

2. Verify in frontend code the redirect URL matches Cognito config

---

### 7. IAM Policy Issues

#### Error: "User: arn:aws:iam::123456789012:role/XXX is not authorized to perform: dynamodb:GetItem"

**Cause**: Lambda IAM role missing DynamoDB permissions.

**Solution**:

1. Check the IAM role policy:

   ```bash
   aws iam get-role-policy --role-name job-search-api-role --policy-name job-search-api-policy --region us-east-1
   ```

2. Verify the policy includes the required table:

   ```json
   {
     "Effect": "Allow",
     "Action": "dynamodb:GetItem",
     "Resource": "arn:aws:dynamodb:us-east-1:123456789012:table/Empresas"
   }
   ```

3. If missing, reapply Terraform:

   ```bash
   terraform apply -target=module.iam
   ```

---

## Quick Reference: Common Commands

```bash
# View all Lambda functions
aws lambda list-functions --region us-east-1

# Get Lambda logs (last 30 minutes)
aws logs tail /aws/lambda/job-search-api --follow --since 30m --region us-east-1

# View all SQS queues
aws sqs list-queues --region us-east-1

# View all DynamoDB tables
aws dynamodb list-tables --region us-east-1

# Check service quotas
aws service-quotas list-service-quotas --service-code lambda --region us-east-1

# View estimated AWS charges
aws ce get-cost-and-usage --time-period Start=2024-01-01,End=2024-01-31 --granularity MONTHLY --metrics "UnblendedCost" --group-by Type=DIMENSION,Key=SERVICE

# Invalidate CloudFront cache
aws cloudfront create-invalidation --distribution-id <ID> --paths "/*" --region us-east-1

# Test API Gateway
curl -H "Authorization: Bearer <TOKEN>" https://API_ID.execute-api.us-east-1.amazonaws.com/prod/health
```

---

## Support and Further Reading

- [AWS Terraform Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)
- [AWS Lambda Limits](https://docs.aws.amazon.com/lambda/latest/dg/limits.html)
- [AWS Bedrock Models](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html)
- [AWS SES Documentation](https://docs.aws.amazon.com/ses/latest/dg/Welcome.html)

---

## Document Maintenance

Last updated: 2024

If you encounter issues not covered here, please:

1. Check AWS CloudWatch Logs for error messages
2. Review the Terraform plan: `terraform plan`
3. Verify AWS service quotas: `aws service-quotas`
4. Contact AWS Support for infrastructure issues
