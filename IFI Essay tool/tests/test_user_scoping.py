"""
Unit tests for user scoping in database operations.
Tests that records are properly filtered by owner_user_id.
"""

import pytest
import sqlite3
import os
import tempfile
from pathlib import Path
from pipeline.database import (
    init_database, save_record, get_records, get_record_by_id,
    update_record, delete_record, get_stats
)
from pipeline.schema import SubmissionRecord


@pytest.fixture
def temp_db(monkeypatch):
    """Create a temporary database for testing."""
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


class TestUserScoping:
    """Tests for user-scoped database operations."""
    
    def test_save_record_with_owner_user_id(self, temp_db):
        """Records should be saved with owner_user_id."""
        user_id_1 = "user-123"
        
        record = SubmissionRecord(
            submission_id="test001",
            student_name="John Doe",
            school_name="Lincoln Elementary",
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test001"
        )
        
        result = save_record(record, filename="test.pdf", owner_user_id=user_id_1)
        assert result is True
        
        # Verify record was saved with owner_user_id
        records = get_records(owner_user_id=user_id_1)
        assert len(records) == 1
        assert records[0]["submission_id"] == "test001"
        assert records[0]["owner_user_id"] == user_id_1
    
    def test_get_records_filters_by_owner(self, temp_db):
        """get_records should only return records for the specified owner."""
        user_id_1 = "user-123"
        user_id_2 = "user-456"
        
        # Create records for user 1
        record1 = SubmissionRecord(
            submission_id="test001",
            student_name="John Doe",
            school_name="Lincoln Elementary",
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test001"
        )
        save_record(record1, filename="test1.pdf", owner_user_id=user_id_1)
        
        record2 = SubmissionRecord(
            submission_id="test002",
            student_name="Jane Smith",
            school_name="Roosevelt Elementary",
            grade=3,
            word_count=150,
            needs_review=False,
            review_reason_codes="",
            artifact_dir="artifacts/test002"
        )
        save_record(record2, filename="test2.pdf", owner_user_id=user_id_1)
        
        # Create record for user 2
        record3 = SubmissionRecord(
            submission_id="test003",
            student_name="Bob Johnson",
            school_name="Washington Elementary",
            grade=7,
            word_count=200,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test003"
        )
        save_record(record3, filename="test3.pdf", owner_user_id=user_id_2)
        
        # User 1 should only see their records
        user1_records = get_records(owner_user_id=user_id_1)
        assert len(user1_records) == 2
        assert all(r["owner_user_id"] == user_id_1 for r in user1_records)
        
        # User 2 should only see their records
        user2_records = get_records(owner_user_id=user_id_2)
        assert len(user2_records) == 1
        assert user2_records[0]["owner_user_id"] == user_id_2
        assert user2_records[0]["submission_id"] == "test003"
    
    def test_get_record_by_id_enforces_ownership(self, temp_db):
        """get_record_by_id should only return records owned by the user."""
        user_id_1 = "user-123"
        user_id_2 = "user-456"
        
        # Create record for user 1
        record = SubmissionRecord(
            submission_id="test001",
            student_name="John Doe",
            school_name="Lincoln Elementary",
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test001"
        )
        save_record(record, filename="test.pdf", owner_user_id=user_id_1)
        
        # User 1 can access their record
        result = get_record_by_id("test001", owner_user_id=user_id_1)
        assert result is not None
        assert result["submission_id"] == "test001"
        
        # User 2 cannot access user 1's record
        result = get_record_by_id("test001", owner_user_id=user_id_2)
        assert result is None
    
    def test_update_record_enforces_ownership(self, temp_db):
        """update_record should only update records owned by the user."""
        user_id_1 = "user-123"
        user_id_2 = "user-456"
        
        # Create record for user 1
        record = SubmissionRecord(
            submission_id="test001",
            student_name="John Doe",
            school_name="Lincoln Elementary",
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test001"
        )
        save_record(record, filename="test.pdf", owner_user_id=user_id_1)
        
        # User 1 can update their record
        result = update_record(
            "test001",
            {"student_name": "John Updated"},
            owner_user_id=user_id_1
        )
        assert result is True
        
        # Verify update
        updated = get_record_by_id("test001", owner_user_id=user_id_1)
        assert updated["student_name"] == "John Updated"
        
        # User 2 cannot update user 1's record
        result = update_record(
            "test001",
            {"student_name": "Hacked"},
            owner_user_id=user_id_2
        )
        assert result is False
        
        # Verify record unchanged
        unchanged = get_record_by_id("test001", owner_user_id=user_id_1)
        assert unchanged["student_name"] == "John Updated"
    
    def test_delete_record_enforces_ownership(self, temp_db):
        """delete_record should only delete records owned by the user."""
        user_id_1 = "user-123"
        user_id_2 = "user-456"
        
        # Create record for user 1
        record = SubmissionRecord(
            submission_id="test001",
            student_name="John Doe",
            school_name="Lincoln Elementary",
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test001"
        )
        save_record(record, filename="test.pdf", owner_user_id=user_id_1)
        
        # User 2 cannot delete user 1's record
        result = delete_record("test001", owner_user_id=user_id_2)
        assert result is False
        
        # Verify record still exists
        records = get_records(owner_user_id=user_id_1)
        assert len(records) == 1
        
        # User 1 can delete their record
        result = delete_record("test001", owner_user_id=user_id_1)
        assert result is True
        
        # Verify record deleted
        records = get_records(owner_user_id=user_id_1)
        assert len(records) == 0
    
    def test_get_stats_filters_by_owner(self, temp_db):
        """get_stats should only count records for the specified owner."""
        user_id_1 = "user-123"
        user_id_2 = "user-456"
        
        # Create records for user 1
        record1 = SubmissionRecord(
            submission_id="test001",
            student_name="John Doe",
            school_name="Lincoln Elementary",
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test001"
        )
        save_record(record1, filename="test1.pdf", owner_user_id=user_id_1)
        
        record2 = SubmissionRecord(
            submission_id="test002",
            student_name="Jane Smith",
            school_name="Roosevelt Elementary",
            grade=3,
            word_count=150,
            needs_review=False,
            review_reason_codes="",
            artifact_dir="artifacts/test002"
        )
        save_record(record2, filename="test2.pdf", owner_user_id=user_id_1)
        
        # Create record for user 2
        record3 = SubmissionRecord(
            submission_id="test003",
            student_name="Bob Johnson",
            school_name="Washington Elementary",
            grade=7,
            word_count=200,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test003"
        )
        save_record(record3, filename="test3.pdf", owner_user_id=user_id_2)
        
        # User 1 stats
        stats1 = get_stats(owner_user_id=user_id_1)
        assert stats1["total_count"] == 2
        assert stats1["clean_count"] == 1
        assert stats1["needs_review_count"] == 1
        
        # User 2 stats
        stats2 = get_stats(owner_user_id=user_id_2)
        assert stats2["total_count"] == 1
        assert stats2["clean_count"] == 0
        assert stats2["needs_review_count"] == 1
    
    def test_get_records_without_owner_returns_empty(self, temp_db):
        """get_records without owner_user_id should return empty list."""
        record = SubmissionRecord(
            submission_id="test001",
            student_name="John Doe",
            school_name="Lincoln Elementary",
            grade=5,
            word_count=100,
            needs_review=True,
            review_reason_codes="PENDING_REVIEW",
            artifact_dir="artifacts/test001"
        )
        save_record(record, filename="test.pdf", owner_user_id="user-123")
        
        # Query without owner_user_id should return empty
        records = get_records(owner_user_id=None)
        assert len(records) == 0
        
        records = get_records()
        assert len(records) == 0

