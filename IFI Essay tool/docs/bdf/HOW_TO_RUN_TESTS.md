# How to Run DBF Compliance Tests

## Quick Start

**IMPORTANT:** You must be in the `IFI Essay tool` directory to run tests.

```bash
# Navigate to the correct directory first
cd "IFI Essay tool"

# Then run the tests
pytest tests/test_dbf_compliance.py tests/test_failure_injection.py -v
```

If you're already in the root `DocPipeline` directory:
```bash
cd "IFI Essay tool" && pytest tests/test_dbf_compliance.py tests/test_failure_injection.py -v
```

## Prerequisites

### 1. Install Dependencies

```bash
# Install pytest and test dependencies
pip install pytest pytest-mock

# Or use the existing requirements.txt (pytest is already included)
pip install -r requirements.txt
```

### 2. Set Environment Variables (Optional)

Tests use mocks for Supabase, so database connection is not required. However, if you want to run integration tests:

```bash
export SUPABASE_URL=your_supabase_url
export SUPABASE_SERVICE_ROLE_KEY=your_service_key
export SUPABASE_ANON_KEY=your_anon_key
```

For unit tests only, you can use dummy values:
```bash
export SUPABASE_URL=https://test.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=test-service-key
export SUPABASE_ANON_KEY=test-anon-key
```

## Running Tests

**⚠️ IMPORTANT:** You must run pytest from the `IFI Essay tool` directory, not from the root `DocPipeline` directory.

### Run All DBF Tests

```bash
# From the IFI Essay tool directory
cd "IFI Essay tool"
pytest tests/test_dbf_compliance.py tests/test_failure_injection.py -v

# Or from root directory, specify the path:
pytest "IFI Essay tool/tests/test_dbf_compliance.py" "IFI Essay tool/tests/test_failure_injection.py" -v
```

### Run Specific Test Files

```bash
# Compliance tests only
pytest tests/test_dbf_compliance.py -v

# Failure injection tests only
pytest tests/test_failure_injection.py -v
```

### Run Specific Test Classes

```bash
# Test invariants only
pytest tests/test_dbf_compliance.py::TestDBFInvariants -v

# Test decision boundaries only
pytest tests/test_dbf_compliance.py::TestDecisionBoundaries -v

# Test LLM verification
pytest tests/test_dbf_compliance.py::TestLLMVerification -v

# Test audit trail
pytest tests/test_dbf_compliance.py::TestAuditTrail -v

# Test failure injection scenarios
pytest tests/test_failure_injection.py::TestFailureInjection -v

# Test safe degradation
pytest tests/test_failure_injection.py::TestSafeDegradation -v

# Test idempotency
pytest tests/test_failure_injection.py::TestIdempotency -v
```

### Run Specific Tests

```bash
# Test a specific invariant
pytest tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_2_determinism -v

# Test a specific failure scenario
pytest tests/test_failure_injection.py::TestFailureInjection::test_fi_01_ocr_provider_outage -v
```

## Using the Test Runner Script

The project includes a test runner script:

```bash
# Make executable (if needed)
chmod +x run_tests.sh

# Run all tests
./run_tests.sh

# Or run DBF tests specifically
pytest tests/test_dbf_compliance.py tests/test_failure_injection.py -v --tb=short
```

## Test Output

### Verbose Output (-v)

Shows each test as it runs:
```
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_1_no_unverified_action PASSED
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_2_determinism PASSED
...
```

### With Coverage

```bash
pip install pytest-cov
pytest tests/test_dbf_compliance.py tests/test_failure_injection.py --cov=pipeline --cov-report=html
```

This generates an HTML coverage report in `htmlcov/index.html`.

## Troubleshooting

### Import Errors

If you get import errors, make sure you're in the correct directory:

```bash
cd "IFI Essay tool"
pytest tests/test_dbf_compliance.py -v
```

### Missing Dependencies

```bash
pip install pytest pytest-mock pytest-cov
```

### Mock Issues

Tests use `unittest.mock` to mock Supabase calls. If mocks aren't working, check that `pytest-mock` is installed:

```bash
pip install pytest-mock
```

## Expected Test Results

All 21 tests should pass:

```
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_1_no_unverified_action PASSED
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_2_determinism PASSED
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_3_idempotency PASSED
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_4_explainability PASSED
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_5_safe_degradation PASSED
tests/test_dbf_compliance.py::TestDecisionBoundaries::test_db_01_ocr_confidence_threshold PASSED
tests/test_dbf_compliance.py::TestDecisionBoundaries::test_db_02_required_fields_threshold PASSED
tests/test_dbf_compliance.py::TestDecisionBoundaries::test_db_03_essay_word_count_threshold PASSED
tests/test_dbf_compliance.py::TestLLMVerification::test_doc_type_verification PASSED
tests/test_dbf_compliance.py::TestLLMVerification::test_field_verification PASSED
tests/test_dbf_compliance.py::TestAuditTrail::test_audit_trace_insertion PASSED
tests/test_dbf_compliance.py::TestAuditTrail::test_audit_event_insertion PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_01_ocr_provider_outage PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_02_ocr_confidence_near_threshold PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_03_missing_required_fields PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_04_duplicate_submission PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_05_audit_write_failure PASSED
tests/test_failure_injection.py::TestSafeDegradation::test_ocr_error_returns_low_confidence_and_failed_flag PASSED
tests/test_failure_injection.py::TestSafeDegradation::test_llm_failure_falls_back PASSED
tests/test_failure_injection.py::TestSafeDegradation::test_very_low_confidence_escalates PASSED
tests/test_failure_injection.py::TestIdempotency::test_duplicate_upload_skips PASSED

============================== 21 passed in 0.10s ==============================
```

## Common Issues

### Tests Not Found

If you see `ERROR: file or directory not found: tests/test_dbf_compliance.py`:

**Problem:** You're running pytest from the wrong directory.

**Solution:** 
```bash
# Make sure you're in the IFI Essay tool directory
cd "IFI Essay tool"
pytest tests/test_dbf_compliance.py tests/test_failure_injection.py -v
```

### Import Errors

If you see import errors related to `supabase` or `fitz`:

**Problem:** Tests mock these dependencies, but if imports fail during module loading, you may need to install them:
```bash
pip install supabase PyMuPDF
```

However, tests should work without these installed since they're mocked.

```
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_1_no_unverified_action PASSED
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_2_determinism PASSED
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_3_idempotency PASSED
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_4_explainability PASSED
tests/test_dbf_compliance.py::TestDBFInvariants::test_invariant_5_5_safe_degradation PASSED
tests/test_dbf_compliance.py::TestDecisionBoundaries::test_db_01_ocr_confidence_threshold PASSED
tests/test_dbf_compliance.py::TestDecisionBoundaries::test_db_02_required_fields_threshold PASSED
tests/test_dbf_compliance.py::TestDecisionBoundaries::test_db_03_essay_word_count_threshold PASSED
tests/test_dbf_compliance.py::TestLLMVerification::test_doc_type_verification PASSED
tests/test_dbf_compliance.py::TestLLMVerification::test_field_verification PASSED
tests/test_dbf_compliance.py::TestAuditTrail::test_audit_trace_insertion PASSED
tests/test_dbf_compliance.py::TestAuditTrail::test_audit_event_insertion PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_01_ocr_provider_outage PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_02_ocr_confidence_near_threshold PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_03_missing_required_fields PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_04_duplicate_submission PASSED
tests/test_failure_injection.py::TestFailureInjection::test_fi_05_audit_write_failure PASSED
tests/test_failure_injection.py::TestSafeDegradation::test_ocr_error_returns_low_confidence PASSED
tests/test_failure_injection.py::TestSafeDegradation::test_llm_failure_falls_back PASSED
tests/test_failure_injection.py::TestSafeDegradation::test_very_low_confidence_escalates PASSED
tests/test_failure_injection.py::TestIdempotency::test_duplicate_upload_skips PASSED
```

## CI/CD Integration

To run in CI/CD:

```yaml
# Example GitHub Actions
- name: Run DBF Compliance Tests
  run: |
    cd "IFI Essay tool"
    pip install pytest pytest-mock
    pytest tests/test_dbf_compliance.py tests/test_failure_injection.py -v
```
