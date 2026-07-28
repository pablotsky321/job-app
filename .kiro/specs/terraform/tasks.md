# Tasks Document: Terraform Infrastructure Implementation

## Introduction

This task list breaks down the Terraform infrastructure implementation into discrete coding steps. The implementation will create infrastructure for the job-search-assistant application on AWS, including DynamoDB tables, SQS queues, Lambda functions, API Gateway, Cognito, S3/CloudFront, EventBridge Scheduler, SES, and CloudWatch monitoring.

The workflow follows a top-down approach:
1. Set up Terraform structure and configuration
2. Implement module code (DynamoDB, SQS, Lambda, etc.)
3. Create main.tf and wire everything together
4. Add variables, outputs, and documentation
5. Import existing resources and verify

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.6", "2.7", "2.9"] },
    { "id": 2, "tasks": ["2.4"] },
    { "id": 3, "tasks": ["2.5", "2.8", "2.10"] },
    { "id": 4, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "id": 5, "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": 6, "tasks": ["5.1", "5.2", "5.3"] },
    { "id": 7, "tasks": ["6.1", "6.2"] }
  ]
}
```

## Tasks

### Phase 1: Terraform Setup and Configuration

- [x] 1.1 Create Terraform directory structure
  - Create terraform/ directory at project root
  - Create terraform/modules/ subdirectory with subdirectories for: dynamodb, sqs, iam, lambda, api-gateway, cognito, s3-cloudfront, eventbridge, ses, cloudwatch
  - Create terraform/scripts/ directory for import script
  - _Requirements: 16_

- [x] 1.2 Create terraform.tf file (version constraints)
  - Set Terraform version >= 1.5.0
  - Configure AWS provider ~> 5.0
  - _Requirements: 21_

- [x] 1.3 Create backend.tf for S3 state management
  - Configure S3 backend with bucket and key from variables
  - Enable encryption for state file
  - Add comment about manual S3 bucket creation requirement (Requirement 1)
  - _Requirements: 1, 16, 17_

- [x] 1.4 Create providers.tf with region and tagging
  - Configure provider "aws" with region from variable (default us-east-1)
  - Set default_tags with Environment and Project from variables
  - _Requirements: 2, 16, 21_

### Phase 2: Module Implementation

- [x] 2.1 Implement IAM module (modules/iam/main.tf)
  - Create 5 IAM roles (api_role, orquestador_role, scan_worker_role, scoring_worker_role, notificador_role), each with its own least-privilege policy per design.md's differentiated permissions (DynamoDB tables actually touched, Bedrock, SQS, SES) — no shared generic role
  - Create the EventBridge Scheduler invoke role (eventbridge_scheduler_role) with lambda:InvokeFunction scoped to the orquestador Lambda ARN
  - Create the GitHub Actions OIDC provider (aws_iam_openid_connect_provider) and the github_actions role with trust policy scoped to the repo
  - _Requirements: 6, 13, 16_

- [x] 2.2 Implement DynamoDB module (modules/dynamodb/main.tf)
  - Create 7 DynamoDB tables: Empresas, Vacantes, UsuarioVacante, Entradas, Perfiles, Suscripciones, ScanJobs
  - Configure correct PK/SK/GSI/TTL for each table per design
  - Set billing_mode = PAY_PER_REQUEST for all tables
  - Add prevent_destroy lifecycle policy to ALL 7 tables (Empresas, Vacantes, UsuarioVacante, Entradas, Perfiles, Suscripciones, ScanJobs) — no principled reason to protect some tables and not others; Perfiles holds parsed CVs, Entradas holds the interview question bank (the project's innovation differentiator), Suscripciones and UsuarioVacante hold all user relationship state
  - _Requirements: 3, 16, 22_

- [x] 2.3 Implement SQS module (modules/sqs/main.tf)
  - Create 4 SQS queues: scan-dlq, scan-queue, scoring-dlq, scoring-queue
  - Configure visibility_timeout_seconds = 540 for scan-queue (6 × 90s timeout)
  - Configure visibility_timeout_seconds = 180 for scoring-queue (6 × 30s timeout)
  - Add redrive_policy with maxReceiveCount = 3 for both main queues
  - Export queue URLs as outputs for Lambda environment variables
  - Source: these visibility timeout values come directly from `backend-scan-y-scoring/design.md`'s "SQS Queue Configuration & Visibility Timeout Formulas" section (Lambda Timeout Scan_Worker=90s → Visibility Timeout=540s; Lambda Timeout Scoring_Worker=30s → Visibility Timeout=180s) — not assumptions made by this spec.
  - _Requirements: 4, 16_

- [x] 2.4 Implement Lambda module (modules/lambda/main.tf)
  - Create 5 Lambda functions: api, orquestador, scan-worker, scoring-worker, notificador
  - Configure correct runtime (python3.12), handler, and role for each (role ARNs consumed as input variables from the IAM module)
  - Set timeouts: api=10s, orquestador=60s, scan-worker=90s, scoring-worker=30s, notificador=30s
  - Set memory: api=512MB, orquestador=512MB, scan-worker=1024MB, scoring-worker=1024MB, notificador=512MB
  - Add reserved_concurrent_executions: scan-worker=5, scoring-worker=3
  - Configure environment variables from backend-scan-y-scoring design (BEDROCK_MODEL_SMALL, BEDROCK_MODEL_MID, DynamoDB tables, SQS queues, etc.)
  - Use data.archive_file for .zip packaging with source_code_hash for redeployment triggers
  - Source: scan-worker=90s and scoring-worker=30s timeouts come directly from `backend-scan-y-scoring/design.md`'s "SQS Queue Configuration & Visibility Timeout Formulas" section, not assumptions made by this spec.
  - _Requirements: 5, 15, 16_

- [x] 2.5 Implement API Gateway module (modules/api-gateway/main.tf)
  - Create REST API with root resource and {proxy+} path
  - Configure AWS_PROXY integration to api Lambda function
  - Create COGNITO authorizer pointing to Cognito User Pool ARN from variable
  - Create API Gateway stage (prod) and method settings for metrics/logging
  - _Requirements: 7, 16_

- [x] 2.6 Implement Cognito module (modules/cognito/main.tf) — import existing App Client and Hosted UI Domain
  - Import the existing Cognito User Pool using var.cognito_user_pool_id (already covered)
  - Import the EXISTING Cognito App Client (`job-search-frontend`, ID `c7dt8acog5t0ifssh05eq0gc4`) — do NOT create a new client. Match its real attributes exactly: generate_secret=false, allowed_oauth_flows=["code"] only (no "implicit"), explicit_auth_flows=["ALLOW_ADMIN_USER_PASSWORD_AUTH","ALLOW_USER_SRP_AUTH","ALLOW_REFRESH_TOKEN_AUTH"], callback_urls=["http://localhost:5173/callback"] and logout_urls=["http://localhost:5173/logout"] as SEPARATE attributes
  - Match refresh_token_validity=60 (days) — CONFIRMED via `aws cognito-idp describe-user-pool-client` on 2026-07-27. Note: infraestructura-desplegada.md's creation-command record said 30, but the live resource has since changed to 60; the live AWS value takes precedence over the static creation log.
  - Match supported_identity_providers=["COGNITO"] — CONFIRMED via the same describe-user-pool-client call, matches the original creation command.
  - Omit `prevent_user_existence_errors` from the resource block entirely — CONFIRMED via describe-user-pool-client that the live value is `null` (never configured). Do not set it to "ENABLED" or "LEGACY"; omitting the argument matches the null state and avoids Terraform attempting to set it on apply.
  - Add and import the Hosted UI Domain resource (`job-search-assistant-mvp`) — this resource is currently missing from any module
  - Export the Hosted UI domain URL as a Terraform output (`modules/cognito/outputs.tf`) for frontend login-URL construction
  - Add prevent_destroy lifecycle policy to the User Pool
  - _Requirements: 8, 16, 22_

- [x] 2.7 Implement S3 + CloudFront module (modules/s3-cloudfront/main.tf)
  - Create S3 bucket for frontend with versioning and public access blocked
  - Create CloudFront distribution with S3 origin, using the CloudFront default certificate (`cloudfront_default_certificate = true`) — no ACM certificate, no custom domain
  - Configure custom error responses for SPA routing (403/404 → /index.html with 200)
  - Set viewer_protocol_policy = "redirect-to-https"
  - Configure default_cache_behavior to forward all headers for SPA routing
  - _Requirements: 9, 16_

- [x] 2.8 Implement EventBridge Scheduler module (modules/eventbridge/main.tf)
  - Create scheduler that triggers orquestador Lambda, consuming the eventbridge_scheduler_role ARN as an input variable from the IAM module (do not declare the role here)
  - Configure schedule_expression from variable (default: cron(0 8,12,18 * * ? *))
  - _Requirements: 10, 16_

- [x] 2.9 Implement SES module (modules/ses/main.tf)
  - Create SES email identities for team emails from variable list
  - Add documentation comments about sandbox mode (200 emails/day, 1 msg/sec)
  - Add documentation about manual verification requirement
  - _Requirements: 11, 16_

- [x] 2.10 Implement CloudWatch module (modules/cloudwatch/main.tf)
  - Create CloudWatch log groups for all 5 Lambda functions
  - Set retention_in_days = 7 for each log group (Requirement 12)
  - Create billing alarm triggered when estimated charges > threshold
  - Create Lambda error alarm (threshold > 0 in 5 minutes)
  - Create Lambda duration alarm (threshold configurable, default p95 > 50s)
  - _Requirements: 12, 16_

### Phase 3: Main Terraform Configuration

- [x] 3.1 Create variables.tf with all required variables
  - Define all 12+ variables from requirements (aws_region, environment, project_name, terraform_state_bucket, cognito_user_pool_id, etc.)
  - Mark sensitive variables with sensitive = true
  - Mark required variables with required = true where appropriate
  - _Requirements: 15, 16, 21_

- [x] 3.2 Create terraform.tfvars.example
  - Create template with placeholder values for all variables
  - Document which variables require manual setup (terraform_state_bucket, cognito_user_pool_id, ses_email)
  - Add inline comments next to `bedrock_model_small` and `bedrock_model_mid` documenting the `us.`-prefix requirement for cross-region inference profiles in us-east-1 (e.g. `us.anthropic.claude-...`, not the bare base model ID) — mark as placeholder pending confirmation of the real model IDs from the AWS console
  - _Requirements: 15, 16, 21_

- [x] 3.3 Create outputs.tf with useful outputs
  - Export Lambda function ARNs for all 5 functions
  - Export SQS queue URLs for scan-queue and scoring-queue
  - Export CloudFront distribution domain and ID
  - Export GitHub Actions role ARN for CI/CD
  - Export S3 bucket name for frontend
  - Export `cognito_hosted_ui_domain` (built from `module.cognito.hosted_ui_domain` + region, per design.md's Cognito module outputs) — required by the frontend to construct the login URL
  - Note: the Cognito module itself (task 2.6) must expose this as a module-level output (`modules/cognito/outputs.tf`) before the root `outputs.tf` can re-export it
  - _Requirements: 16, 21_

- [x] 3.4 Create main.tf to wire everything together
  - Call all submodules with appropriate variables
  - Declare the `aws_resourcegroups_group.job_search_assistant` resource block at root level (required before its import command can be documented in the import script, since `terraform import` needs an existing resource address to bind to)
  - Use depends_on where implicit dependencies are insufficient
  - Pass IAM module role ARNs to the Lambda and EventBridge modules
  - Pass Lambda function ARNs to SQS and API Gateway modules
  - Pass Cognito User Pool ARN to API Gateway module
  - _Requirements: 16, 19_

### Phase 4: Documentation

- [x] 4.1 Create README.md in terraform directory
  - Document directory structure
  - Explain setup instructions (Requirements 21)
  - List environment variables and their purposes
  - Document security considerations
  - Provide cost estimation and monitoring guidance
  - _Requirements: 21_

- [x] 4.2 Create scripts/import_resources.sh
  - Document import commands for 7 DynamoDB tables
  - Document import commands for 4 SQS queues
  - Document import command for 1 Cognito User Pool
  - Document import command for the Cognito App Client (`us-east-1_LreFyDA2b/c7dt8acog5t0ifssh05eq0gc4` format: `<user_pool_id>/<client_id>`)
  - Document import command for the Hosted UI Domain (`job-search-assistant-mvp`)
  - Document import command for the Resource Group (binds to the `aws_resourcegroups_group.job_search_assistant` address declared in main.tf per task 3.4)
  - Include steps for getting actual ARNs/IDs from AWS console
  - _Requirements: 14, 16, 21_

- [x] 4.3 Create INSTRUCTIONS.md for manual setup steps
  - Document S3 bucket creation requirement (Requirement 1)
  - Document SES email verification process (Requirement 11)
  - Document post-deploy step of updating Cognito Callback URLs to the real CloudFront domain
  - _Requirements: 2, 11, 18, 21_

- [x] 4.4 Update .gitignore if needed
  - Add terraform/terraform.tfvars to gitignore (Requirement 15)
  - Ensure backend state files are not committed
  - _Requirements: 15, 17_

### Phase 5: Import Existing Resources

- [x] 5.1 Create terraform.tfvars with actual values
  - Get terraform_state_bucket from existing S3 bucket or create new one
  - Get cognito_user_pool_id from existing Cognito User Pool (job-search-assistant)
  - Set ses_email to team email address
  - Set all other variables as appropriate (environment, aws_region, etc.)
  - _Requirements: 14, 15_

- [x] 5.2 Run terraform validate and terraform fmt
  - Run terraform init (with backend configuration)
  - Run terraform validate to ensure no syntax errors
  - Run terraform fmt -check or terraform fmt -write to ensure formatting
  - _Requirements: 20_

- [x] 5.3 Run terraform plan and review
  - Run terraform plan to see all changes
  - Verify 15 existing resources are imported (no planned changes for those)
  - Verify 20+ new resources are planned for creation
  - Review IAM policies for least privilege
  - _Requirements: 14, 20_

### Phase 6: Final Validation

- [x] 6.1 Test import status with terraform state list
  - Run terraform state list to verify all 15 resources are imported
  - Verify resource names match expected (aws_dynamodb_table.*, aws_sqs_queue.*, etc.)
  - _Requirements: 14, 20_

- [x] 6.2 Verify CloudFront distribution and Lambda functions
  - After terraform apply, verify CloudFront distribution is active
  - Test Lambda functions can be invoked (via test button or CLI)
  - Verify API Gateway routes work (test with curl or Postman)
  - _Requirements: 20, 22_

## Pre-Implementation Requirements

### Manual Setup Required Before `terraform apply`

1. **Create S3 bucket for Terraform state** (Requirement 1)
   - Create a new S3 bucket in us-east-1
   - Enable versioning on the bucket
   - Note: Terraform cannot manage its own initial backend - this must be done manually first

2. **Verify Cognito User Pool exists** (Requirement 8)
   - Confirm the User Pool "job-search-assistant" exists in us-east-1
   - Note the User Pool ID for terraform.tfvars
   - Note: Importing a new User Pool would lose existing configuration and users

3. **Verify SQS queues exist** (Requirement 4)
   - Confirm queues scan-dlq, scan-queue, scoring-dlq, scoring-queue exist
   - Note the queue URLs for documentation purposes (terraform will use ARNs)

4. **Verify DynamoDB tables exist** (Requirement 3)
   - Confirm all 7 tables exist: Empresas, Vacantes, UsuarioVacante, Entradas, Perfiles, Suscripciones, ScanJobs
   - Note the table ARNs for documentation purposes (terraform will use ARNs)

5. **Verify Resource Group exists** (Requirement 14)
   - Confirm the Resource Group "job-search-assistant" exists
   - Note the ARN for documentation purposes

6. **Request SES production access** (Requirement 11)
   - Submit SES production access request (approx 24h approval)
   - Or use sandbox mode and manually verify email addresses
   - Note: Sandbox mode limits sending to 200 emails/day, 1 msg/sec

## Post-Implementation Steps

After running `terraform apply`, perform these verification steps:

1. **Verify import status**
   - Run `terraform state list` to verify all 15 resources are imported
   - Check for any resources showing as "created" instead of "imported"

2. **Run terraform plan**
   - After import, run `terraform plan` to ensure no unexpected changes
   - All imported resources should show 0 changes

3. **Verify CloudFront distribution**
   - Check AWS Console to confirm CloudFront distribution status is "Deployed"
   - Wait ~10-15 minutes for full deployment

4. **Verify Lambda functions**
   - Test each Lambda function using AWS Console "Test" button
   - Verify environment variables are set correctly
   - Check CloudWatch Logs for any errors

5. **Verify API Gateway**
   - Test API Gateway routes using curl or Postman
   - Verify Cognito authentication works
   - Test with a valid JWT token

## Important Constraints

The following constraints MUST be followed (violations are bugs, not preferences):

1. **Lambda Runtime**: Python 3.12 only (no Docker/ECR, no other runtimes) - Requirement 5
2. **Lambda Packaging**: .zip format only - Requirement 5
3. **SQS Visibility Timeout**: Must be exactly 6 × Lambda timeout
   - scan-queue: 540 seconds (6 × 90s)
   - scoring-queue: 180 seconds (6 × 30s) - Requirement 4
4. **DynamoDB Billing**: PAY_PER_REQUEST (on-demand) only - Requirement 3
5. **prevent_destroy**: Must be true for ALL 7 DynamoDB tables (Empresas, Vacantes, UsuarioVacante, Entradas, Perfiles, Suscripciones, ScanJobs) and the Cognito User Pool - Requirement 22
6. **CloudWatch Log Retention**: 7 days for all Lambda log groups - Requirement 12
7. **CloudFront Error Responses**: Map 403 and 404 to /index.html with status 200 for SPA routing - Requirement 9
8. **Bedrock Model IDs**: Never hardcoded in environment variables - always read from variables defined in variables.tf - Requirement 5
9. **IAM Roles**: One role per Lambda, no shared roles - Requirement 6
10. **S3 Backend**: State must be stored in S3 with versioning enabled - Requirement 1
11. **No Hardcoded Secrets**: All sensitive values (Account IDs, ARNs, Cognito IDs) must be read from variables - Requirement 17
12. **Region**: All resources must be in us-east-1 - Requirement 2

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP (none in this infrastructure spec)
- All tasks reference specific requirements for traceability
- Checkpoints are built into each phase (validate, fmt, plan, apply)
- Property tests are not applicable for infrastructure code (Terraform validates structure internally)
- Unit tests for infrastructure code would require tools likeTerratest or AWS SAM CLI, which are out of scope
- The design is based on the `backend-scan-y-scoring` specification for Lambda details
- GitHub Actions workflow YAML is out of scope - only the IAM role is provisioned (Requirement 18)
- Frontend and backend code are out of scope (Requirement 18)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.6", "2.7", "2.9"] },
    { "id": 2, "tasks": ["2.4"] },
    { "id": 3, "tasks": ["2.5", "2.8", "2.10"] },
    { "id": 4, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "id": 5, "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": 6, "tasks": ["5.1", "5.2", "5.3"] },
    { "id": 7, "tasks": ["6.1", "6.2"] }
  ]
}
```