# Requirements Document: Terraform Infrastructure for Job-Search-Assistant

## Introduction

This document specifies the requirements for Terraform infrastructure to deploy the job-search-assistant application on AWS. The infrastructure includes infrastructure as code for all AWS resources needed to run the application, including DynamoDB tables, SQS queues, Lambda functions, API Gateway, Cognito, S3/CloudFront, EventBridge Scheduler, SES, and CloudWatch monitoring.

The infrastructure will be deployed in the `us-east-1` region and will import 15 existing manually created resources (7 DynamoDB tables, 4 SQS queues, 1 Cognito User Pool, 1 Cognito App Client, 1 Cognito Hosted UI Domain, and 1 Resource Group) while provisioning the remaining 20+ resources.

## Glossary

- **Terraform**: Infrastructure as Code tool for provisioning AWS resources
- **DynamoDB**: NoSQL database for storing companies, vacancies, users, subscriptions, and scan jobs
- **SQS**: Message queuing service for async processing (scan and scoring queues)
- **DLQ**: Dead Letter Queue for messages that failed processing after 3 retries
- **Lambda**: Serverless compute for running the API, workers, and orchestrator
- **API Gateway**: HTTP endpoint for API requests with Cognito authentication
- **Cognito**: Identity management for user authentication
- **S3**: Object storage for frontend static assets and Terraform state
- **CloudFront**: CDN for frontend static assets with SPA routing support
- **EventBridge Scheduler**: Scheduled trigger for the orquestador Lambda
- **SES**: Email service for sending notifications
- **IAM**: Identity and Access Management for resource permissions
- **CloudWatch**: Monitoring, logging, and billing alarms
- **OIDC**: OpenID Connect for GitHub Actions authentication to AWS
- **Backend-scan-y-scoring design**: Design document specifying Lambda functions (orquestador, scan-worker, scoring-worker) with their timeouts and concurrency settings
- **Visibility Timeout**: Time window during which a message is invisible to other consumers before being re-delivered

## Requirements

### Requirement 1: Backend State Management

**User Story:** As a developer, I want to store Terraform state in S3, so that multiple developers can collaborate and state is versioned and backed up.

#### Acceptance Criteria

1. WHEN Terraform is initialized, THE Backend SHALL use an S3 bucket for state storage with versioning enabled
2. WHEN an S3 bucket is specified in variables, THE Backend SHALL use that bucket for state storage
3. IF no bucket is specified in variables, THEN THE System SHALL provide clear instructions to create one manually
4. THE State File SHALL NOT be committed to the repository
5. WHERE S3 state is used, THE Versioning SHALL be enabled on the bucket
6. WHILE state is stored in S3, THE State File SHALL remain encrypted at rest (S3 default encryption)

### Requirement 2: Region and Environment Configuration

**User Story:** As a developer, I want to specify AWS region and environment, so that resources are deployed correctly.

#### Acceptance Criteria

1. WHEN Terraform is initialized, THE Region SHALL be configurable via variables
2. THE Default Region SHALL be `us-east-1` (N. Virginia)
3. WHEN environment is specified, ALL Resources SHALL include tags `Environment={environment}` and `Project=job-search-assistant`
4. WHERE environment is `hackathon`, THE Resources SHALL be marked as temporary

### Requirement 3: DynamoDB Tables

**User Story:** As a developer, I want DynamoDB tables for data persistence, so that the application can store companies, vacancies, users, and scan jobs.

#### Acceptance Criteria

1. WHEN Terraform is applied, THE Following 7 Tables SHALL be created with on-demand billing:
   1. `Empresas`: PK `companyId` (S), no SK, no GSI
   2. `Vacantes`: PK `companyId` (S), SK `vacancyId` (S), no GSI, TTL on `ttl` attribute
   3. `UsuarioVacante`: PK `userId` (S), SK `sk` (S), no GSI
   4. `Entradas`: PK `pk` (S), SK `entryId` (S), no GSI
   5. `Perfiles`: PK `userId` (S), no SK, no GSI
   6. `Suscripciones`: PK `userId` (S), SK `companyId` (S), GSI `porEmpresa` (PK `companyId` (S), SK `userId` (S))
   7. `ScanJobs`: PK `jobId` (S), TTL on `ttl` attribute, no GSI

