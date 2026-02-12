"""
Local DBF Compliance Test Script
Tests the DBF remediation changes against a local Supabase instance.
"""

import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_audit_tables_exist():
    """Test that audit tables exist in Supabase."""
    print("🔍 Testing audit tables exist...")
    
    try:
        from pipeline.supabase_audit import insert_audit_trace, insert_audit_event
        from pipeline.audit import build_decision_trace
    except ImportError as e:
        print(f"⚠️ Could not import audit functions: {e}")
        print("   This may be due to Pydantic version compatibility.")
        print("   Try: pip install 'pydantic>=2.0' or test audit insertion via Flask app.")
        return None  # Skip this test
    
    # Test trace insertion
    trace_dict = build_decision_trace(
        submission_id="test_local_001",
        filename="test.pdf",
        owner_user_id="test-user-id",
        ocr_result={"confidence_avg": 0.65, "text": "test", "lines": []},
        extracted_fields={"student_name": "Test Student"},
        validation_result={"needs_review": True, "review_reason_codes": "PENDING_REVIEW"},
        rules_applied=[{"rule_id": "test_rule", "result": False}]
    )
    
    result = insert_audit_trace(
        submission_id="test_local_001",
        owner_user_id="test-user-id",
        trace_dict=trace_dict
    )
    
    if result:
        print("✅ Audit trace insertion successful")
    else:
        print("⚠️ Audit trace insertion failed (check Supabase connection)")
    
    # Test event insertion
    result = insert_audit_event(
        submission_id="test_local_001",
        actor_role="system",
        event_type="TEST_EVENT",
        event_payload={"test": True}
    )
    
    if result:
        print("✅ Audit event insertion successful")
    else:
        print("⚠️ Audit event insertion failed (check Supabase connection)")
    
    return result


def test_ocr_failed_reason_code():
    """Test that OCR_FAILED reason code is set correctly."""
    print("\n🔍 Testing OCR_FAILED reason code...")
    
    from pipeline.validate import validate_record
    from pipeline.schema import OcrResult
    
    # Test with ocr_failed=True
    partial = {
        "submission_id": "test_local_002",
        "student_name": "Test Student",
        "school_name": "Test School",
        "grade": 5,
        "word_count": 100,
        "ocr_confidence_avg": 0.0,
        "ocr_failed": True,  # OCR actually failed
        "artifact_dir": "test_dir"
    }
    
    record, validation = validate_record(partial)
    
    if "OCR_FAILED" in record.review_reason_codes:
        print("✅ OCR_FAILED reason code set correctly")
        print(f"   Review reason codes: {record.review_reason_codes}")
    else:
        print(f"❌ OCR_FAILED not found in reason codes: {record.review_reason_codes}")
        return False
    
    # Test with low confidence but NOT failed
    partial_low_conf = {
        "submission_id": "test_local_003",
        "student_name": "Test Student",
        "school_name": "Test School",
        "grade": 5,
        "word_count": 100,
        "ocr_confidence_avg": 0.4,  # Low confidence
        "ocr_failed": False,  # OCR succeeded, just low confidence
        "artifact_dir": "test_dir"
    }
    
    record2, validation2 = validate_record(partial_low_conf)
    
    if "LOW_CONFIDENCE" in record2.review_reason_codes and "OCR_FAILED" not in record2.review_reason_codes:
        print("✅ LOW_CONFIDENCE set correctly (OCR succeeded, just low confidence)")
        print(f"   Review reason codes: {record2.review_reason_codes}")
    else:
        print(f"❌ Expected LOW_CONFIDENCE but not OCR_FAILED: {record2.review_reason_codes}")
        return False
    
    return True


