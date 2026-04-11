from __future__ import annotations

import io
from unittest.mock import patch

import pytest


@pytest.fixture
def app():
    from flask_app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key"
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_session(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "test-user-123"
        sess["supabase_access_token"] = "test-token"
    return sess


@patch("flask_app._export_records_to_csv")
@patch("flask_app.get_db_records")
def test_export_csv_uses_global_approved_records(mock_get_records, mock_export_csv, client, auth_session):
    mock_get_records.return_value = [
        {"submission_id": "approved-1"},
        {"submission_id": "approved-2"},
    ]
    mock_export_csv.return_value = io.BytesIO(b"csv-bytes")

    response = client.get("/export")

    assert response.status_code == 200
    assert mock_get_records.call_count == 1
    kwargs = mock_get_records.call_args.kwargs
    assert kwargs["needs_review"] is False
    assert kwargs["force_service_role"] is True
    assert kwargs.get("owner_user_id") is None
    assert response.data == b"csv-bytes"