2. WHILE all tables exist, THE `prevent_destroy = true` Lifecycle Policy SHALL be applied to each
3. WHEN tables are imported from manual creation, THE Import Commands SHALL use the actual table ARNs from the deployment
4. FOR ALL Tables, THE Billing Mode SHALL be `PAY_PER_REQUEST` (on-demand)

### Requirement 4: SQS Queues with DLQs

**User Story:** As a developer, I want SQS queues with dead letter queues, so that messages are retried and failed messages are captured.

#### Acceptance Criteria

1. WHEN Terraform is applied, THE Following 4 Queues SHALL be created:
   1. `scan-dlq`: Dead Letter Queue (no DLQ needed)
   2. `scan-queue`: Main queue with `maxReceiveCount=3`, `RedrivePolicy` → `scan-dlq`
   3. `scoring-dlq`: Dead Letter Queue (no DLQ needed)
   4. `scoring-queue`: Main queue with `maxReceiveCount=3`, `RedrivePolicy` → `scoring-dlq`

2. WHEN visibility timeout is configured, THE Visibility Timeout SHALL equal `6 × Lambda Timeout` (from backend-scan-y-scoring design)
3. WHEN `scan-queue` timeout is set, THE Visibility Timeout SHALL be `540 seconds` (6 × 90s timeout for scan-worker)
4. WHEN `scoring-queue` timeout is set, THE Visibility Timeout SHALL be `180 seconds` (6 × 30s timeout for scoring-worker)
5. IF queue URLs are needed elsewhere, THE Queue URLs SHALL be exported as outputs for use in Lambda environment variables

### Requirement 5: Lambda Functions

**User Story:** As a developer, I want Lambda functions for the API and workers, so that the application can handle requests and process messages.

#### Acceptance Criteria

1. WHEN Lambda functions are created, THE Following 5 Functions SHALL be created:
   1. `api`: FastAPI + Mangum, monolithic, API Gateway sync endpoint, 512MB memory, 10s timeout
   2. `orquestador`: EventBridge Scheduler trigger, no concurrency reservation
   3. `scan-worker`: Concurrency reserved = 5, 1024MB memory, 90s timeout
   4. `scoring-worker`: Concurrency reserved = 3, 1024MB memory, 30s timeout
   5. `notificador`: SES integration, no concurrency reservation

2. WHEN a Lambda function is packaged, THE Packaging SHALL be `.zip` format (PROHIBIT Docker/ECR)
3. WHILE packaging, THE Runtime SHALL be Python 3.12
4. WHEN environment variables are set, THE Bedrock Model IDs SHALL NOT be hardcoded, but read from environment variables (`BEDROCK_MODEL_SMALL`, `BEDROCK_MODEL_MID`)
5. FOR ALL Lambdas, THE IAM Role SHALL have minimal privileges (no shared generic role)
6. WHEN function code is referenced, THE S3 Bucket SHALL be configurable via variables
7. WHERE Lambda function code is updated, THE `source_code_hash` SHALL be used to trigger redeployment
8. WHEN logs are generated, THE CloudWatch Log Group SHALL have 7-day retention (default is never expire)

### Requirement 6: IAM Roles and Policies

**User Story:** As a developer, I want minimal-privilege IAM roles for each Lambda, so that security is maintained and permissions are auditable.

#### Acceptance Criteria

1. WHEN IAM roles are created, THE Following Roles SHALL be created (one per Lambda, no shared roles):
   1. `api-role`: Permissions from backend-scan-y-scoring design
   2. `orquestador-role`: Permissions from backend-scan-y-scoring design
   3. `scan-worker-role`: Permissions from backend-scan-y-scoring design
   4. `scoring-worker-role`: Permissions from backend-scan-y-scoring design
   5. `notificador-role`: SES permissions for sending emails

