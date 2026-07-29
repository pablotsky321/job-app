# Task 7: Preservation Baseline Report

**Date**: Captured at session start, before any code or Terraform changes
**Purpose**: Establish baseline metrics for pytest and terraform plan to verify that fixes don't introduce regressions

---

## Pytest Baseline (Current State — Unfixed)

**Command executed**: `python -m pytest backend --tb=short -v`

**Summary**:
- **Passed**: 721
- **Failed**: 16 (pre-existing, documented below)
- **Warnings**: 197
- **Total execution time**: 11.96s

### Pre-Existing Failures (NOT Related to This Fix)

All 16 failures are in `backend/tests/test_board_api_client.py` and stem from a logging configuration issue, not from handler naming or packaging:

```
FAILED backend\tests\test_board_api_client.py::TestGreenhouseExtraction::test_successful_extraction
FAILED backend\tests\test_board_api_client.py::TestGreenhouseExtraction::test_excludes_entries_without_url
FAILED backend\tests\test_board_api_client.py::TestGreenhouseExtraction::test_modalidad_always_sin_dato
FAILED backend\tests\test_board_api_client.py::TestGreenhouseExtraction::test_empty_jobs_list
FAILED backend\tests\test_board_api_client.py::TestGreenhouseExtraction::test_uses_correct_endpoint
FAILED backend\tests\test_board_api_client.py::TestLeverExtraction::test_successful_extraction
FAILED backend\tests\test_board_api_client.py::TestLeverExtraction::test_excludes_entries_without_url
FAILED backend\tests\test_board_api_client.py::TestLeverExtraction::test_uses_correct_endpoint
FAILED backend\tests\test_board_api_client.py::TestHttpErrorHandling::test_http_404
FAILED backend\tests\test_board_api_client.py::TestHttpErrorHandling::test_http_500
FAILED backend\tests\test_board_api_client.py::TestHttpErrorHandling::test_timeout
FAILED backend\tests\test_board_api_client.py::TestHttpErrorHandling::test_connection_error
FAILED backend\tests\test_board_api_client.py::TestInvalidJson::test_invalid_json_response
FAILED backend\tests\test_board_api_client.py::TestInvalidJson::test_unexpected_json_structure
FAILED backend\tests\test_board_api_client.py::TestMissingBoardToken::test_no_board_token
FAILED backend\tests\test_board_api_client.py::TestMissingBoardToken::test_empty_board_token
```

**Error type**: `TypeError: backend.shared.logging_config.LoggerWithContext._log() got multiple values for keyword argument 'extra'`

**Exclusion rationale**: These failures are pre-existing and unrelated to the 4 bloqueadores being fixed in this spec (handler naming, handler/zip consistency, packaging pipeline, IAM permissions). They will NOT be modified by any tasks in this spec. They are documented here to establish a baseline for comparison after the fixes are applied.

### Test Coverage by Module

The 721 passed tests cover:
- `test_auth.py`: 28 tests (all PASSED)
- `test_auth_dependency.py`: 10 tests (all PASSED)
- `test_board_api_client.py`: 19 tests (3 PASSED, 16 FAILED — pre-existing)
- `test_cascada_descubrimiento.py`: 41 tests (all PASSED)
- `test_companies.py`: 39 tests (all PASSED)
- `test_db.py`: 17 tests (all PASSED)
- `test_extraction.py`: 23 tests (all PASSED)
- `test_get_scan_job.py`: 12 tests (all PASSED)
- `test_health.py`: 5 tests (all PASSED)
- `test_html_cleaner.py`: [multiple tests, all PASSED]
- `test_logging_config.py`: [multiple tests, all PASSED]
- `test_scan_worker.py`: [multiple tests, all PASSED — includes imports of current `handler_scan_worker` function name]
- `test_scoring_worker.py`: [multiple tests, all PASSED — includes imports of current `handler_scoring_worker` function name]
- And other test modules

---

## Terraform Baseline (Current State — Unfixed)

**Command executed**: `terraform plan` (from `terraform/` directory)

**State**:
- `terraform validate`: ✅ Success (configuration is valid)

### Plan Summary

```
Terraform will perform the following actions:

Plan: 65 to add, 15 to change, 0 to destroy
```

### Current Lambda Handler Configurations (Before Fix)

**From Terraform plan output — will be changed by Task 9**:

All 5 Lambda functions are currently created as new resources (indicated by `+` in the plan):

