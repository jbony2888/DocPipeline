"""
Integration tests for approval gating.
Tests that records cannot be approved without required fields.
"""

import pytest
import sqlite3
import os
import tempfile
from pathlib import Path
from pipeline.database import init_database, save_record, get_record_by_id, update_record
from pipeline.validate import can_approve_record
from pipeline.schema import SubmissionRecord


@pytest.fixture
def temp_db(monkeypatch):
    """Create a temporary database for testing."""
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_submissions.db")
    
    # Override DB_PATH using monkeypatch
    import pipeline.database as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    
    # Initialize database
    init_database()
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)
    os.rmdir(temp_dir)


class TestApprovalGating:
    """Integration tests for approval gating."""
    
    def test_cannot_approve_record_with_missing_grade(self, temp_db):
        """Attempting to approve a record with missing grade should fail validation."""
        # Create a record with missing grade
        record = SubmissionRecord(
            submission_id="test123",
            student_name="John Doe",
            school_name="Lincoln Elementary",
            grade=None,  # Missing grade
            word_count=100,
            needs_review=True,
            review_reason_codes="MISSING_GRADE",
            artifact_dir="artifacts/test123"
        )
        
        # Save to database
        save_record(record, filename="test.pdf")
        
        # Check if record can be approved
        db_record = get_record_by_id("test123")
        can_approve, missing_fields = can_approve_record(db_record)
        
        assert can_approve is False
        assert "grade" in missing_fields
        
        # Attempt to approve (should fail validation check)
        # In real app, this would be blocked by UI, but we test the validation logic
        assert can_approve is False, "Record should not be approvable without grade"
    
    def test_can_approve_record_with_all_fields(self, temp_db):
        """Record with all required fields should be approvable."""
        # Create a complete record
        record = SubmissionRecord(
            submission_id="test456",
            student_name="Jane Smith",
            school_name="Roosevelt Elementary",
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test456"
        )
        
        # Save to database
        save_record(record, filename="test.pdf")
        
        # Check if record can be approved
        db_record = get_record_by_id("test456")
        can_approve, missing_fields = can_approve_record(db_record)
        
        assert can_approve is True
        assert len(missing_fields) == 0
    
    def test_cannot_approve_record_with_missing_student_name(self, temp_db):
        """Record with missing student_name should not be approvable."""
        record = SubmissionRecord(
            submission_id="test789",
            student_name=None,  # Missing
            school_name="Lincoln Elementary",
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="MISSING_STUDENT_NAME",
            artifact_dir="artifacts/test789"
        )
        
        import pipeline.database as db_module
        db_module.DB_PATH = temp_db
        save_record(record, filename="test.pdf")
        
        db_record = get_record_by_id("test789")
        can_approve, missing_fields = can_approve_record(db_record)
        
        assert can_approve is False
        assert "student_name" in missing_fields
    
    def test_cannot_approve_record_with_missing_school_name(self, temp_db):
        """Record with missing school_name should not be approvable."""
        record = SubmissionRecord(
            submission_id="test101",
            student_name="John Doe",
            school_name=None,  # Missing
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="MISSING_SCHOOL_NAME",
            artifact_dir="artifacts/test101"
        )
        
        import pipeline.database as db_module
        db_module.DB_PATH = temp_db
        save_record(record, filename="test.pdf")
        
        db_record = get_record_by_id("test101")
        can_approve, missing_fields = can_approve_record(db_record)
        
        assert can_approve is False
        assert "school_name" in missing_fields
    
    def test_approval_after_editing_missing_field(self, temp_db):
        """After editing to add missing field, record should become approvable."""
        # Create record with missing grade
        record = SubmissionRecord(
            submission_id="test202",
            student_name="John Doe",
            school_name="Lincoln Elementary",
            grade=None,  # Missing
            word_count=100,
            needs_review=True,
            review_reason_codes="MISSING_GRADE",
            artifact_dir="artifacts/test202"
        )
        
        import pipeline.database as db_module
        db_module.DB_PATH = temp_db
        save_record(record, filename="test.pdf")
        
        # Initially not approvable
        db_record = get_record_by_id("test202")
        can_approve, missing_fields = can_approve_record(db_record)
        assert can_approve is False
        assert "grade" in missing_fields
        
        # Update record to add grade
        update_record("test202", {"grade": 5})
        
        # Now should be approvable
        db_record_updated = get_record_by_id("test202")
        can_approve_after, missing_after = can_approve_record(db_record_updated)
        assert can_approve_after is True
        assert len(missing_after) == 0