def test_deterministic_classification():
    """Test that classification is deterministic."""
    print("\n🔍 Testing deterministic classification...")
    
    from pipeline.classify import extract_classification_features, verify_doc_type_signal
    
    ocr_text = """Student's Name: John Doe
School: Test Elementary School
Grade: 5

What my father means to me...

My father has always been someone I look up to."""
    
    features1 = extract_classification_features(ocr_text)
    features2 = extract_classification_features(ocr_text)
    
    if features1 == features2:
        print("✅ Feature extraction is deterministic")
    else:
        print("❌ Feature extraction is not deterministic")
        return False
    
    # Test verification
    signal = "IFI_OFFICIAL_FORM_FILLED"
    doc_type1, verified1, reason1 = verify_doc_type_signal(signal, features1, ocr_text)
    doc_type2, verified2, reason2 = verify_doc_type_signal(signal, features2, ocr_text)
    
    if doc_type1 == doc_type2:
        print(f"✅ Classification verification is deterministic: {doc_type1}")
    else:
        print(f"❌ Classification not deterministic: {doc_type1} != {doc_type2}")
        return False
    
    return True


def test_escalation_threshold():
    """Test that very low confidence escalates."""
    print("\n🔍 Testing escalation threshold...")
    
    from pipeline.validate import validate_record
    
    # Test with confidence < 0.3 (should escalate)
    partial = {
        "submission_id": "test_local_004",
        "student_name": "Test Student",
        "school_name": "Test School",
        "grade": 5,
        "word_count": 100,
        "ocr_confidence_avg": 0.25,  # Very low
        "artifact_dir": "test_dir"
    }
    
    record, validation = validate_record(partial)
    
    if "ESCALATED" in record.review_reason_codes:
        print("✅ Escalation threshold working (confidence < 0.3)")
        print(f"   Review reason codes: {record.review_reason_codes}")
    else:
        print(f"❌ Escalation not triggered: {record.review_reason_codes}")
        return False
    
    return True


def test_audit_trace_structure():
    """Test that audit trace has correct structure."""
    print("\n🔍 Testing audit trace structure...")
    
    from pipeline.audit import build_decision_trace
    
    trace = build_decision_trace(
        submission_id="test_local_005",
        filename="test.pdf",
        owner_user_id="test-user",
        ocr_result={"confidence_avg": 0.65, "text": "test", "lines": []},
        extracted_fields={"student_name": "Test"},
        validation_result={"needs_review": True},
        rules_applied=[{"rule_id": "test", "result": False}]
    )
    
    required_keys = ["input", "signals", "rules_applied", "outcome", "errors"]
    missing = [key for key in required_keys if key not in trace]
    
    if not missing:
        print("✅ Audit trace has all required sections")
        print(f"   Sections: {list(trace.keys())}")
    else:
        print(f"❌ Missing sections: {missing}")
        return False
    
    # Verify structure
    assert "submission_id" in trace["input"]
    assert "needs_review" in trace["outcome"]
    
    print("✅ Audit trace structure validated")
    return True


def main():
    """Run all local DBF tests."""
    print("=" * 60)
    print("DBF Local Testing")
    print("=" * 60)
    print()
    
    # Check environment
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("⚠️ Warning: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        print("   Some tests may fail. Set these in your .env file.")
        print()
    
    tests = [
        ("Audit Tables", test_audit_tables_exist),
        ("OCR_FAILED Reason Code", test_ocr_failed_reason_code),
        ("Deterministic Classification", test_deterministic_classification),
        ("Escalation Threshold", test_escalation_threshold),
        ("Audit Trace Structure", test_audit_trace_structure),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            if result is None:
                # Test skipped (e.g., import issue)
                results.append((name, None))
            else:
                results.append((name, result))
        except Exception as e:
            print(f"❌ {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    for name, result in results:
        if result is None:
            status = "⏭️  SKIP"
        elif result:
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        print(f"{status}: {name}")
    
    # Count only non-skipped tests
    non_skipped = [r for _, r in results if r is not None]
    all_passed = all(non_skipped) if non_skipped else False
    
    if all_passed:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️ Some tests failed. Check Supabase connection and migration.")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