2. WHILE roles are created, THE Policies SHALL follow the principle of least privilege
3. WHEN Bedrock access is needed, THE Policy SHALL include `bedrock:InvokeModel` with specific model ARNs
4. WHEN DynamoDB access is needed, THE Policy SHALL include `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem`, `dynamodb:Query`, `dynamodb:Scan`
5. WHEN SQS access is needed, THE Policy SHALL include `sqs:SendMessage`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`
6. WHEN SES access is needed, THE Policy SHALL include `ses:SendEmail`, `ses:SendRawEmail`
7. WHERE CloudWatch logs are needed, THE Policy SHALL include `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`

### Requirement 7: API Gateway with Cognito Authorizer

**User Story:** As a developer, I want API Gateway with Cognito authentication, so that only authenticated users can access the API.

#### Acceptance Criteria

1. WHEN API Gateway is created, THE Resource SHALL be a REST API with a `/` resource
2. WHEN a route is defined, THE Integration SHALL be `AWS_PROXY` to the `api` Lambda function
3. WHEN authentication is configured, THE Authorizer SHALL be of type `COGNITO` pointing to the existing User Pool
4. WHERE the User Pool ARN is needed, THE Variable `COGNITO_USER_POOL_ID` SHALL be read from the `.env` file (not hardcoded)
5. WHEN routes are created, THE Following Routes SHALL be defined (not all in scope, but infrastructure must support):
   1. `POST /scans`: Trigger scan job
   2. `GET /scans/{jobId}`: Poll scan job status
   3. `GET /vacancies`: List user vacancies
   4. `GET /vacancies/{id}`: Get vacancy details
   5. `POST /vacancies/manual`: Create manual vacancy
   6. `GET /me/profile`: Get user profile
   7. `PUT /me/profile`: Update user profile
   8. `POST /scans/rescore`: Trigger rescore
   9. `GET /me/notificaciones`: Get user notifications

6. WHILE routes are created, THE Authorization Type SHALL be `COGNITO` for all routes
7. WHEN CORS is enabled, THE CORS Configuration SHALL allow origins from variables (CORS for localhost during development)

### Requirement 8: Cognito User Pool (Import Only)

**User Story:** As a developer, I want to import the existing Cognito User Pool, App Client, and Hosted UI Domain, so that I don't lose existing users and configuration.

#### Acceptance Criteria

1. WHEN the User Pool is imported, THE Import Command SHALL use the actual User Pool ID from the deployment
2. WHEN the App Client is imported, THE Import Command SHALL use the actual App Client ID from the deployment (the `job-search-frontend` App Client already exists in AWS and SHALL be imported, not created fresh)
3. WHEN the App Client is configured, THE Following Settings SHALL be set:
   - Client Name: `job-search-frontend`
   - Generate Secret: `false` (no client secret)
   - Allowed OAuth Flows: `authorization_code`
   - Allowed OAuth Scopes: `email`, `openid`, `profile`
   - Callback URLs: `http://localhost:5173/callback`
   - Logout URLs: `http://localhost:5173/logout`
   - Prevent User Existence Errors: `ENABLED`
   - Enable Token Revocation: `true`

4. WHILE the User Pool is imported, THE `prevent_destroy = true` Lifecycle Policy SHALL be applied
5. WHERE Hosted UI is used, THE Domain Prefix SHALL be `job-search-assistant-mvp` (the Hosted UI Domain already exists in AWS and SHALL be imported, not created fresh)
6. WHEN the Hosted UI Domain is imported, THE Resulting Domain URL SHALL be exported as a Terraform output for use by the frontend when building the login URL

### Requirement 9: S3 + CloudFront for Frontend

**User Story:** As a developer, I want S3 + CloudFront for frontend hosting, so that the React SPA is served efficiently.

#### Acceptance Criteria

1. WHEN an S3 bucket is created, THE Bucket SHALL be configured as a static website host
2. WHEN CloudFront distribution is created, THE Error Responses SHALL be:
   - HTTP Error Code: `403`
   - Response Page Path: `/index.html`
   - HTTP Response Code: `200`
   - HTTP Error Code: `404`
   - Response Page Path: `/index.html`
   - HTTP Response Code: `200`

3. WHILE error responses are configured, THE SPA Routing Support SHALL be enabled
4. WHEN origin is configured, THE Origin SHALL point to the S3 bucket
5. WHERE SSL is configured, THE CloudFront Distribution SHALL use the CloudFront default certificate (`*.cloudfront.net`, `cloudfront_default_certificate = true`), with no custom domain, no ACM certificate request, and no Route53 configuration
6. WHEN cache behavior is set, THE Default Cache Behavior SHALL forward all headers (for SPA routing)

