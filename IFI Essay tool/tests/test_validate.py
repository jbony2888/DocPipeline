"""
Unit tests for validation module.
Tests required field validation and approval gating.
"""

import pytest
from pipeline.validate import validate_record, can_approve_record
from pipeline.schema import SubmissionRecord


class TestCanApproveRecord:
    """Tests for can_approve_record() function."""
    
    def test_approve_with_all_required_fields(self):
        """Record with all required fields should be approvable."""
        record = {
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": 5
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is True
        assert len(missing) == 0
    
    def test_approve_with_grade_k(self):
        """Record with grade "K" should be approvable."""
        record = {
            "student_name": "Jane Smith",
            "school_name": "Roosevelt Elementary",
            "grade": "K"
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is True
        assert len(missing) == 0
    
    def test_cannot_approve_missing_student_name(self):
        """Record missing student_name should not be approvable."""
        record = {
            "student_name": None,
            "school_name": "Lincoln Elementary",
            "grade": 5
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "student_name" in missing
    
    def test_cannot_approve_empty_student_name(self):
        """Record with empty student_name should not be approvable."""
        record = {
            "student_name": "",
            "school_name": "Lincoln Elementary",
            "grade": 5
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "student_name" in missing
    
    def test_cannot_approve_whitespace_student_name(self):
        """Record with whitespace-only student_name should not be approvable."""
        record = {
            "student_name": "   ",
            "school_name": "Lincoln Elementary",
            "grade": 5
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "student_name" in missing
    
    def test_cannot_approve_missing_school_name(self):
        """Record missing school_name should not be approvable."""
        record = {
            "student_name": "John Doe",
            "school_name": None,
            "grade": 5
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "school_name" in missing
    
    def test_cannot_approve_empty_school_name(self):
        """Record with empty school_name should not be approvable."""
        record = {
            "student_name": "John Doe",
            "school_name": "",
            "grade": 5
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "school_name" in missing
    
    def test_cannot_approve_missing_grade(self):
        """Record missing grade should not be approvable."""
        record = {
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": None
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "grade" in missing
    
    def test_cannot_approve_empty_grade(self):
        """Record with empty grade should not be approvable."""
        record = {
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": ""
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "grade" in missing
    
    def test_cannot_approve_invalid_grade_too_low(self):
        """Record with grade < 1 should not be approvable."""
        record = {
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": 0
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "grade" in missing
    
    def test_cannot_approve_invalid_grade_too_high(self):
        """Record with grade > 12 should not be approvable."""
        record = {
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": 13
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "grade" in missing
    
    def test_cannot_approve_multiple_missing_fields(self):
        """Record missing multiple fields should list all missing fields."""
        record = {
            "student_name": None,
            "school_name": "",
            "grade": None
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is False
        assert "student_name" in missing
        assert "school_name" in missing
        assert "grade" in missing
        assert len(missing) == 3
    
    def test_approve_with_valid_grade_string(self):
        """Record with grade as valid string "5" should be approvable."""
        record = {
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": "5"
        }
        can_approve, missing = can_approve_record(record)
        assert can_approve is True
        assert len(missing) == 0


class TestValidateRecord:
    """Tests for validate_record() function."""
    
    def test_validate_with_all_required_fields(self):
        """Record with all required fields should flag MISSING_STUDENT_NAME, etc. correctly."""
        partial = {
            "submission_id": "test123",
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": 5,
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        # Should still need review (default state)
        assert record.needs_review is True
        # But should not have MISSING_* flags
        assert "MISSING_STUDENT_NAME" not in report["issues"]
        assert "MISSING_SCHOOL_NAME" not in report["issues"]
        assert "MISSING_GRADE" not in report["issues"]
    
    def test_validate_missing_student_name(self):
        """Record missing student_name should flag MISSING_STUDENT_NAME."""
        partial = {
            "submission_id": "test123",
            "student_name": None,
            "school_name": "Lincoln Elementary",
            "grade": 5,
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        assert record.needs_review is True
        assert "MISSING_STUDENT_NAME" in report["issues"]
        assert record.review_reason_codes == "MISSING_STUDENT_NAME;PENDING_REVIEW" or "MISSING_STUDENT_NAME" in record.review_reason_codes
    
    def test_validate_missing_school_name(self):
        """Record missing school_name should flag MISSING_SCHOOL_NAME."""
        partial = {
            "submission_id": "test123",
            "student_name": "John Doe",
            "school_name": None,
            "grade": 5,
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        assert record.needs_review is True
        assert "MISSING_SCHOOL_NAME" in report["issues"]
    
    def test_validate_missing_grade(self):
        """Record missing grade should flag MISSING_GRADE."""
        partial = {
            "submission_id": "test123",
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": None,
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        assert record.needs_review is True
        assert "MISSING_GRADE" in report["issues"]
    
    def test_validate_empty_student_name(self):
        """Record with empty student_name should flag MISSING_STUDENT_NAME."""
        partial = {
            "submission_id": "test123",
            "student_name": "",
            "school_name": "Lincoln Elementary",
            "grade": 5,
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        assert record.needs_review is True
        assert "MISSING_STUDENT_NAME" in report["issues"]
    
    def test_validate_whitespace_student_name(self):
        """Record with whitespace-only student_name should flag MISSING_STUDENT_NAME."""
        partial = {
            "submission_id": "test123",
            "student_name": "   ",
            "school_name": "Lincoln Elementary",
            "grade": 5,
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        assert record.needs_review is True
        assert "MISSING_STUDENT_NAME" in report["issues"]
    
    def test_validate_multiple_missing_fields(self):
        """Record missing multiple fields should flag all missing fields."""
        partial = {
            "submission_id": "test123",
            "student_name": None,
            "school_name": "",
            "grade": None,
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        assert record.needs_review is True
        assert "MISSING_STUDENT_NAME" in report["issues"]
        assert "MISSING_SCHOOL_NAME" in report["issues"]
        assert "MISSING_GRADE" in report["issues"]
    
    def test_validate_grade_k(self):
        """Record with grade "K" should be valid (stored as None in schema)."""
        partial = {
            "submission_id": "test123",
            "student_name": "Jane Smith",
            "school_name": "Roosevelt Elementary",
            "grade": "K",
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        # Should not flag MISSING_GRADE (K is valid)
        assert "MISSING_GRADE" not in report["issues"]
        # Grade "K" is stored as None in schema (since schema expects int)
        assert record.grade is None
    
    def test_validate_invalid_grade_too_low(self):
        """Record with grade < 1 should flag MISSING_GRADE."""
        partial = {
            "submission_id": "test123",
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": 0,
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        assert record.needs_review is True
        assert "MISSING_GRADE" in report["issues"]
    
    def test_validate_invalid_grade_too_high(self):
        """Record with grade > 12 should flag MISSING_GRADE."""
        partial = {
            "submission_id": "test123",
            "student_name": "John Doe",
            "school_name": "Lincoln Elementary",
            "grade": 13,
            "word_count": 100,
            "artifact_dir": "artifacts/test123"
        }
        record, report = validate_record(partial)
        
        assert record.needs_review is True
        assert "MISSING_GRADE" in report["issues"]

