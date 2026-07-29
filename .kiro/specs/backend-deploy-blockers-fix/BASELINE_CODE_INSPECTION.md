# Task 7: Code Inspection Baseline

## Current Handler Function Names (Before Fix)

### Scan Worker - File: `backend/workers/scan_worker.py`

**Current function name**: `handler_scan_worker`
**Location**: Last function in the file (after `_handle_failed_or_sospechoso`)
**Signature**: `def handler_scan_worker(event: Dict[str, Any], context: Any) -> Dict[str, Any]:`

**Test imports affected**:
- `backend/tests/test_scan_worker.py` line 140: `from backend.workers.scan_worker import handler_scan_worker`
- `backend/tests/test_scan_worker.py` line 179: `from backend.workers.scan_worker import handler_scan_worker`
- `backend/tests/test_scan_worker.py` line 273: `from backend.workers.scan_worker import handler_scan_worker`
- `backend/tests/test_scan_worker.py` line 302: `from backend.workers.scan_worker import handler_scan_worker`
- `backend/tests/test_scan_worker.py` line 331: `from backend.workers.scan_worker import handler_scan_worker`

**Test invocations affected**: Lines 160, 209, 286, 315, 343 (function calls using the old name)

### Scoring Worker - File: `backend/workers/scoring_worker.py`

**Current function name**: `handler_scoring_worker`
**Location**: Around line 150 (in main handler section, after helper functions)
**Signature**: `def handler_scoring_worker(event: Dict[str, Any], context: Any) -> None:`

**Test imports affected**:
- `backend/tests/test_scoring_worker.py` line 225: `from backend.workers.scoring_worker import handler_scoring_worker`
- `backend/tests/test_scoring_worker.py` line 263: `from backend.workers.scoring_worker import handler_scoring_worker`
- `backend/tests/test_scoring_worker.py` line 315: `from backend.workers.scoring_worker import handler_scoring_worker`
- `backend/tests/test_scoring_worker.py` line 375: `from backend.workers.scoring_worker import handler_scoring_worker`
- `backend/tests/test_scoring_worker.py` line 418: `from backend.workers.scoring_worker import handler_scoring_worker`

**Test invocations affected**: Lines 242, 292, 349, 393, 446 (function calls using the old name)

---

## Current Terraform Handler Configuration (Before Fix)

**File**: `terraform/modules/lambda/main.tf`

### 1. AWS Lambda Function: `api`

**Resource**: `aws_lambda_function.api`
**Line**: ~46-56 (approximate based on bugfix.md citation)
**Current handler value**: `"main.handler"` ❌ (WRONG)
**Issue**: Code lives in `backend/main.py` with imports like `from backend.shared...` that require the package structure
**Fix needed**: Change to `handler = "backend.main.handler"` (Task 9.1)

### 2. AWS Lambda Function: `orquestador`

**Resource**: `aws_lambda_function.orquestador`
**Line**: ~119 (approximate)
**Current handler value**: `"main.handler"` ❌ (WRONG)
**Issue**: Same as `api` — shares the same `backend/main.py`
**Fix needed**: Change to `handler = "backend.main.handler"` (Task 9.2)

### 3. AWS Lambda Function: `scan_worker`

**Resource**: `aws_lambda_function.scan_worker`
**Line**: ~178 (approximate)
**Current handler value**: `"main.handler"` ❌ (WRONG)
**Issue**: Code only exposes `handler_scan_worker` function, not `handler` or `main.handler`
**Fix needed**: Change to `handler = "backend.workers.scan_worker.handler"` (Task 9.3) — requires renaming function to `handler` first (Task 8.1)

### 4. AWS Lambda Function: `scoring_worker`

**Resource**: `aws_lambda_function.scoring_worker`
**Line**: ~229 (approximate)
**Current handler value**: `"main.handler"` ❌ (WRONG)
**Issue**: Code only exposes `handler_scoring_worker` function, not `handler` or `main.handler`
**Fix needed**: Change to `handler = "backend.workers.scoring_worker.handler"` (Task 9.4) — requires renaming function to `handler` first (Task 8.2)

### 5. AWS Lambda Function: `notificador`

**Resource**: `aws_lambda_function.notificador`
**Current handler value**: `"backend.workers.notificador.handler.handler"` ✅ (CORRECT)
**Status**: NO CHANGES NEEDED (verified preservation requirement)

---

## Current IAM Policy Configuration (Before Fix)

**File**: `terraform/modules/iam/main.tf`

### 1. `api_policy` (aws_iam_role_policy for api_role)

**Line range**: ~45-90 (approximate)
**Current statements**: Multiple statements for DynamoDB, SQS, Bedrock
**Missing statement**: `lambda:InvokeFunction` on `job-search-api` function ❌
**Fix needed**: Add new statement granting `lambda:InvokeFunction` to `arn:aws:lambda:*:*:function/job-search-api` (Task 11.1)

### 2. `github_actions_policy` (aws_iam_role_policy for github_actions role)

**Line range**: ~421-436 (approximate)
**Current S3 statement Resource patterns**: 
- `"arn:aws:s3:::*-terraform-state-bucket"` ❌ (WRONG)
- `"arn:aws:s3:::*-terraform-state-bucket/*"` ❌ (WRONG)
- `"arn:aws:s3:::*-lambda-code-bucket"` ❌ (WRONG)
- `"arn:aws:s3:::*-lambda-code-bucket/*"` ❌ (WRONG)

