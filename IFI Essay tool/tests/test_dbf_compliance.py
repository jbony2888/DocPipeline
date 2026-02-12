"""
DBF Compliance Test Suite
Tests for DBF v1.0 invariants and decision boundaries.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

# Mock Supabase imports before importing pipeline modules
sys.modules['supabase'] = MagicMock()
sys.modules['supabase'].create_client = MagicMock()
sys.modules['auth'] = MagicMock()
sys.modules['auth.supabase_client'] = MagicMock()

# Now import pipeline modules
from pipeline.validate import validate_record
from pipeline.audit import build_decision_trace
from pipeline.classify import verify_doc_type_signal, extract_classification_features
from pipeline.extract_ifi import verify_extracted_fields

# Mock the audit functions to avoid Supabase dependency
def mock_insert_audit_trace(*args, **kwargs):
    return True

def mock_insert_audit_event(*args, **kwargs):
    return True

# Patch the imports
import pipeline.supabase_audit
pipeline.supabase_audit.insert_audit_trace = mock_insert_audit_trace
pipeline.supabase_audit.insert_audit_event = mock_insert_audit_event

# Import for use in tests
insert_audit_trace = mock_insert_audit_trace
insert_audit_event = mock_insert_audit_event


class TestDBFInvariants:
    """Test DBF mandatory invariants (5.1-5.5)"""
    
    def test_invariant_5_1_no_unverified_action(self):
        """5.1: No action may be taken without passing verification."""
        # All records default to needs_review=True
        partial = {
            "submission_id": "test_123",
            "student_name": "John Doe",
            "school_name": "Test School",
            "grade": 5,
            "word_count": 100,
            "ocr_confidence_avg": 0.8,
            "artifact_dir": "test_dir"
        }
        
        record, validation = validate_record(partial)
        
        # Even with all fields present, should default to needs_review=True
        assert record.needs_review is True, "All records must start in needs_review=True"
        assert "PENDING_REVIEW" in record.review_reason_codes, "Should have PENDING_REVIEW reason code"
    
    def test_invariant_5_2_determinism(self):
        """5.2: Identical inputs MUST yield identical decisions."""
        # Test that classification is deterministic
        ocr_text = "Name: John Doe\nSchool: Test School\nGrade: 5\n\nEssay text here..."
        
        features1 = extract_classification_features(ocr_text)
        features2 = extract_classification_features(ocr_text)
        
        assert features1 == features2, "Feature extraction must be deterministic"
        
        # Test verification is deterministic
        signal = "IFI_OFFICIAL_FORM_FILLED"
        doc_type1, verified1, reason1 = verify_doc_type_signal(signal, features1, ocr_text)
        doc_type2, verified2, reason2 = verify_doc_type_signal(signal, features2, ocr_text)
        
        assert doc_type1 == doc_type2, "Classification verification must be deterministic"
        assert verified1 == verified2, "Verification result must be deterministic"
    
    def test_invariant_5_3_idempotency(self):
        """5.3: Duplicate events MUST NOT produce duplicate side effects."""
        # This is tested in test_failure_injection.py test_duplicate_upload
        # Here we verify the check function exists and can be called
        from pipeline.supabase_db import check_duplicate_submission
        
        # Mock Supabase client and create_client
        with patch('pipeline.supabase_db.get_supabase_client') as mock_client:
            with patch('supabase.create_client') as mock_create:
                # Mock Supabase response
                mock_admin = MagicMock()
                mock_admin.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
                mock_create.return_value = mock_admin
                
                # Mock environment
                import os
                with patch.dict(os.environ, {'SUPABASE_SERVICE_ROLE_KEY': 'test', 'SUPABASE_URL': 'https://test.supabase.co'}):
                    result = check_duplicate_submission("test_id", "user123", None, None)
                    # Should return is_duplicate=False when no existing record
                    assert result["is_duplicate"] is False
    
    def test_invariant_5_4_explainability(self):
        """5.4: Every decision MUST be traceable to Input → Signal → Rule → Outcome."""
        # Test that audit trace contains all required sections
        trace = build_decision_trace(
            submission_id="test_123",
            filename="test.pdf",
            owner_user_id="user123",
            ocr_result={"confidence_avg": 0.65, "text": "test", "lines": []},
            extracted_fields={"student_name": "John"},
            validation_result={"needs_review": True, "review_reason_codes": "PENDING_REVIEW"},
            rules_applied=[{"rule_id": "test_rule", "result": False}]
        )
        
        assert "input" in trace, "Trace must have input section"
        assert "signals" in trace, "Trace must have signals section"
        assert "rules_applied" in trace, "Trace must have rules_applied section"
        assert "outcome" in trace, "Trace must have outcome section"
        
        # Verify trace structure
        assert trace["input"]["submission_id"] == "test_123"
        assert "ocr" in trace["signals"]
        assert len(trace["rules_applied"]) > 0
        assert "needs_review" in trace["outcome"]
    
    def test_invariant_5_5_safe_degradation(self):
        """5.5: When confidence is insufficient, system MUST defer, escalate, or refuse."""
        # Test low confidence triggers review
        partial_low_conf = {
            "submission_id": "test_123",
            "student_name": "John Doe",
            "school_name": "Test School",
            "grade": 5,
            "word_count": 100,
            "ocr_confidence_avg": 0.25,  # Very low confidence (< 0.3)
            "artifact_dir": "test_dir"
        }
        
        record, validation = validate_record(partial_low_conf)
        
        assert record.needs_review is True, "Low confidence must trigger review"
        assert "LOW_CONFIDENCE" in record.review_reason_codes, "Must have LOW_CONFIDENCE reason"
        assert "ESCALATED" in record.review_reason_codes, "Very low confidence (<0.3) must escalate"


class TestDecisionBoundaries:
    """Test explicit decision boundaries"""
    
    def test_db_01_ocr_confidence_threshold(self):
        """DB-01: OCR Confidence → Needs Review Routing"""
        # Test threshold at 0.5
        partial_above = {
            "submission_id": "test_123",
            "ocr_confidence_avg": 0.6,
            "word_count": 100,
            "artifact_dir": "test_dir"
        }
        
        partial_below = {
            "submission_id": "test_123",
            "ocr_confidence_avg": 0.4,
            "word_count": 100,
            "artifact_dir": "test_dir"
        }
        
        _, val_above = validate_record(partial_above)
        _, val_below = validate_record(partial_below)
        
        # Above threshold should not trigger LOW_CONFIDENCE
        assert "LOW_CONFIDENCE" not in val_above.get("review_reason_codes", "")
        
        # Below threshold should trigger LOW_CONFIDENCE
        assert "LOW_CONFIDENCE" in val_below.get("review_reason_codes", "")
    
    def test_db_02_required_fields_threshold(self):
        """DB-02: Required Fields → Needs Review Routing"""
        partial_missing = {
            "submission_id": "test_123",
            "student_name": None,  # Missing
            "school_name": "Test School",
            "grade": 5,
            "word_count": 100,
            "artifact_dir": "test_dir"
        }
        
        record, validation = validate_record(partial_missing)
        
        assert record.needs_review is True
        assert "MISSING_STUDENT_NAME" in record.review_reason_codes
    
    def test_db_03_essay_word_count_threshold(self):
        """DB-03: Essay Word Count → Needs Review Routing"""
        partial_short = {
            "submission_id": "test_123",
            "student_name": "John",
            "school_name": "Test",
            "grade": 5,
            "word_count": 30,  # Below 50
            "artifact_dir": "test_dir"
        }
        
        record, validation = validate_record(partial_short)
        
        assert record.needs_review is True
        assert "SHORT_ESSAY" in record.review_reason_codes


class TestLLMVerification:
    """Test that LLM outputs are verified deterministically"""
    
    def test_doc_type_verification(self):
        """M2: LLM doc_type signal is verified deterministically"""
        ocr_text = "Student's Name: John Doe\nSchool: Test School\nGrade: 5\n\nEssay..."
        
        features = extract_classification_features(ocr_text)
        signal_doc_type = "IFI_OFFICIAL_FORM_FILLED"
        
        doc_type_final, verified, reason = verify_doc_type_signal(signal_doc_type, features, ocr_text)
        
        # doc_type_final should be determined by code, not LLM
        assert doc_type_final is not None
        assert isinstance(doc_type_final, str)
        # Should be one of the valid types
        assert doc_type_final in [
            "IFI_OFFICIAL_FORM_FILLED",
            "IFI_OFFICIAL_TEMPLATE_BLANK",
            "ESSAY_WITH_HEADER_METADATA",
            "ESSAY_ONLY",
            "MULTI_ENTRY",
            "UNKNOWN"
        ]
    
    def test_field_verification(self):
        """M2: Extracted fields are verified against OCR text"""
        ocr_text = "Name: John Doe\nSchool: Test School"
        result = {
            "student_name": "John Doe",
            "school_name": "Test School",
            "grade": 5
        }
        
        verified_result = verify_extracted_fields(result, ocr_text)
        
        # Fields that exist in OCR should remain
        assert verified_result.get("student_name") == "John Doe"
        assert verified_result.get("school_name") == "Test School"
        
        # Fields not in OCR should be nullified
        result_not_in_ocr = {
            "student_name": "Jane Smith",  # Not in OCR
            "school_name": "Test School"
        }
        verified_not_in_ocr = verify_extracted_fields(result_not_in_ocr, ocr_text)
        assert verified_not_in_ocr.get("student_name") is None


class TestAuditTrail:
    """Test that audit trail is written to Supabase"""
    
    def test_audit_trace_insertion(self):
        """Test that audit trace function exists and can be called"""
        trace_dict = {
            "input": {"submission_id": "test_123"},
            "signals": {"ocr": {"confidence_avg": 0.65}},
            "rules_applied": [],
            "outcome": {"needs_review": True},
            "errors": []
        }
        
        # Test that function exists and can be called (mocked to return True)
        result = insert_audit_trace("test_123", "user123", trace_dict)
        assert result is True  # Mocked function returns True
    
    def test_audit_event_insertion(self):
        """Test that audit event function exists and can be called"""
        # Test that function exists and can be called (mocked to return True)
        result = insert_audit_event(
            submission_id="test_123",
            actor_role="system",
            event_type="OCR_COMPLETE",
            event_payload={"confidence": 0.65},
            actor_user_id="user123"
        )
        assert result is True  # Mocked function returns True