- `module.lambda.aws_lambda_function.api` — **NOT YET CREATED**
  - Current config (to be fixed): `handler = "main.handler"` (per bugfix.md, line ~48-53)
  - Issue: Mismatch with `backend/main.py` which requires `backend.` package prefix

- `module.lambda.aws_lambda_function.orquestador` — **NOT YET CREATED**
  - Current config (to be fixed): `handler = "main.handler"` (per bugfix.md, line ~119)
  - Issue: Same as `api` — code lives in `backend/main.py`

- `module.lambda.aws_lambda_function.scan_worker` — **NOT YET CREATED**
  - Current config (to be fixed): `handler = "main.handler"` (per bugfix.md, line ~178)
  - Issue: Code exposes `handler_scan_worker`, not `handler`

- `module.lambda.aws_lambda_function.scoring_worker` — **NOT YET CREATED**
  - Current config (to be fixed): `handler = "main.handler"` (per bugfix.md, line ~229)
  - Issue: Code exposes `handler_scoring_worker`, not `handler`

- `module.lambda.aws_lambda_function.notificador` — **NOT YET CREATED** (will NOT be touched)
  - Current config (correct, no fix needed): `handler = "backend.workers.notificador.handler.handler"`
  - Status: Already correct, no changes in this spec

### IAM Policy Baseline (Before Fix)

**From terraform plan output**:

`module.iam.aws_iam_role_policy.api_policy`:
- Currently created as new resource
- Missing statement with `lambda:InvokeFunction` (per bugfix.md section 1.6)
- Will be fixed by Task 11

`module.iam.aws_iam_role_policy.github_actions_policy`:
- Currently created as new resource
- S3 statement uses broken patterns: `*-terraform-state-bucket` and `*-lambda-code-bucket` (per bugfix.md sections 2.8, 2.8.1)
- Will be fixed by Task 14

### Terraform Module Structure (Unchanged)

- `terraform/modules/lambda/main.tf`: Contains 5 Lambda function definitions
- `terraform/modules/iam/main.tf`: Contains IAM role and policy definitions
- **Note**: `terraform/modules/iam/variables.tf` does NOT exist yet (will be created in Task 12)

---

## Verification Checklist

### For Pytest After Fix (Task 17.3)

After applying all fixes (Tasks 8-14), the pytest count MUST remain:
- ✅ Passed: 721 (exact match required)
- ✅ Failed: 16 (same pre-existing failures only)
- ✅ Warnings: ~197 (approx, may vary slightly due to deprecation warnings)

### For Terraform After Fix (Task 17.2)

After applying all fixes (Tasks 9, 12, 14), the terraform plan MUST show:
- ✅ Only 4 handler attribute changes in `module.lambda` (api, orquestador, scan_worker, scoring_worker)
- ✅ No changes to `notificador` handler
- ✅ No other changes to Lambda function definitions
- ✅ New IAM variables in `module.iam` (lambda_code_bucket, terraform_state_bucket)
- ✅ S3 statement Resource changes in `github_actions_policy` (only)
- ✅ No new grants to roles other than `api_role` (for `lambda:InvokeFunction`) and updates to `github_actions_policy` Resource ARNs

---

## Notes

1. **No AWS credential requirements**: This baseline was captured purely through local validation (`terraform validate`, `pytest`). No AWS API calls were made.

2. **Terraform state**: The terraform plan shows 65 resources to add and 15 to update on a fresh apply (initial deployment scenario). This is the baseline for the unfixed state.

3. **Hypothesis tests**: The pytest output includes warnings related to Hypothesis (PBT library). These are expected and not related to this fix.

4. **Python deprecation warnings**: Several `datetime.utcnow()` deprecation warnings appear. These are pre-existing and will not be fixed in this spec.

5. **Test exclusion**: The 16 pre-existing failures in `test_board_api_client.py` will be excluded from "after-fix" regression verification. Any new failures introduced by this spec's changes would be caught and reported as regressions.

---

## References

- **Bugfix Requirements**: `.kiro/specs/backend-deploy-blockers-fix/bugfix.md` (Bug Analysis section)
- **Design Document**: `.kiro/specs/backend-deploy-blockers-fix/design.md` (Preservation Requirements, Properties 1-7)
- **Implementation Plan**: `.kiro/specs/backend-deploy-blockers-fix/tasks.md` (Task 7, Task 17 verification)
