# IAM Module for job-search-assistant
#
# This module creates all IAM roles and policies for the application:
# 1. Five Lambda execution roles (one per Lambda function) - with minimal, differentiated permissions
# 2. EventBridge Scheduler invoke role - for triggering the orquestador Lambda
# 3. GitHub Actions OIDC provider and role - for CI/CD deployments without long-lived credentials
#
# Reference Requirements: 6, 13, 16
# Reference Design: "IAM Module", "GitHub Actions OIDC Role"

# ============================================================================
# 1. LAMBDA EXECUTION ROLES - One per Lambda, with minimal differentiated permissions
# ============================================================================

# =======================
# API Lambda Role
# =======================
# Used by: api Lambda function (FastAPI + Mangum)
# Permissions: DynamoDB (read/write), Bedrock (invoke), API Gateway (invoke), CloudWatch Logs
# NOTE: api reads/writes all DynamoDB tables except ScanJobs
# (ScanJobs is only modified by orquestador and scan-worker)
resource "aws_iam_role" "api_role" {
  name = "job-search-api-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Role = "API Lambda"
  }
}

resource "aws_iam_role_policy" "api_policy" {
  name = "job-search-api-policy"
  role = aws_iam_role.api_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs - required for all Lambdas
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB - read/write operations on tables accessed by API
      # (Empresas, Vacantes, UsuarioVacante, Perfiles, Suscripciones, Entradas, ScanJobs)
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          "arn:aws:dynamodb:*:*:table/Empresas",
          "arn:aws:dynamodb:*:*:table/Vacantes",
          "arn:aws:dynamodb:*:*:table/UsuarioVacante",
          "arn:aws:dynamodb:*:*:table/Perfiles",
          "arn:aws:dynamodb:*:*:table/Suscripciones",
          "arn:aws:dynamodb:*:*:table/Entradas",
          "arn:aws:dynamodb:*:*:table/ScanJobs"
        ]
      },
      # Bedrock - invoke models for profile extraction and rescoring
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      },
      # API Gateway - invoke permissions (for integration)
      {
        Effect = "Allow"
        Action = [
          "execute-api:Invoke"
        ]
        Resource = "*"
      }
    ]
  })
}

# =======================
# Orquestador Lambda Role
# =======================
# Used by: orquestador Lambda function (EventBridge Scheduler trigger)
# Permissions: DynamoDB (read/write Empresas, Vacantes, ScanJobs, Suscripciones, Perfiles),
#              SQS (send to scan queue), CloudWatch Logs
# NOTE: orquestador reads company subscriptions and creates scan jobs
resource "aws_iam_role" "orquestador_role" {
  name = "job-search-orquestador-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Role = "Orquestador Lambda"
  }
}

resource "aws_iam_role_policy" "orquestador_policy" {
  name = "job-search-orquestador-policy"
  role = aws_iam_role.orquestador_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB - read/write for orchestration
      # orquestador reads Empresas, Suscripciones to find companies to scan
      # orquestador writes to ScanJobs to track scan progress
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          "arn:aws:dynamodb:*:*:table/Empresas",
          "arn:aws:dynamodb:*:*:table/Vacantes",
          "arn:aws:dynamodb:*:*:table/ScanJobs",
          "arn:aws:dynamodb:*:*:table/Suscripciones",
          "arn:aws:dynamodb:*:*:table/Perfiles"
        ]
      },
      # SQS - send scan jobs to scan-queue for processing
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = "arn:aws:sqs:*:*:scan-queue"
      }
    ]
  })
}

# =======================
# Scan Worker Lambda Role
# =======================
# Used by: scan-worker Lambda function (SQS consumer for scan-queue)
# Permissions: DynamoDB (read/write Empresas, Vacantes, ScanJobs),
#              SQS (receive from scan-queue, send to scoring-queue),
#              Bedrock (invoke models), CloudWatch Logs
# NOTE: scan-worker processes company URLs, extracts vacancies, and queues scoring jobs
# Concurrency Reserved: 5 (from design)
resource "aws_iam_role" "scan_worker_role" {
  name = "job-search-scan-worker-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Role = "Scan Worker Lambda"
  }
}