### Requirement 10: EventBridge Scheduler

**User Story:** As a developer, I want EventBridge Scheduler to trigger the orquestador Lambda, so that scanning happens automatically.

#### Acceptance Criteria

1. WHEN a schedule is created, THE Schedule SHALL trigger the `orquestador` Lambda function
2. WHEN the schedule is configured, THE Schedule Expression SHALL be configurable via variable (default: cron(0 8,12,18 * * ? *)
3. WHILE schedule is active, THE Schedule SHALL be enabled by default
4. WHEN a schedule is created, THE Target SHALL be the `orquestador` Lambda function ARN
5. WHERE IAM role is needed, THE Execution Role SHALL have `lambda:InvokeFunction` permission

### Requirement 11: SES Email Configuration

**User Story:** As a developer, I want SES configured for sending emails, so that the application can notify users.

#### Acceptance Criteria

1. WHEN SES is configured, THE Email Identity Verification SHALL be set up for the team emails (5 addresses)
2. WHILE verification is pending, THE Status SHALL be `Pending` and must be manually verified by email click
3. WHEN sandbox mode is active, THE Sending Limits SHALL be documented (200 emails/day, 1 msg/sec)
4. IF production access is requested, THE Request Process SHALL be documented (approval in ~24h)
5. WHEN emails are sent, THE Source Email SHALL be configurable via variable

### Requirement 12: CloudWatch Monitoring

**User Story:** As a developer, I want CloudWatch monitoring and billing alarms, so that I can track costs and performance.

#### Acceptance Criteria

1. WHEN log groups are created, THE Retention Period SHALL be 7 days (default is never expire)
2. WHEN billing alarms are created, THE Following Alarms SHALL be created:
   1. `billing-alarm`: Trigger when estimated charges > $X (configurable via variable)
   2. `billing-unit`: USD

3. WHILE alarms are created, THE Alarm Actions SHALL include email notification or SNS topic
4. WHEN Lambda alarms are created, THE Following Alarms SHALL be created:
   1. `lambda-errors`: Trigger when error count > 0 in 5 minutes
   2. `lambda-duration`: Trigger when p95 duration > threshold (configurable)

5. WHERE metrics are published, THE Lambda Metrics SHALL include:
   - Invocations
   - Duration
   - Errors
   - Throttles

### Requirement 13: GitHub Actions OIDC Role

**User Story:** As a developer, I want an OIDC role for GitHub Actions, so that CI/CD can deploy without long-lived credentials.

#### Acceptance Criteria

1. WHEN an OIDC role is created, THE Trust Policy SHALL allow GitHub Actions to assume the role
2. WHEN the role is created, THE IAM Policy SHALL include permissions for Terraform deployment:
   - S3: GetObject, PutObject, ListBucket (for state and code)
   - Lambda: InvokeFunction, UpdateFunctionCode
   - DynamoDB: CreateTable, DescribeTable, etc. (all needed for infrastructure)
   - SQS: CreateQueue, SendMessage, etc.
   - Cognito: AdminCreateUser, etc. (for user management)
   - API Gateway: CreateRestApi, PutIntegration, etc.
   - S3: PutObject (for frontend assets)
   - CloudFront: CreateInvalidation
   - IAM: CreateRole, AttachRolePolicy, etc.

3. WHERE the role is used, THE Role ARN SHALL be exported for use in GitHub Actions workflow
4. WHEN the role is created, THE Session Name SHALL include `GitHub-Actions` for audit

### Requirement 14: Import Existing Resources

**User Story:** As a developer, I want to import existing manually created resources, so that I don't lose data or configuration.

#### Acceptance Criteria

1. WHEN resources are imported, THE Following 15 Resources SHALL be imported:
   - 7 DynamoDB Tables (Empresas, Vacantes, UsuarioVacante, Entradas, Perfiles, Suscripciones, ScanJobs)
   - 4 SQS Queues (scan-dlq, scan-queue, scoring-dlq, scoring-queue)
   - 1 Cognito User Pool (job-search-assistant)
   - 1 Cognito App Client (job-search-frontend)
   - 1 Cognito Hosted UI Domain (job-search-assistant-mvp)
   - 1 Resource Group (job-search-assistant)

2. WHILE resources are imported, THE Import Commands SHALL use actual ARNs and IDs from the deployment
3. WHERE import commands are needed, THE `terraform import` Commands SHALL be documented in a script
4. AFTER import is complete, THE Terraform State SHALL match the actual resources

### Requirement 15: Variables and Configuration

**User Story:** As a developer, I want configurable variables without hardcoded secrets, so that configuration is secure and flexible.

#### Acceptance Criteria

1. WHEN variables are defined, THE Following Variables SHALL be defined:
   1. `aws_region`: AWS region (default: `us-east-1`)
   2. `environment`: Environment name (default: `hackathon`)
   3. `project_name`: Project name (default: `job-search-assistant`)
   4. `terraform_state_bucket`: S3 bucket name for Terraform state (required, no default)
   5. `terraform_state_key`: S3 key for Terraform state (default: `terraform.tfstate`)
   6. `cognito_user_pool_id`: Cognito User Pool ID (required, no default)
   7. `frontend_domain`: Frontend domain (default: `job-search-assistant.mvp`)
   8. `ses_email`: Source email for SES (required, no default)
   9. `scan_worker_timeout`: Lambda timeout for scan-worker (default: `90`)
   10. `scoring_worker_timeout`: Lambda timeout for scoring-worker (default: `30`)
   11. `billing_alarm_threshold`: Monthly billing threshold in USD (default: `500`)
   12. `cors_origins`: Comma-separated list of CORS allowed origins (default: `http://localhost:5173`)
   13. `bedrock_model_small`: Bedrock model ID for the small model (required, no default)
   14. `bedrock_model_mid`: Bedrock model ID for the mid-tier model (required, no default)

2. WHEN variables are defined, THE Sensitive Variables SHALL NOT have defaults:
   - `cognito_user_pool_id`
   - `terraform_state_bucket`
   - `ses_email`

3. WHILE variables are defined, THE Required Variables SHALL be marked as required
4. WHERE terraform.tfvars is used, THE File SHALL be gitignored (not versioned)
5. WHEN terraform.tfvars.example is created, THE File SHALL be versioned as template with placeholder values
6. WHERE `bedrock_model_small` and `bedrock_model_mid` are documented, THE Documentation SHALL note the `us.` region-prefix requirement for cross-region inference profiles in `us-east-1` (e.g. `us.anthropic.claude-...`), since several current Bedrock models are only invocable via inference profiles and not via the bare base model ID

### Requirement 16: Structure and Organization

**User Story:** As a developer, I want a clear Terraform structure, so that the infrastructure is maintainable.

#### Acceptance Criteria

1. WHEN structure is organized, THE Following Structure SHALL be used:
   ```
   terraform/
   ├── main.tf                 # Root module, calls submodules
   ├── variables.tf            # Variables definition
   ├── terraform.tfvars        # Actual values (gitignored)
   ├── terraform.tfvars.example # Template (versioned)
   ├── outputs.tf              # Outputs
   ├── backend.tf              # Backend configuration
   ├── providers.tf            # Provider configuration
   ├── terraform.tf            # Terraform version constraint
   ├── scripts/
   │   └── import_resources.sh # Import commands for existing resources
   └── modules/
       ├── dynamodb/
       │   └── main.tf         # DynamoDB tables
       ├── sqs/
       │   └── main.tf         # SQS queues and DLQs
       ├── lambda/
       │   └── main.tf         # Lambda functions (single module, multiple functions)
       ├── api-gateway/
       │   └── main.tf         # API Gateway with Cognito authorizer
       ├── cognito/
       │   └── main.tf         # Cognito User Pool (import only)
       ├── s3-cloudfront/
       │   └── main.tf         # S3 bucket and CloudFront distribution
       ├── eventbridge/
       │   └── main.tf         # EventBridge Scheduler
       ├── ses/
       │   └── main.tf         # SES configuration
       └── cloudwatch/
           └── main.tf         # CloudWatch log groups and alarms
   ```

2. WHILE modules are created, THE Modules SHALL be separate directories with their own variables.tf and outputs.tf
3. WHEN modules are called, THE Main Module SHALL call all submodules with appropriate variables
4. WHERE state is managed, THE Backend Configuration SHALL be in `backend.tf` (not in `main.tf`)

### Requirement 17: Security Requirements

**User Story:** As a developer, I want secure infrastructure, so that the application is protected from unauthorized access.

#### Acceptance Criteria

1. WHILE resources are created, THE Secret Values SHALL NOT be hardcoded (Account ID, ARNs, Cognito IDs, etc.)
2. WHERE sensitive values are needed, THE Variables SHALL be read from `terraform.tfvars` (gitignored)
3. WHEN IAM policies are created, THE Policies SHALL follow the principle of least privilege
4. WHILE S3 buckets are created, THE Bucket Policy SHALL NOT allow public access
5. WHEN CloudFront distribution is created, THE Distribution SHALL have `Viewer Protocol Policy = Redirect HTTP to HTTPS`
6. WHERE SES is used, THE Sandbox Mode SHALL be clearly documented
7. WHEN lambda environment variables are set, THE Sensitive Variables SHALL use `sensitive = true`

### Requirement 18: Out of Scope

**User Story:** As a developer, I want to know what's out of scope, so that I don't expect functionality that isn't provided.

#### Acceptance Criteria

1. THE Following Items SHALL be explicitly out of scope:
   1. GitHub Actions workflow YAML (only the IAM role for OIDC)
   2. Manual S3 bucket creation for backend state (Terraform cannot manage its own initial backend)
   3. Manual SES email verification (each owner must manually click verification link)
   4. Frontend code (React SPA)
   5. Backend code (Python Lambda functions)
   6. Database migrations
   7. Data seeding
   8. Domain registration or SSL certificate request (ACM certificate must be manually created or imported)
   9. Route53 hosted zone or DNS configuration
   10. VPC, subnets, security groups (Lambda runs in default VPC)
   11. KMS keys for encryption (S3 default encryption is sufficient)
   12. CloudWatch dashboards (only alarms)
   13. Lambda layers or provisioned concurrency

2. WHERE out of scope items are mentioned, THE Documentation SHALL state that they must be handled separately

### Requirement 19: Dependencies

**User Story:** As a developer, I want to know dependencies between resources, so that I can understand the deployment order.

#### Acceptance Criteria

1. WHILE resources are deployed, THE Following Dependencies SHALL be respected:
   1. DynamoDB tables must exist before Lambda functions (for environment variable references)
   2. SQS queues must exist before Lambda functions (for queue URLs in environment variables)
   3. Cognito User Pool must exist before API Gateway authorizer (for User Pool ARN)
   4. S3 bucket must exist before CloudFront distribution (for origin configuration)
   5. IAM roles must exist before Lambda functions (for role ARN)
   6. API Gateway must exist before CloudFront distribution (for origin if API is behind CDN)

2. WHEN dependencies are not explicit, THE Terraform `depends_on` SHALL be used to enforce order
3. WHERE circular dependencies exist, THE Architecture SHALL be refactored to remove them

### Requirement 20: Validation and Testing

**User Story:** As a developer, I want to validate and test the infrastructure, so that I can catch errors before deployment.

#### Acceptance Criteria

1. WHEN validation is run, THE `terraform validate` SHALL pass without errors
2. WHILE validation is run, THE `terraform fmt -check` SHALL pass (or `terraform fmt -write` shall be run)
3. WHEN tests are run, THE `terraform plan` SHALL not show unexpected changes after import
4. WHERE infrastructure changes are made, THE `terraform plan` SHALL be reviewed before `terraform apply`

### Requirement 21: Documentation

**User Story:** As a developer, I want documentation for the infrastructure, so that I can understand and maintain it.

#### Acceptance Criteria

1. WHILE documentation is created, THE Following Documentation SHALL be provided:
   1. README.md in terraform directory explaining structure and setup
   2. Comments in code explaining resource purpose
   3. Import script with step-by-step instructions
   4. List of environment variables and their purposes
   5. Security considerations and best practices
   6. Cost estimation and monitoring guidance

2. WHEN documentation is updated, THE Documentation SHALL be kept in sync with code changes
3. WHERE secrets are mentioned, THE Documentation SHALL NOT include actual secret values

### Requirement 22: Safety Requirements

**User Story:** As a developer, I want safety requirements to prevent accidental data loss, so that critical resources are protected.

#### Acceptance Criteria

1. WHILE DynamoDB tables and Cognito User Pool are managed, THE `prevent_destroy = true` Lifecycle Policy SHALL be applied
2. IF a destroy plan is generated, THE Plan SHALL fail explicitly (not just warn)
3. WHEN resources are created, THE Deletion Protection SHALL be enabled where available
4. WHILE resources are updated, THE Resource Updates SHALL NOT cause data loss

## Dependencies

This spec has a dependency on the `backend-scan-y-scoring` design document for the following information:
- Lambda function names: `api`, `orquestador`, `scan-worker`, `scoring-worker`, `notificador`
- Lambda timeouts: `scan-worker` = 90s, `scoring-worker` = 30s (used to calculate SQS visibility timeouts)
- Lambda concurrency: `scan-worker` = 5, `scoring-worker` = 3 (reserved concurrency)
- Lambda memory: `scan-worker` = 1024MB, `scoring-worker` = 1024MB
- Lambda environment variables (from backend-scan-y-scoring design.md)
- IAM permissions per Lambda (from backend-scan-y-scoring design.md)
- SQS visibility timeout values: `backend-scan-y-scoring/design.md`, section "SQS Queue Configuration & Visibility Timeout Formulas", ALREADY fixes these exact values as confirmed (not placeholder assumptions made by this spec):
  - `scan-worker` Lambda timeout = 90s → `scan-queue` visibility timeout = 540s (6 × 90s)
  - `scoring-worker` Lambda timeout = 30s → `scoring-queue` visibility timeout = 180s (6 × 30s)

## Constraints

1. **Terraform Version**: Must use Terraform 1.5+ for `depends_on` improvements
2. **AWS Region**: us-east-1 only (cheaper, better Bedrock availability)
3. **Lambda Runtime**: Python 3.12 only (no Node.js, Java, or Go)
4. **Lambda Packaging**: .zip format only (no Docker/ECR containers)
5. **SQS Visibility Timeout**: Must be 6 × Lambda timeout (critical for idempotency)
6. **DynamoDB Billing**: On-demand (PAY_PER_REQUEST) only, no provisioned capacity
7. **CloudWatch Log Retention**: 7 days (default is never expire, which causes cost issues)
8. **S3 Bucket Name**: Must be globally unique (user must provide or generate)
9. **Cognito User Pool**: Import only, cannot be recreated (would lose users)
10. **Bedrock Model IDs**: Never hardcoded, always read from environment variables

## In Scope vs. Out of Scope

### In Scope

- Terraform infrastructure code for all AWS resources
- S3 backend state management
- DynamoDB tables (7) with correct PK/SK/GSI/TTL
- SQS queues (4) with DLQs and correct visibility timeouts
- Lambda functions (5) with correct memory, timeout, and concurrency
- IAM roles and policies (minimal privilege, one per Lambda)
- API Gateway with Cognito authorizer
- S3 + CloudFront for frontend static hosting
- EventBridge Scheduler for orquestador Lambda
- SES email configuration
- CloudWatch log groups with 7-day retention
- Billing alarms
- GitHub Actions OIDC role
- Import commands for 15 existing resources
- Variables without hardcoded secrets
- terraform.tfvars.example template

### Out of Scope

- GitHub Actions workflow YAML (only IAM role for OIDC)
- Manual S3 bucket creation (Terraform cannot manage its own initial backend)
- Manual SES email verification
- Frontend code (React SPA)
- Backend code (Python Lambda functions)
- Database migrations
- Data seeding
- Domain registration or SSL certificate
- Route53 hosted zone or DNS configuration
- VPC, subnets, security groups
- KMS keys for encryption
- CloudWatch dashboards
- Lambda layers or provisioned concurrency

## Next Steps

After this requirements document is complete, the next phase is:
1. Design: Create design.md with module structure, resource definitions, and implementation plan
2. Tasks: Break down implementation into specific tasks with acceptance criteria
3. Implementation: Write Terraform code following the design
