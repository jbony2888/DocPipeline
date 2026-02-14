"""
Unit tests for job processing and queue functionality.
Tests RLS fixes, job enqueueing, and status checking.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os
import json


class TestJobEnqueueing:
    """Tests for job enqueueing with RLS fixes."""
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_SERVICE_ROLE_KEY': 'test-service-role-key'
    })
    @patch('jobs.pg_queue.create_client')
    def test_enqueue_uses_service_role_key(self, mock_create_client):
        """enqueue_submission should use service role key to bypass RLS."""
        from jobs.pg_queue import enqueue_submission
        
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [{'id': 'test-job-id'}]
        mock_create_client.return_value = mock_supabase
        
        job_id = enqueue_submission(
            file_bytes=b'test file content',
            filename='test.pdf',
            owner_user_id='test-user-123',
            access_token='test-token'
        )
        
        assert job_id == 'test-job-id'
        # Verify service role key was used
        mock_create_client.assert_called_once_with(
            'https://test.supabase.co',
            'test-service-role-key'
        )
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_SERVICE_ROLE_KEY': ''
    })
    def test_enqueue_fails_without_service_role_key(self):
        """enqueue_submission should fail if service role key is missing."""
        from jobs.pg_queue import enqueue_submission
        
        with pytest.raises(Exception) as exc_info:
            enqueue_submission(
                file_bytes=b'test file content',
                filename='test.pdf',
                owner_user_id='test-user-123',
                access_token='test-token'
            )
        
        assert 'Service Role Key' in str(exc_info.value) or 'not set' in str(exc_info.value)
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_SERVICE_ROLE_KEY': 'test-service-role-key'
    })
    @patch('jobs.pg_queue.create_client')
    def test_enqueue_stores_owner_user_id(self, mock_create_client):
        """enqueue_submission should store owner_user_id in job_data."""
        from jobs.pg_queue import enqueue_submission
        
        mock_supabase = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute.return_value.data = [{'id': 'test-job-id'}]
        mock_supabase.table.return_value.insert.return_value = mock_insert
        mock_create_client.return_value = mock_supabase
        
        enqueue_submission(
            file_bytes=b'test file content',
            filename='test.pdf',
            owner_user_id='test-user-123',
            access_token='test-token'
        )
        
        # Verify job_data contains owner_user_id
        call_args = mock_supabase.table.return_value.insert.call_args
        assert call_args is not None
        job_data = call_args[0][0]["job_data"]
        assert job_data['owner_user_id'] == 'test-user-123'


class TestJobStatusChecking:
    """Tests for job status checking with RLS fixes."""
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_SERVICE_ROLE_KEY': 'test-service-role-key'
    })
    @patch('jobs.pg_queue.create_client')
    def test_get_queue_status_uses_service_role_key(self, mock_create_client):
        """get_queue_status should use service role key to bypass RLS."""
        from jobs.pg_queue import get_queue_status
        
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
            {'id': 'job1', 'status': 'finished', 'started_at': '2024-01-01T10:00:00Z', 'finished_at': '2024-01-01T10:00:15Z'},
            {'id': 'job2', 'status': 'queued'}
        ]
        mock_create_client.return_value = mock_supabase
        
        status = get_queue_status(['job1', 'job2'])
        
        assert status['total'] == 2
        assert status['completed'] == 1
        assert status['pending'] == 1
        # Verify service role key was used
        mock_create_client.assert_called_once_with(
            'https://test.supabase.co',
            'test-service-role-key'
        )
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_SERVICE_ROLE_KEY': ''
    })
    def test_get_queue_status_handles_missing_key(self):
        """get_queue_status should handle missing service role key gracefully."""
        from jobs.pg_queue import get_queue_status
        
        status = get_queue_status(['job1', 'job2'])
        
        assert status['total'] == 2
        assert status['pending'] == 2
        assert 'error' in status or status['completed'] == 0
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_SERVICE_ROLE_KEY': 'test-service-role-key'
    })
    @patch('jobs.pg_queue.create_client')
    def test_get_queue_status_calculates_estimated_time(self, mock_create_client):
        """get_queue_status should calculate estimated remaining time."""
        from jobs.pg_queue import get_queue_status
        
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
            {'id': 'job1', 'status': 'finished', 'started_at': '2024-01-01T10:00:00Z', 'finished_at': '2024-01-01T10:00:15Z'},
            {'id': 'job2', 'status': 'queued'},
            {'id': 'job3', 'status': 'queued'}
        ]
        mock_create_client.return_value = mock_supabase
        
        status = get_queue_status(['job1', 'job2', 'job3'])
        
        assert status['total'] == 3
        assert status['completed'] == 1
        assert status['pending'] == 2
        assert status['estimated_remaining_seconds'] > 0


class TestBatchStatusAPI:
    """Tests for /api/batch_status endpoint."""
    
    @pytest.fixture
    def app(self):
        """Create Flask app for testing."""
        from flask_app import app as flask_app
        flask_app.config['TESTING'] = True
        flask_app.config['SECRET_KEY'] = 'test-secret-key'
        return flask_app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()
    
    @pytest.fixture
    def mock_session(self, client):
        """Mock authenticated session."""
        with client.session_transaction() as sess:
            sess['user_id'] = 'test-user-123'
            sess['supabase_access_token'] = 'test-token'
            sess['processing_jobs'] = [
                {'filename': 'test1.pdf', 'job_id': 'job1'},
                {'filename': 'test2.pdf', 'job_id': 'job2'}
            ]
        return sess
    
    @patch('flask_app.get_queue_status')
    def test_batch_status_returns_job_status(self, mock_get_status, client, mock_session):
        """batch_status should return job status from queue."""
        mock_get_status.return_value = {
            'total': 2,
            'completed': 1,
            'failed': 0,
            'pending': 1,
            'in_progress': 0,
            'estimated_remaining_seconds': 30
        }
        
        response = client.get('/api/batch_status')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['total'] == 2
        assert data['completed'] == 1
        assert data['pending'] == 1
    
    @patch('flask_app.get_supabase_client')
    @patch('flask_app.get_queue_status')
    def test_batch_status_fallback_to_db(self, mock_get_status, mock_get_client, client, mock_session):
        """batch_status should fallback to database if session is empty."""
        # Clear session jobs
        with client.session_transaction() as sess:
            sess['processing_jobs'] = []
            sess['user_id'] = 'test-user-123'
            sess['supabase_access_token'] = 'test-token'
        
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.not_.return_value.not_.return_value.execute.return_value.data = [
            {'id': 'job1'},
            {'id': 'job2'}
        ]
        mock_get_client.return_value = mock_supabase
        mock_get_status.return_value = {
            'total': 2,
            'completed': 0,
            'pending': 2,
            'in_progress': 0,
            'estimated_remaining_seconds': 40
        }
        
        response = client.get('/api/batch_status')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['total'] == 2