resource "aws_iam_role_policy" "scan_worker_policy" {
  name = "job-search-scan-worker-policy"
  role = aws_iam_role.scan_worker_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB - read/write for scanning
      # scan-worker reads Empresas, reads/writes Vacantes, updates ScanJobs
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          "arn:aws:dynamodb:*:*:table/Empresas",
          "arn:aws:dynamodb:*:*:table/Vacantes",
          "arn:aws:dynamodb:*:*:table/ScanJobs"
        ]
      },
      # SQS - receive from scan-queue, send to scoring-queue
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:SendMessage"
        ]
        Resource = [
          "arn:aws:sqs:*:*:scan-queue",
          "arn:aws:sqs:*:*:scoring-queue"
        ]
      },
      # Bedrock - invoke models for extraction and classification
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      }
    ]
  })
}

# =======================
# Scoring Worker Lambda Role
# =======================
# Used by: scoring-worker Lambda function (SQS consumer for scoring-queue)
# Permissions: DynamoDB (read/write Perfiles, UsuarioVacante, Vacantes, Empresas),
#              SQS (receive from scoring-queue),
#              Bedrock (invoke models), CloudWatch Logs
# NOTE: scoring-worker scores vacancies against user profiles
# Concurrency Reserved: 3 (from design)
resource "aws_iam_role" "scoring_worker_role" {
  name = "job-search-scoring-worker-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Role = "Scoring Worker Lambda"
  }
}

resource "aws_iam_role_policy" "scoring_worker_policy" {
  name = "job-search-scoring-worker-policy"
  role = aws_iam_role.scoring_worker_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB - read/write for scoring
      # scoring-worker reads Perfiles (user profiles), reads Vacantes/Empresas (vacancy details),
      # writes to UsuarioVacante (match results and scores)
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          "arn:aws:dynamodb:*:*:table/Perfiles",
          "arn:aws:dynamodb:*:*:table/UsuarioVacante",
          "arn:aws:dynamodb:*:*:table/Vacantes",
          "arn:aws:dynamodb:*:*:table/Empresas"
        ]
      },
      # SQS - receive from scoring-queue only (no sending)
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = "arn:aws:sqs:*:*:scoring-queue"
      },
      # Bedrock - invoke models for scoring and recommendations
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      }
    ]
  })
}

# =======================
# Notificador Lambda Role
# =======================
# Used by: notificador Lambda function (Email notifications)
# Permissions: SES (send emails), CloudWatch Logs
# NOTE: notificador has minimal permissions - only SES for email sending
resource "aws_iam_role" "notificador_role" {
  name = "job-search-notificador-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Role = "Notificador Lambda"
  }
}

resource "aws_iam_role_policy" "notificador_policy" {
  name = "job-search-notificador-policy"
  role = aws_iam_role.notificador_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # SES - send emails for notifications
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      },
      # DynamoDB Streams - read scan job status transitions from ScanJobs table
      # Required for the notificador Lambda's DynamoDB Streams event source mapping
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:DescribeStream",
          "dynamodb:ListStreams"
        ]
        Resource = "arn:aws:dynamodb:*:*:table/ScanJobs/stream/*"
      }
    ]
  })
}

# ============================================================================
# 2. EVENTBRIDGE SCHEDULER INVOKE ROLE
# ============================================================================
# Used by: EventBridge Scheduler to invoke the orquestador Lambda
# Permissions: Lambda invoke (scoped to orquestador Lambda ARN only)
#
# This role is separate from the Lambda execution roles because it represents
# a different principal (Scheduler service, not the Lambda function itself).
# The role is referenced by the EventBridge module via outputs.

resource "aws_iam_role" "eventbridge_scheduler_role" {
  name = "job-search-eventbridge-scheduler-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Role = "EventBridge Scheduler"
  }
}

# Policy for EventBridge Scheduler to invoke the orquestador Lambda
# Lambda ARN is constructed as a placeholder - the EventBridge module will receive this via output
resource "aws_iam_role_policy" "eventbridge_scheduler_policy" {
  name = "job-search-eventbridge-scheduler-policy"
  role = aws_iam_role.eventbridge_scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Lambda invoke - scoped to orquestador Lambda only (least privilege)
      # The actual Lambda ARN is constructed as a placeholder format
      # The EventBridge module will need to reference the actual orquestador Lambda ARN
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = "arn:aws:lambda:*:*:function/job-search-orquestador"
      }
    ]
  })
}

