#!/bin/bash

################################################################################
# Terraform Import Script for Job Search Assistant
#
# This script imports 15 existing AWS resources into Terraform state:
# - 7 DynamoDB tables
# - 4 SQS queues
# - 1 Cognito User Pool
# - 1 Cognito App Client
# - 1 Cognito Hosted UI Domain
# - 1 Resource Group
#
# IMPORTANT NOTES:
#
# 1. Prerequisites:
#    - Terraform must be initialized: terraform init
#    - terraform.tfvars must be configured with actual values
#    - All 15 resources must already exist in AWS
#    - AWS credentials must be configured (AWS_PROFILE, AWS_ACCESS_KEY_ID, etc.)
#
# 2. Getting Resource IDs/ARNs:
#    - DynamoDB Table ARNs: aws dynamodb list-tables --region us-east-1
#      Example: arn:aws:dynamodb:us-east-1:123456789012:table/Empresas
#    - SQS Queue URLs: aws sqs list-queues --region us-east-1
#      Example: https://sqs.us-east-1.amazonaws.com/123456789012/scan-queue
#    - Cognito User Pool ID: aws cognito-idp list-user-pools --max-results 10 --region us-east-1
#      Example: us-east-1_abcdefghi
#    - Cognito App Client ID: aws cognito-idp list-user-pool-clients --user-pool-id <pool-id> --region us-east-1
#      Example: c7dt8acog5t0ifssh05eq0gc4
#    - Resource Group ARN: aws resource-groups list-groups --region us-east-1
#      Example: arn:aws:resource-groups:us-east-1:123456789012:group/job-search-assistant
#
# 3. Execution:
#    - Review each import command before running
#    - Replace placeholder values (AWS_ACCOUNT_ID, USER_POOL_ID, CLIENT_ID, RESOURCE_GROUP_ARN)
#      with actual values from your AWS account
#    - Run this script from the terraform/ directory: bash scripts/import_resources.sh
#    - Or run individual import commands manually if you prefer granular control
#
# 4. Manual Prerequisites:
#    - The following are NOT imported (they must be verified to exist before running this script):
#      - S3 bucket for Terraform backend (must be created manually)
#      - SES email identities (must be manually verified via email link)
#
# 5. Verification:
#    - After running imports, verify with: terraform state list
#    - Check for any resources showing errors in output
#    - Run: terraform plan (should show 0 changes for imported resources)
#
################################################################################

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'  # No Color