**Issue**: These patterns never match the real bucket names:
- Actual Lambda code bucket: `job-search-lambda-code-5155151158151` (not ending in `-lambda-code-bucket`)
- Actual Terraform state bucket: `job-search-terraform-state-5543569870` (not ending in `-terraform-state-bucket`)

**Fix needed**: 
- (Task 12) Create `terraform/modules/iam/variables.tf` with `lambda_code_bucket` and `terraform_state_bucket` variables
- (Task 12) Update module invocation in `terraform/main.tf` to pass these variables
- (Task 14.1) Replace Resource patterns with `${var.lambda_code_bucket}` and `${var.terraform_state_bucket}` interpolations

---

## Terraform Variables Configuration (Before Fix)

**File**: `terraform/terraform.tfvars`

### Lambda Code Bucket Variable

**Current value**: `lambda_code_bucket = "job-search-lambda-code"` ❌ (OUTDATED)
**Real bucket name**: `job-search-lambda-code-5155151158151`
**Missing suffix**: `-5155151158151` (account ID-based suffix)
**Fix needed**: Update to `lambda_code_bucket = "job-search-lambda-code-5155151158151"` (Task 13.1)

### Terraform State Bucket Variable

**Current value**: `terraform_state_bucket = "job-search-terraform-state-5543569870"` ✅ (CORRECT)
**Status**: NO CHANGE NEEDED

---

## File Structure Verification

### IAM Module Currently Missing

**File**: `terraform/modules/iam/variables.tf`
**Current status**: DOES NOT EXIST ❌
**Contents needed**:
```hcl
variable "lambda_code_bucket" {
  description = "S3 bucket name where Lambda function .zip files are stored"
  type        = string
}

variable "terraform_state_bucket" {
  description = "S3 bucket name for Terraform state storage"
  type        = string
}
```
**To be created in**: Task 12.1

### Module Invocation Currently Not Passing Variables

**File**: `terraform/main.tf`
**Block**: `module "iam"`
**Current config**: No input variables passed to the `iam` module
**Fix needed**: Pass both variables (Task 12.2)

---

## Packaging Script Missing

**Location**: `scripts/build_lambda_packages.py`
**Current status**: DOES NOT EXIST ❌
**To be created in**: Task 10
**Purpose**: Build and upload `.zip` files for all 5 Lambdas to S3

---

## Pre-Deployment Status Summary

| Item | Status | References |
|------|--------|-----------|
| Handler name: scan_worker | ❌ WRONG (`handler_scan_worker`) | Terraform expects `handler` |
| Handler name: scoring_worker | ❌ WRONG (`handler_scoring_worker`) | Terraform expects `handler` |
| Handler config: api | ❌ WRONG (`main.handler`) | Should be `backend.main.handler` |
| Handler config: orquestador | ❌ WRONG (`main.handler`) | Should be `backend.main.handler` |
| Handler config: scan_worker | ❌ WRONG (`main.handler`) | Should be `backend.workers.scan_worker.handler` |
| Handler config: scoring_worker | ❌ WRONG (`main.handler`) | Should be `backend.workers.scoring_worker.handler` |
| Handler config: notificador | ✅ CORRECT | No changes needed |
| IAM: api_policy `lambda:InvokeFunction` | ❌ MISSING | Must add permission |
| IAM: github_actions_policy S3 patterns | ❌ BROKEN | Patterns don't match real bucket names |
| IAM: module iam/variables.tf | ❌ MISSING | Must create |
| Terraform.tfvars: lambda_code_bucket | ❌ OUTDATED | Missing account suffix `-5155151158151` |
| Terraform.tfvars: terraform_state_bucket | ✅ CORRECT | No changes needed |
| Scripts: build_lambda_packages.py | ❌ MISSING | Must create |
| Tests: test_scan_worker.py imports | ✅ WILL BE FIXED | In Task 8.3 |
| Tests: test_scoring_worker.py imports | ✅ WILL BE FIXED | In Task 8.4 |
| Pytest: total passed | 721 | Baseline for preservation check |
| Pytest: pre-existing failures | 16 | In test_board_api_client.py (logging issue, not related to this fix) |

---

## Verification Steps Completed

✅ Confirmed Python code structure with imports
✅ Confirmed current handler function names in both workers
✅ Confirmed Terraform Lambda configurations
✅ Confirmed IAM policy gaps
✅ Confirmed missing Terraform module variables
✅ Confirmed pytest baseline (721 passed, 16 pre-existing failures)
✅ Confirmed terraform validate success (no syntax errors in current state)

---

## Next Steps (After Task 7)

1. **Task 8**: Rename handler functions in Python code
2. **Task 8.3-8.4**: Update test imports and invocations
3. **Task 9**: Update Terraform Lambda handlers
4. **Task 10**: Create packaging script
5. **Task 11**: Add IAM permission for `api` self-invocation
6. **Task 12**: Create IAM module variables and update module invocation
7. **Task 13**: Fix terraform.tfvars bucket name
8. **Task 14**: Fix github_actions_policy S3 resource patterns
9. **Task 15**: Implement backend-deploy.yml workflow
10. **Task 17-19**: Final verification