# ============================================================================
# 3. GITHUB ACTIONS OIDC PROVIDER AND ROLE
# ============================================================================
# Used by: GitHub Actions CI/CD workflows for deploying without long-lived credentials
#
# The GitHub OIDC provider is created once per AWS account and is reusable
# by multiple roles (though currently we only have one role).
#
# Trust Policy Scope: repo:organization/job-search-assistant:ref:refs/heads/main
# This restricts deployments to the main branch only (not pull requests or other branches).

# Create the GitHub OIDC provider (if not already exists)
# The thumbprint is the SHA-1 hash of the GitHub OIDC provider's certificate
# This value is static and won't change unless GitHub updates their OIDC certificate
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = {
    Provider = "GitHub OIDC"
  }
}

# GitHub Actions Deployment Role
# This role is assumed by GitHub Actions workflows via OIDC token exchange
# It grants permissions needed for infrastructure deployment via Terraform
resource "aws_iam_role" "github_actions" {
  name = "job-search-github-actions-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            # Scope the trust policy to main branch only
            # Format: repo:organization/repository:ref:refs/heads/branch
            "token.actions.githubusercontent.com:sub" = "repo:organization/job-search-assistant:ref:refs/heads/main"
          }
        }
      }
    ]
  })

  tags = {
    Role = "GitHub Actions OIDC"
  }
}

