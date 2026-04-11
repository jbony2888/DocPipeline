from __future__ import annotations

from typing import Any

import pytest


class _Result:
    def __init__(self, data: list[dict[str, Any]] | None = None):
        self.data = data or []


class _Query:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self._filters: list[tuple[str, Any]] = []
        self._limit: int | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key: str, value: Any):
        self._filters.append((key, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, value: int):
        self._limit = int(value)
        return self

    def execute(self):
        rows = self._rows
        for key, value in self._filters:
            rows = [row for row in rows if row.get(key) == value]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result([dict(row) for row in rows])


class _FakeSupabase:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self.table_calls: list[str] = []

    def table(self, name: str):
        self.table_calls.append(name)
        if name != "submissions":
            raise AssertionError(f"Unexpected table: {name}")
        return _Query(self._rows)


def test_get_records_prefers_service_role_for_owner_scoped_queries(monkeypatch):
    from pipeline import supabase_db

    service_rows = [
        {
            "submission_id": "approved-1",
            "owner_user_id": "user-123",
            "needs_review": False,
            "student_name": "John Doe",
        },
        {
            "submission_id": "review-1",
            "owner_user_id": "user-123",
            "needs_review": True,
            "student_name": "Jane Doe",
        },
    ]
    service_client = _FakeSupabase(service_rows)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Authenticated client should not be used for owner-scoped export reads")

    monkeypatch.setattr(supabase_db, "_get_service_role_client", lambda: service_client)
    monkeypatch.setattr(supabase_db, "get_supabase_client", fail_if_called)

    rows = supabase_db.get_records(needs_review=False, owner_user_id="user-123")

    assert [row["submission_id"] for row in rows] == ["approved-1"]
    assert all(row["owner_user_id"] == "user-123" for row in rows)
    assert service_client.table_calls == ["submissions"]


def test_get_records_falls_back_when_service_role_unavailable(monkeypatch):
    from pipeline import supabase_db

    auth_rows = [
        {
            "submission_id": "approved-2",
            "owner_user_id": "user-999",
            "needs_review": False,
        }
    ]
    auth_client = _FakeSupabase(auth_rows)

    monkeypatch.setattr(supabase_db, "_get_service_role_client", lambda: None)
    monkeypatch.setattr(supabase_db, "get_supabase_client", lambda access_token=None: auth_client)

    rows = supabase_db.get_records(needs_review=False, owner_user_id="user-999", access_token="token")

    assert [row["submission_id"] for row in rows] == ["approved-2"]
    assert auth_client.table_calls == ["submissions"]