# Configuration
REGION="us-east-1"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Terraform Import Script - Job Search Assistant${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if terraform is installed
if ! command -v terraform &> /dev/null; then
    echo -e "${RED}ERROR: terraform is not installed or not in PATH${NC}"
    exit 1
fi

# Check if we're in the terraform directory
if [ ! -f "terraform.tf" ]; then
    echo -e "${RED}ERROR: terraform.tf not found. Please run this script from the terraform/ directory${NC}"
    exit 1
fi

# Check if terraform has been initialized
if [ ! -d ".terraform" ]; then
    echo -e "${RED}ERROR: Terraform not initialized. Run 'terraform init' first${NC}"
    exit 1
fi

# Check if terraform.tfvars exists
if [ ! -f "terraform.tfvars" ]; then
    echo -e "${RED}ERROR: terraform.tfvars not found. Please create it from terraform.tfvars.example${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Collecting Resource IDs from AWS...${NC}"
echo ""

# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}ERROR: Could not determine AWS Account ID. Check AWS credentials.${NC}"
    exit 1
fi
echo -e "AWS Account ID: ${GREEN}${AWS_ACCOUNT_ID}${NC}"

# Get Cognito User Pool ID from terraform.tfvars
COGNITO_USER_POOL_ID=$(grep "cognito_user_pool_id" terraform.tfvars | grep -o '"[^"]*"' | head -1 | tr -d '"')
if [ -z "$COGNITO_USER_POOL_ID" ]; then
    echo -e "${YELLOW}WARNING: Could not extract cognito_user_pool_id from terraform.tfvars${NC}"
    read -p "Enter Cognito User Pool ID (e.g., us-east-1_abcdefghi): " COGNITO_USER_POOL_ID
fi
echo -e "Cognito User Pool ID: ${GREEN}${COGNITO_USER_POOL_ID}${NC}"

# Get Cognito App Client ID from AWS
echo ""
echo "Fetching Cognito App Client ID from AWS..."
COGNITO_APP_CLIENT_ID=$(aws cognito-idp list-user-pool-clients \
    --user-pool-id "$COGNITO_USER_POOL_ID" \
    --region "$REGION" \
    --query 'UserPoolClients[0].ClientId' \
    --output text 2>/dev/null || echo "")

if [ -z "$COGNITO_APP_CLIENT_ID" ] || [ "$COGNITO_APP_CLIENT_ID" = "None" ]; then
    echo -e "${YELLOW}WARNING: Could not fetch Cognito App Client ID from AWS${NC}"
    read -p "Enter Cognito App Client ID (e.g., c7dt8acog5t0ifssh05eq0gc4): " COGNITO_APP_CLIENT_ID
fi
echo -e "Cognito App Client ID: ${GREEN}${COGNITO_APP_CLIENT_ID}${NC}"

# Get Resource Group ARN
echo ""
echo "Fetching Resource Group ARN from AWS..."
RESOURCE_GROUP_ARN=$(aws resource-groups list-groups \
    --region "$REGION" \
    --query 'Groups[0].GroupArn' \
    --output text 2>/dev/null || echo "")

if [ -z "$RESOURCE_GROUP_ARN" ] || [ "$RESOURCE_GROUP_ARN" = "None" ]; then
    echo -e "${YELLOW}WARNING: Could not fetch Resource Group ARN from AWS${NC}"
    read -p "Enter Resource Group ARN (e.g., arn:aws:resource-groups:us-east-1:123456789012:group/job-search-assistant): " RESOURCE_GROUP_ARN
fi
echo -e "Resource Group ARN: ${GREEN}${RESOURCE_GROUP_ARN}${NC}"

echo ""
echo -e "${YELLOW}Step 2: Importing DynamoDB Tables (7 tables)...${NC}"
echo ""

# Import DynamoDB Tables
DYNAMODB_TABLES=(
    "Empresas"
    "Vacantes"
    "UsuarioVacante"
    "Entradas"
    "Perfiles"
    "Suscripciones"
    "ScanJobs"
)

for table in "${DYNAMODB_TABLES[@]}"; do
    echo -n "Importing DynamoDB table: $table ... "
    if terraform import "aws_dynamodb_table.${table,,}" "$table" 2>/dev/null; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${YELLOW}SKIPPED (might already be imported or doesn't exist)${NC}"
    fi
done

echo ""
echo -e "${YELLOW}Step 3: Importing SQS Queues (4 queues)...${NC}"
echo ""

# Import SQS Queues - need full URLs
SQS_QUEUES=(
    "scan-dlq"
    "scan-queue"
    "scoring-dlq"
    "scoring-queue"
)

for queue in "${SQS_QUEUES[@]}"; do
    queue_url="https://sqs.${REGION}.amazonaws.com/${AWS_ACCOUNT_ID}/${queue}"
    echo -n "Importing SQS queue: $queue ... "
    if terraform import "aws_sqs_queue.${queue//-/_}" "$queue_url" 2>/dev/null; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${YELLOW}SKIPPED (might already be imported or doesn't exist)${NC}"
    fi
done

echo ""
echo -e "${YELLOW}Step 4: Importing Cognito User Pool...${NC}"
echo ""

echo -n "Importing Cognito User Pool: $COGNITO_USER_POOL_ID ... "
if terraform import "aws_cognito_user_pool.user_pool" "$COGNITO_USER_POOL_ID" 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}SKIPPED (might already be imported)${NC}"
fi

echo ""
echo -e "${YELLOW}Step 5: Importing Cognito App Client...${NC}"
echo ""

COGNITO_APP_CLIENT_IMPORT="${COGNITO_USER_POOL_ID}/${COGNITO_APP_CLIENT_ID}"
echo -n "Importing Cognito App Client: $COGNITO_APP_CLIENT_ID ... "
if terraform import "aws_cognito_user_pool_client.frontend" "$COGNITO_APP_CLIENT_IMPORT" 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}SKIPPED (might already be imported)${NC}"
fi

echo ""
echo -e "${YELLOW}Step 6: Importing Cognito Hosted UI Domain...${NC}"
echo ""

COGNITO_DOMAIN="job-search-assistant-mvp"
echo -n "Importing Cognito Hosted UI Domain: $COGNITO_DOMAIN ... "
if terraform import "aws_cognito_user_pool_domain.frontend" "$COGNITO_DOMAIN" 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}SKIPPED (might already be imported or doesn't exist)${NC}"
fi

echo ""
echo -e "${YELLOW}Step 7: Importing Resource Group...${NC}"
echo ""

echo -n "Importing Resource Group ... "
if terraform import "aws_resourcegroups_group.job_search_assistant" "$RESOURCE_GROUP_ARN" 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}SKIPPED (might already be imported or doesn't exist)${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Import Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Review imported resources: ${GREEN}terraform state list${NC}"
echo "2. Verify no changes needed: ${GREEN}terraform plan${NC}"
echo "3. If all looks good, apply: ${GREEN}terraform apply${NC}"
echo ""
echo -e "${YELLOW}Manual Post-Deploy Steps:${NC}"
echo "1. Update Cognito Callback URLs to point to the actual CloudFront domain"
echo "2. Verify SES email identities are verified (check email inbox for verification links)"
echo "3. Test API Gateway routes with valid JWT tokens"
echo ""