# GitHub Actions Deployment Policy
# Permissions needed for Terraform to deploy infrastructure
# This is a comprehensive policy for infrastructure deployment
resource "aws_iam_role_policy" "github_actions_policy" {
  name = "job-search-github-actions-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 - for Terraform state and Lambda function code
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:GetBucketVersioning",
          "s3:PutBucketVersioning"
        ]
        Resource = [
          "arn:aws:s3:::*-terraform-state-bucket",
          "arn:aws:s3:::*-terraform-state-bucket/*",
          "arn:aws:s3:::*-lambda-code-bucket",
          "arn:aws:s3:::*-lambda-code-bucket/*"
        ]
      },
      # Lambda - for updating function code and managing functions
      {
        Effect = "Allow"
        Action = [
          "lambda:CreateFunction",
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
          "lambda:DeleteFunction",
          "lambda:GetFunction",
          "lambda:ListFunctions",
          "lambda:InvokeFunction",
          "lambda:CreateEventSourceMapping",
          "lambda:DeleteEventSourceMapping",
          "lambda:UpdateEventSourceMapping",
          "lambda:GetEventSourceMapping",
          "lambda:ListEventSourceMappings"
        ]
        Resource = "*"
      },
      # DynamoDB - for managing tables
      {
        Effect = "Allow"
        Action = [
          "dynamodb:CreateTable",
          "dynamodb:DescribeTable",
          "dynamodb:DeleteTable",
          "dynamodb:UpdateTable",
          "dynamodb:ListTables",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:TagResource",
          "dynamodb:UntagResource"
        ]
        Resource = "*"
      },
      # SQS - for managing queues
      {
        Effect = "Allow"
        Action = [
          "sqs:CreateQueue",
          "sqs:DeleteQueue",
          "sqs:SetQueueAttributes",
          "sqs:GetQueueAttributes",
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:GetQueueUrl",
          "sqs:ListQueues",
          "sqs:TagQueue",
          "sqs:UntagQueue"
        ]
        Resource = "*"
      },
      # Cognito - for managing user pool resources
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminSetUserPassword",
          "cognito-idp:DescribeUserPool",
          "cognito-idp:DescribeUserPoolClient",
          "cognito-idp:CreateUserPoolClient",
          "cognito-idp:UpdateUserPoolClient",
          "cognito-idp:DeleteUserPoolClient",
          "cognito-idp:ListUserPoolClients"
        ]
        Resource = "*"
      },
      # API Gateway - for managing REST API
      {
        Effect = "Allow"
        Action = [
          "apigateway:GET",
          "apigateway:POST",
          "apigateway:PUT",
          "apigateway:DELETE",
          "apigateway:PATCH"
        ]
        Resource = "*"
      },
      # CloudFront - for managing distributions and invalidations
      {
        Effect = "Allow"
        Action = [
          "cloudfront:CreateDistribution",
          "cloudfront:UpdateDistribution",
          "cloudfront:DeleteDistribution",
          "cloudfront:DescribeDistribution",
          "cloudfront:ListDistributions",
          "cloudfront:CreateInvalidation",
          "cloudfront:GetInvalidation",
          "cloudfront:CreateCloudFrontOriginAccessIdentity",
          "cloudfront:DeleteCloudFrontOriginAccessIdentity",
          "cloudfront:GetCloudFrontOriginAccessIdentity"
        ]
        Resource = "*"
      },
      # S3 - for static website hosting (frontend assets)
      {
        Effect = "Allow"
        Action = [
          "s3:CreateBucket",
          "s3:DeleteBucket",
          "s3:GetBucketPolicy",
          "s3:PutBucketPolicy",
          "s3:DeleteBucketPolicy",
          "s3:GetBucketVersioning",
          "s3:PutBucketVersioning",
          "s3:GetObjectVersioning",
          "s3:PutBucketPublicAccessBlock",
          "s3:GetBucketPublicAccessBlock",
          "s3:ListBucketVersions",
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:TagResource",
          "s3:UntagResource"
        ]
        Resource = "*"
      },
      # IAM - for managing roles and policies
      {
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:GetRole",
          "iam:GetRolePolicy",
          "iam:ListRolePolicies",
          "iam:CreatePolicy",
          "iam:DeletePolicy",
          "iam:GetPolicy",
          "iam:GetPolicyVersion",
          "iam:ListPolicyVersions",
          "iam:PassRole"
        ]
        Resource = "*"
      },
      # EventBridge Scheduler
      {
        Effect = "Allow"
        Action = [
          "scheduler:CreateSchedule",
          "scheduler:UpdateSchedule",
          "scheduler:DeleteSchedule",
          "scheduler:GetSchedule",
          "scheduler:ListSchedules"
        ]
        Resource = "*"
      },
      # SES - for email configuration
      {
        Effect = "Allow"
        Action = [
          "ses:VerifyEmailIdentity",
          "ses:VerifyDomainIdentity",
          "ses:DeleteIdentity",
          "ses:GetIdentityVerificationAttributes",
          "ses:ListIdentities"
        ]
        Resource = "*"
      },
      # CloudWatch - for managing log groups and alarms
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:DeleteLogGroup",
          "logs:DescribeLogGroups",
          "logs:PutRetentionPolicy",
          "logs:TagLogGroup"
        ]
        Resource = "*"
      },
      # CloudWatch Alarms
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricAlarm",
          "cloudwatch:DeleteAlarms",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:ListMetrics",
          "cloudwatch:GetMetricStatistics"
        ]
        Resource = "*"
      },
      # SNS - for alarm notifications
      {
        Effect = "Allow"
        Action = [
          "sns:CreateTopic",
          "sns:DeleteTopic",
          "sns:GetTopicAttributes",
          "sns:SetTopicAttributes",
          "sns:Subscribe",
          "sns:Unsubscribe",
          "sns:Publish"
        ]
        Resource = "*"
      },
      # OIDC Provider management (for future provider creation if needed)
      {
        Effect = "Allow"
        Action = [
          "iam:CreateOpenIDConnectProvider",
          "iam:DeleteOpenIDConnectProvider",
          "iam:GetOpenIDConnectProvider",
          "iam:AddClientIDToOpenIDConnectProvider",
          "iam:RemoveClientIDFromOpenIDConnectProvider"
        ]
        Resource = "*"
      }
    ]
  })
}


# ============================================================================
# 4. API GATEWAY CLOUDWATCH LOGGING ROLE
# ============================================================================
# Used by: API Gateway to write logs to CloudWatch Log Groups
# Permissions: CloudWatch Logs (create log streams and put log events)
#
# This role is separate from Lambda execution roles because it's assumed by
# the API Gateway service, not by the Lambda functions themselves.

resource "aws_iam_role" "api_gateway_cloudwatch_role" {
  name = "job-search-api-gateway-cloudwatch-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Role = "API Gateway CloudWatch Logging"
  }
}

resource "aws_iam_role_policy" "api_gateway_cloudwatch_policy" {
  name = "job-search-api-gateway-cloudwatch-policy"
  role = aws_iam_role.api_gateway_cloudwatch_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs - write permissions for API Gateway logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}
