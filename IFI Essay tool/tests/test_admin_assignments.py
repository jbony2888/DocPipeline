"""
Tests for admin assignment endpoints.
"""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch

import pytest


class _Result:
    def __init__(self, data: list[dict[str, Any]] | None = None):
        self.data = data or []


class _FakeAuthUser:
    def __init__(self, user_id: str, email: str):
        self.id = user_id
        self.email = email


class _FakeAuthAdmin:
    def __init__(self, users: list[dict[str, str]] | None = None):
        self._users = [
            _FakeAuthUser(str(user.get("id") or ""), str(user.get("email") or ""))
            for user in (users or [])
        ]

    def list_users(self, page: int = 1, per_page: int = 1000):
        start = max(0, (int(page) - 1) * int(per_page))
        end = start + int(per_page)
        return self._users[start:end]


class _FakeAuth:
    def __init__(self, users: list[dict[str, str]] | None = None):
        self.admin = _FakeAuthAdmin(users)


class _Query:
    def __init__(self, db: dict[str, Any], table_name: str):
        self._db = db
        self._table_name = table_name
        self._eq_filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list[Any]]] = []
        self._limit: int | None = None
        self._order_key: str | None = None
        self._order_desc: bool = False
        self._upsert_payload: list[dict[str, Any]] | None = None
        self._upsert_conflict: str | None = None
        self._update_payload: dict[str, Any] | None = None
        self._delete_mode = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key: str, value: Any):
        self._eq_filters.append((key, value))
        return self

    def in_(self, key: str, values: list[Any]):
        self._in_filters.append((key, values))
        return self

    def limit(self, value: int):
        self._limit = int(value)
        return self

    def order(self, key: str, desc: bool = False):
        self._order_key = key
        self._order_desc = bool(desc)
        return self

    def upsert(self, payload: list[dict[str, Any]], on_conflict: str | None = None, **_kwargs):
        self._upsert_payload = payload
        self._upsert_conflict = on_conflict
        return self

    def update(self, payload: dict[str, Any]):
        self._update_payload = dict(payload)
        return self

    def delete(self):
        self._delete_mode = True
        return self

    def execute(self):
        if self._upsert_payload is not None:
            return self._execute_upsert()
        if self._update_payload is not None:
            return self._execute_update()
        if self._delete_mode:
            return self._execute_delete()
        return self._execute_select()

    def _execute_select(self):
        rows = self._apply_filters(self._db[self._table_name])
        if self._order_key:
            rows = sorted(rows, key=lambda r: r.get(self._order_key), reverse=self._order_desc)
        if self._limit is not None:
            rows = rows[: self._limit]

        if self._table_name == "assignments":
            out = []
            readers_by_id = {r["id"]: r for r in self._db["readers"]}
            for row in rows:
                joined = dict(row)
                reader = readers_by_id.get(row.get("reader_id")) or {}
                joined["readers"] = {
                    "id": reader.get("id"),
                    "email": reader.get("email"),
                    "name": reader.get("name"),
                }
                out.append(joined)
            return _Result(copy.deepcopy(out))
        return _Result(copy.deepcopy(rows))

    def _apply_filters(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = rows
        for key, value in self._eq_filters:
            out = [r for r in out if r.get(key) == value]
        for key, values in self._in_filters:
            values_set = set(values)
            out = [r for r in out if r.get(key) in values_set]
        return out

    def _execute_upsert(self):
        assert self._upsert_payload is not None
        conflict_keys = [k.strip() for k in (self._upsert_conflict or "").split(",") if k.strip()]
        table = self._db[self._table_name]
        inserted: list[dict[str, Any]] = []

        for row in self._upsert_payload:
            existing = None
            if conflict_keys:
                for current in table:
                    if all(current.get(k) == row.get(k) for k in conflict_keys):
                        existing = current
                        break
            if existing is not None:
                continue

            new_row = dict(row)
            if self._table_name == "readers":
                new_row.setdefault("id", self._db["_reader_id_seq"])
                self._db["_reader_id_seq"] += 1
            if self._table_name == "assignments":
                new_row.setdefault("id", self._db["_assignment_id_seq"])
                self._db["_assignment_id_seq"] += 1
                new_row.setdefault("created_at", "2026-03-22T00:00:00Z")
            if self._table_name == "essay_rankings":
                new_row.setdefault("id", self._db["_essay_ranking_id_seq"])
                self._db["_essay_ranking_id_seq"] += 1
                new_row.setdefault("created_at", "2026-03-22T00:00:00Z")
                new_row.setdefault("updated_at", "2026-03-22T00:00:00Z")
            table.append(new_row)
            inserted.append(new_row)

        return _Result(copy.deepcopy(inserted))

    def _execute_update(self):
        assert self._update_payload is not None
        rows = self._apply_filters(self._db[self._table_name])
        updated = []
        for row in rows:
            row.update(self._update_payload)
            updated.append(dict(row))
        return _Result(copy.deepcopy(updated))

    def _execute_delete(self):
        table = self._db[self._table_name]
        rows_to_delete = self._apply_filters(table)
        ids_to_delete = {r.get("id") for r in rows_to_delete}
        self._db[self._table_name] = [r for r in table if r.get("id") not in ids_to_delete]
        return _Result(copy.deepcopy(rows_to_delete))


class _FakeSupabase:
    def __init__(
        self,
        submissions: list[dict[str, Any]] | None = None,
        readers: list[dict[str, Any]] | None = None,
        assignments: list[dict[str, Any]] | None = None,
        essay_rankings: list[dict[str, Any]] | None = None,
        auth_users: list[dict[str, str]] | None = None,
    ):
        self.db = {
            "submissions": submissions or [],
            "readers": readers or [],
            "assignments": assignments or [],
            "essay_rankings": essay_rankings or [],
            "_reader_id_seq": 1,
            "_assignment_id_seq": 1,
            "_essay_ranking_id_seq": 1,
        }
        self.auth = _FakeAuth(auth_users)
        if self.db["readers"]:
            self.db["_reader_id_seq"] = max(int(r["id"]) for r in self.db["readers"]) + 1
        if self.db["assignments"]:
            self.db["_assignment_id_seq"] = max(int(r["id"]) for r in self.db["assignments"]) + 1
        if self.db["essay_rankings"]:
            self.db["_essay_ranking_id_seq"] = max(int(r["id"]) for r in self.db["essay_rankings"]) + 1

    def table(self, name: str):
        if name not in self.db:
            raise KeyError(name)
        return _Query(self.db, name)


@pytest.fixture
def app():
    from flask_app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key"
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _set_admin_session(client):
    with client.session_transaction() as sess:
        sess["admin_authenticated"] = True


def _set_reader_portal_session(client, email: str):
    with client.session_transaction() as sess:
        sess["reader_portal_email"] = str(email or "").strip().lower()


def test_batches_endpoint_groups_by_school_and_grade(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[
            {"school_name": "De Lasalle", "grade": 2, "student_name": "A", "needs_review": False, "review_reason_codes": "", "owner_user_id": "u-1"},
            {"school_name": "De La Salle Institute", "grade": 2, "student_name": "B", "needs_review": False, "review_reason_codes": "", "owner_user_id": "u-1"},
            {"school_name": "DelaSalle Institute", "grade": 3, "student_name": "C", "needs_review": False, "review_reason_codes": "", "owner_user_id": "u-2"},
            {"school_name": "Danna Alexandra Villalba Ramirez", "grade": 2, "student_name": "D", "needs_review": False, "review_reason_codes": "", "owner_user_id": "u-3"},
        ],
        auth_users=[
            {"id": "u-1", "email": "teacher1@example.com"},
            {"id": "u-2", "email": "teacher2@example.com"},
            {"id": "u-3", "email": "teacher3@example.com"},
        ],
    )
    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get("/admin/essays/batches")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["schools"]) == 3
    by_school = {row["school"]: row for row in data["schools"]}
    assert "De La Salle Institute" in by_school
    assert "Rachel Carson Elementary School" in by_school
    assert "Mundelein HS" in by_school
    assert len(by_school["De La Salle Institute"]["grades"]) == 2
    grade2 = next(row for row in by_school["De La Salle Institute"]["grades"] if row["grade"] == "2")
    assert grade2["teacherEmails"] == ["teacher1@example.com"]
    assert grade2["teacherEmailCount"] == 1


def test_batches_endpoint_accepts_already_standardized_school_labels(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[
            {"school_name": "Mundelein HS", "grade": 10, "student_name": "A", "needs_review": False, "review_reason_codes": "[]", "owner_user_id": "u-1"},
            {"school_name": "Mundelein HS", "grade": 10, "student_name": "B", "needs_review": False, "review_reason_codes": "[]", "owner_user_id": "u-2"},
        ],
        auth_users=[
            {"id": "u-1", "email": "teacher1@example.com"},
            {"id": "u-2", "email": "teacher2@example.com"},
        ],
    )
    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get("/admin/essays/batches")
    assert res.status_code == 200
    data = res.get_json()
    by_school = {row["school"]: row for row in data["schools"]}
    munderein = by_school["Mundelein HS"]["grades"]
    assert len(munderein) == 1
    assert munderein[0]["grade"] == "10"
    assert munderein[0]["approvedCount"] == 2
    assert munderein[0]["teacherEmails"] == ["teacher1@example.com", "teacher2@example.com"]


def test_batches_endpoint_deduplicates_teacher_emails_per_school_grade(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[
            {"school_name": "De La Salle Institute", "grade": 9, "student_name": "A", "needs_review": False, "review_reason_codes": "", "owner_user_id": "u-1"},
            {"school_name": "De Lasalle", "grade": 9, "student_name": "B", "needs_review": False, "review_reason_codes": "", "owner_user_id": "u-1"},
            {"school_name": "De La Salle Institute", "grade": 9, "student_name": "C", "needs_review": False, "review_reason_codes": "", "owner_user_id": "u-2"},
        ],
        auth_users=[
            {"id": "u-1", "email": "Teacher1@Example.com"},
            {"id": "u-2", "email": "teacher2@example.com"},
        ],
    )
    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get("/admin/essays/batches")
    assert res.status_code == 200
    data = res.get_json()
    by_school = {row["school"]: row for row in data["schools"]}
    grade9 = next(row for row in by_school["De La Salle Institute"]["grades"] if row["grade"] == "9")
    assert grade9["teacherEmails"] == ["teacher1@example.com", "teacher2@example.com"]
    assert grade9["teacherEmailCount"] == 2


def test_summary_endpoint_returns_approved_count_for_school_grade(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[
            {"grade": 2, "school_name": "DelaSalle Institute", "student_name": "A", "needs_review": False, "review_reason_codes": ""},
            {"grade": 2, "school_name": "De La Salle Institute", "student_name": "B", "needs_review": True, "review_reason_codes": "MISSING_GRADE"},
            {"grade": 2, "school_name": "Carson", "student_name": "C", "needs_review": False, "review_reason_codes": ""},
        ]
    )
    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get("/admin/essays/summary?school=De%20La%20Salle%20Institute&grade=2")
    assert res.status_code == 200
    data = res.get_json()
    assert data["school"] == "De La Salle Institute"
    assert data["grade"] == "2"
    assert data["approvedCount"] == 1
    assert data["batchCount"] == 1
    assert len(data["batches"]) == 1
    assert data["batches"][0]["batchNumber"] == 1


def test_calculate_assignment_batch_count_uses_expected_thresholds():
    from admin.assignments_service import calculate_assignment_batch_count

    assert calculate_assignment_batch_count(0) == 0
    assert calculate_assignment_batch_count(1) == 1
    assert calculate_assignment_batch_count(30) == 1
    assert calculate_assignment_batch_count(31) == 2
    assert calculate_assignment_batch_count(60) == 2
    assert calculate_assignment_batch_count(61) == 3
    assert calculate_assignment_batch_count(90) == 3
    assert calculate_assignment_batch_count(91) == 4
    assert calculate_assignment_batch_count(120) == 4


def test_get_batch_bounds_evenly_distributes_by_batch_count():
    from admin.assignments_service import get_batch_bounds

    assert get_batch_bounds(1, 37) == (0, 19)
    assert get_batch_bounds(2, 37) == (19, 37)

    assert get_batch_bounds(1, 61) == (0, 21)
    assert get_batch_bounds(2, 61) == (21, 41)
    assert get_batch_bounds(3, 61) == (41, 61)

    assert get_batch_bounds(1, 91) == (0, 23)
    assert get_batch_bounds(2, 91) == (23, 46)
    assert get_batch_bounds(3, 91) == (46, 69)
    assert get_batch_bounds(4, 91) == (69, 91)


def test_assign_and_send_creates_missing_reader_and_assignment(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "school_name": "DelaSalle Institute",
                "grade": 2,
                "student_name": "A",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-1",
                "filename": "essay-a.pdf",
                "created_at": "2026-03-20T10:00:00Z",
            },
        ]
    )
    with patch("admin.routes._get_service_role_client", return_value=sb), \
         patch("admin.routes.download_original_with_service_role", return_value=(b"pdf-data", "artifacts/sub-1/original.pdf")), \
         patch("admin.routes.send_assignment_batch_email", return_value=True):
        res = client.post(
            "/admin/assign-and-send",
            json={"school": "De La Salle Institute", "grade": "2", "batchNumber": 1, "readerEmail": "Reader1@Example.com"},
        )
    assert res.status_code == 200
    data = res.get_json()
    assert data["essayCount"] == 1
    assert data["assignedReaders"] == 1
    assert data["batchNumber"] == 1
    assert data["batchEssayCount"] == 1
    assert len(sb.db["readers"]) == 1
    assert len(sb.db["assignments"]) == 1
    assert all(r["school_name"] == "De La Salle Institute" for r in sb.db["assignments"])
    assert sb.db["assignments"][0]["batch_number"] == 1


def test_assign_and_send_reuses_existing_reader(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[{
            "submission_id": "sub-1",
            "school_name": "De La Salle Institute",
            "grade": 2,
            "student_name": "A",
            "needs_review": False,
            "review_reason_codes": "",
            "artifact_dir": "artifacts/sub-1",
            "filename": "essay-a.pdf",
            "created_at": "2026-03-20T10:00:00Z",
        }],
        readers=[{"id": 10, "email": "reader1@example.com", "name": None}],
    )
    with patch("admin.routes._get_service_role_client", return_value=sb), \
         patch("admin.routes.download_original_with_service_role", return_value=(b"pdf-data", "artifacts/sub-1/original.pdf")), \
         patch("admin.routes.send_assignment_batch_email", return_value=True):
        res = client.post(
            "/admin/assign-and-send",
            json={"school": "De La Salle Institute", "grade": "2", "batchNumber": 1, "readerEmail": "reader1@example.com"},
        )
    assert res.status_code == 200
    assert len(sb.db["readers"]) == 1
    assert sb.db["assignments"][0]["reader_id"] == 10


def test_assign_and_send_allows_multiple_readers_for_same_batch(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[{
            "submission_id": "sub-1",
            "school_name": "De La Salle Institute",
            "grade": 2,
            "student_name": "A",
            "needs_review": False,
            "review_reason_codes": "",
            "artifact_dir": "artifacts/sub-1",
            "filename": "essay-a.pdf",
            "created_at": "2026-03-20T10:00:00Z",
        }],
        readers=[
            {"id": 1, "email": "reader1@example.com", "name": None},
            {"id": 2, "email": "reader2@example.com", "name": None},
        ],
        assignments=[{"id": 4, "reader_id": 1, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:00:00Z"}],
    )
    with patch("admin.routes._get_service_role_client", return_value=sb), \
         patch("admin.routes.download_original_with_service_role", return_value=(b"pdf-data", "artifacts/sub-1/original.pdf")), \
         patch("admin.routes.send_assignment_batch_email", return_value=True):
        res = client.post(
            "/admin/assign-and-send",
            json={"school": "De La Salle Institute", "grade": "2", "batchNumber": 1, "readerEmail": "reader2@example.com"},
        )
    assert res.status_code == 200
    assert len(sb.db["assignments"]) == 2
    assert sorted(row["reader_id"] for row in sb.db["assignments"]) == [1, 2]


def test_assign_and_send_fails_when_no_approved_essays(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[{"school_name": "De La Salle Institute", "grade": 2, "student_name": "A", "needs_review": True, "review_reason_codes": "MISSING_GRADE"}]
    )
    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.post(
            "/admin/assign-and-send",
            json={"school": "De La Salle Institute", "grade": "2", "batchNumber": 1, "readerEmail": "reader1@example.com"},
        )
    assert res.status_code == 400
    assert "No approved essays" in res.get_json()["error"]


def test_assign_and_send_validates_bad_emails(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[{"school_name": "De La Salle Institute", "grade": 2, "student_name": "A", "needs_review": False, "review_reason_codes": ""}]
    )
    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.post(
            "/admin/assign-and-send",
            json={"school": "De La Salle Institute", "grade": "2", "batchNumber": 1, "readerEmail": "not-an-email"},
        )
    assert res.status_code == 400
    data = res.get_json()
    assert "invalid" in data["error"].lower()
    assert "not-an-email" in data["invalidEmails"]


def test_assign_and_send_requires_valid_batch_number(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[{
            "submission_id": "sub-1",
            "school_name": "De La Salle Institute",
            "grade": 2,
            "student_name": "A",
            "needs_review": False,
            "review_reason_codes": "",
            "artifact_dir": "artifacts/sub-1",
            "filename": "essay-a.pdf",
            "created_at": "2026-03-20T10:00:00Z",
        }]
    )
    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.post(
            "/admin/assign-and-send",
            json={"school": "De La Salle Institute", "grade": "2", "batchNumber": 2, "readerEmail": "reader1@example.com"},
        )
    assert res.status_code == 400
    assert "out of range" in res.get_json()["error"]


def test_assignment_records_and_unassign(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[],
        readers=[{"id": 7, "email": "reader@example.com", "name": None}],
        assignments=[{"id": 55, "reader_id": 7, "school_name": "School A", "grade": "2", "batch_number": 1, "total_batches": 2, "created_at": "2026-03-22T10:00:00Z"}],
    )
    with patch("admin.routes._get_service_role_client", return_value=sb):
        list_res = client.get("/admin/assignment-records")
        assert list_res.status_code == 200
        records = list_res.get_json()["records"]
        assert len(records) == 1
        assert records[0]["readerEmail"] == "reader@example.com"
        assert records[0]["batchNumber"] == 1
        assert records[0]["totalBatches"] == 2

        del_res = client.post("/admin/unassign", json={"assignmentId": 55})
        assert del_res.status_code == 200
        assert len(sb.db["assignments"]) == 0


def test_assign_and_send_returns_error_when_email_send_fails(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[{
            "submission_id": "sub-1",
            "school_name": "De La Salle Institute",
            "grade": 2,
            "student_name": "A",
            "needs_review": False,
            "review_reason_codes": "",
            "artifact_dir": "artifacts/sub-1",
            "filename": "essay-a.pdf",
            "created_at": "2026-03-20T10:00:00Z",
        }]
    )
    with patch("admin.routes._get_service_role_client", return_value=sb), \
         patch("admin.routes.download_original_with_service_role", return_value=(b"pdf-data", "artifacts/sub-1/original.pdf")), \
         patch("admin.routes.send_assignment_batch_email", return_value=False):
        res = client.post(
            "/admin/assign-and-send",
            json={"school": "De La Salle Institute", "grade": "2", "batchNumber": 1, "readerEmail": "reader1@example.com"},
    )
    assert res.status_code == 500
    assert "could not be sent" in res.get_json()["error"]
    assert len(sb.db["assignments"]) == 1


def test_admin_authorization_is_enforced(client):
    sb = _FakeSupabase(submissions=[])
    with patch("admin.routes._get_service_role_client", return_value=sb):
        res_summary = client.get("/admin/essays/summary?school=De%20La%20Salle%20Institute&grade=2")
        res_assign = client.post(
            "/admin/assign-and-send",
            json={"school": "De La Salle Institute", "grade": "2", "batchNumber": 1, "readerEmail": "reader1@example.com"},
        )
        res_records = client.get("/admin/assignment-records")
        res_unassign = client.post("/admin/unassign", json={"assignmentId": 1})
    assert res_summary.status_code == 403
    assert res_assign.status_code == 403
    assert res_records.status_code == 403
    assert res_unassign.status_code == 403


def test_reader_assignment_review_saves_forced_rankings_and_updates_reader_name(client, app):
    from admin.routes import _generate_reader_portal_token

    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Alice",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-1",
                "filename": "essay-a.pdf",
                "created_at": "2026-03-20T10:00:00Z",
            },
            {
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Bob",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-2",
                "filename": "essay-b.pdf",
                "created_at": "2026-03-20T10:05:00Z",
            },
        ],
        readers=[{"id": 7, "email": "reader@example.com", "name": None}],
        assignments=[{"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:00:00Z"}],
    )
    with app.app_context():
        token = _generate_reader_portal_token("reader@example.com")
    _set_reader_portal_session(client, "reader@example.com")

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.post(
            f"/admin/reader-assignments/55/review?token={token}",
            data={
                "token": token,
                "reader_name": "Jane Reader",
                "reader_email": "reader@example.com",
                "rank_sub-1": "1",
                "rank_sub-2": "2",
            },
        )

    assert res.status_code == 200
    assert b"Rankings saved" in res.data
    assert sb.db["readers"][0]["name"] == "Jane Reader"
    assert len(sb.db["essay_rankings"]) == 2
    assert sorted((row["submission_id"], row["rank_position"]) for row in sb.db["essay_rankings"]) == [
        ("sub-1", 1),
        ("sub-2", 2),
    ]


def test_reader_assignment_review_saves_single_essay_ranking(client, app):
    from admin.routes import _generate_reader_portal_token

    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Alice",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-1",
                "filename": "essay-a.pdf",
                "created_at": "2026-03-20T10:00:00Z",
            },
            {
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Bob",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-2",
                "filename": "essay-b.pdf",
                "created_at": "2026-03-20T10:05:00Z",
            },
        ],
        readers=[{"id": 7, "email": "reader@example.com", "name": None}],
        assignments=[{"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:00:00Z"}],
    )
    with app.app_context():
        token = _generate_reader_portal_token("reader@example.com")
    _set_reader_portal_session(client, "reader@example.com")

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.post(
            f"/admin/reader-assignments/55/review?token={token}",
            data={
                "token": token,
                "reader_name": "Jane Reader",
                "reader_email": "reader@example.com",
                "rank_sub-1": "1",
                "save_submission_id": "sub-1",
            },
        )

    assert res.status_code == 200
    assert b"Saved rank 1 for this essay" in res.data
    assert sb.db["readers"][0]["name"] == "Jane Reader"
    assert sorted((row["submission_id"], row["rank_position"]) for row in sb.db["essay_rankings"]) == [
        ("sub-1", 1),
    ]


def test_reader_assignment_review_unranks_single_essay(client, app):
    from admin.routes import _generate_reader_portal_token

    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Alice",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-1",
                "filename": "essay-a.pdf",
                "created_at": "2026-03-20T10:00:00Z",
            },
            {
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Bob",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-2",
                "filename": "essay-b.pdf",
                "created_at": "2026-03-20T10:05:00Z",
            },
        ],
        readers=[{"id": 7, "email": "reader@example.com", "name": "Jane Reader"}],
        assignments=[{"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:00:00Z"}],
        essay_rankings=[
            {
                "id": 1,
                "assignment_id": 55,
                "reader_id": 7,
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 1,
                "reader_name": "Jane Reader",
                "reader_email": "reader@example.com",
                "created_at": "2026-03-22T10:00:00Z",
                "updated_at": "2026-03-22T10:00:00Z",
            },
        ],
    )
    with app.app_context():
        token = _generate_reader_portal_token("reader@example.com")
    _set_reader_portal_session(client, "reader@example.com")

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.post(
            f"/admin/reader-assignments/55/review?token={token}",
            data={
                "token": token,
                "reader_name": "Jane Reader",
                "reader_email": "reader@example.com",
                "unrank_submission_id": "sub-1",
            },
        )

    assert res.status_code == 200
    assert b"Essay moved back to unranked" in res.data
    assert sb.db["essay_rankings"] == []


def test_reader_assignment_review_rejects_duplicate_ranks(client, app):
    from admin.routes import _generate_reader_portal_token

    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Alice",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-1",
                "filename": "essay-a.pdf",
                "created_at": "2026-03-20T10:00:00Z",
            },
            {
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Bob",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-2",
                "filename": "essay-b.pdf",
                "created_at": "2026-03-20T10:05:00Z",
            },
        ],
        readers=[{"id": 7, "email": "reader@example.com", "name": None}],
        assignments=[{"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:00:00Z"}],
    )
    with app.app_context():
        token = _generate_reader_portal_token("reader@example.com")
    _set_reader_portal_session(client, "reader@example.com")

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.post(
            f"/admin/reader-assignments/55/review?token={token}",
            data={
                "token": token,
                "reader_name": "Jane Reader",
                "reader_email": "reader@example.com",
                "rank_sub-1": "1",
                "rank_sub-2": "1",
            },
        )

    assert res.status_code == 200
    assert b"Ranks must use every position" in res.data
    assert sb.db["essay_rankings"] == []


def test_reader_assignment_review_lists_only_essays_in_assigned_batch(client, app):
    from admin.routes import _generate_reader_portal_token

    submissions = []
    for idx in range(1, 32):
        submissions.append(
            {
                "submission_id": f"sub-{idx}",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": f"Student {idx}",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": f"artifacts/sub-{idx}",
                "filename": f"essay-{idx}.pdf",
                "created_at": f"2026-03-20T10:{idx:02d}:00Z",
            }
        )

    sb = _FakeSupabase(
        submissions=submissions,
        readers=[{"id": 7, "email": "reader@example.com", "name": None}],
        assignments=[{"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 2, "total_batches": 2, "created_at": "2026-03-22T10:00:00Z"}],
    )
    with app.app_context():
        token = _generate_reader_portal_token("reader@example.com")
    _set_reader_portal_session(client, "reader@example.com")

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get(f"/admin/reader-assignments/55/review?token={token}")

    assert res.status_code == 200
    assert b"Student 17" in res.data
    assert b"Student 31" in res.data
    assert b"Student 16" not in res.data


def test_reader_assignment_review_resubmission_overwrites_previous_rankings(client, app):
    from admin.routes import _generate_reader_portal_token

    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Alice",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-1",
                "filename": "essay-a.pdf",
                "created_at": "2026-03-20T10:00:00Z",
            },
            {
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Bob",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": "artifacts/sub-2",
                "filename": "essay-b.pdf",
                "created_at": "2026-03-20T10:05:00Z",
            },
        ],
        readers=[{"id": 7, "email": "reader@example.com", "name": "Jane Reader"}],
        assignments=[{"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:00:00Z"}],
        essay_rankings=[
            {
                "id": 1,
                "assignment_id": 55,
                "reader_id": 7,
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 1,
                "reader_name": "Jane Reader",
                "reader_email": "reader@example.com",
                "created_at": "2026-03-22T10:00:00Z",
                "updated_at": "2026-03-22T10:00:00Z",
            },
            {
                "id": 2,
                "assignment_id": 55,
                "reader_id": 7,
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 2,
                "reader_name": "Jane Reader",
                "reader_email": "reader@example.com",
                "created_at": "2026-03-22T10:00:00Z",
                "updated_at": "2026-03-22T10:00:00Z",
            },
        ],
    )
    with app.app_context():
        token = _generate_reader_portal_token("reader@example.com")
    _set_reader_portal_session(client, "reader@example.com")

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.post(
            f"/admin/reader-assignments/55/review?token={token}",
            data={
                "token": token,
                "reader_name": "Jane Reader",
                "reader_email": "reader@example.com",
                "rank_sub-1": "2",
                "rank_sub-2": "1",
            },
        )

    assert res.status_code == 200
    assert b"Rankings saved" in res.data
    assert len(sb.db["essay_rankings"]) == 2
    assert sorted((row["submission_id"], row["rank_position"]) for row in sb.db["essay_rankings"]) == [
        ("sub-1", 2),
        ("sub-2", 1),
    ]


def test_reader_submission_view_rejects_essay_outside_assignment_batch(client, app):
    from admin.routes import _generate_reader_portal_token

    submissions = []
    for idx in range(1, 32):
        submissions.append(
            {
                "submission_id": f"sub-{idx}",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": f"Student {idx}",
                "needs_review": False,
                "review_reason_codes": "",
                "artifact_dir": f"artifacts/sub-{idx}",
                "filename": f"essay-{idx}.pdf",
                "created_at": f"2026-03-20T10:{idx:02d}:00Z",
            }
        )

    sb = _FakeSupabase(
        submissions=submissions,
        readers=[{"id": 7, "email": "reader@example.com", "name": None}],
        assignments=[{"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 2, "total_batches": 2, "created_at": "2026-03-22T10:00:00Z"}],
    )
    with app.app_context():
        token = _generate_reader_portal_token("reader@example.com")
    _set_reader_portal_session(client, "reader@example.com")

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get(f"/admin/reader-assignments/55/submissions/sub-1/view?token={token}")

    assert res.status_code == 404


def test_ranking_results_aggregates_same_essay_across_multiple_readers(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Alice",
                "needs_review": False,
                "review_reason_codes": "",
            },
            {
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Bob",
                "needs_review": False,
                "review_reason_codes": "",
            },
        ],
        readers=[
            {"id": 7, "email": "reader1@example.com", "name": "Reader One"},
            {"id": 8, "email": "reader2@example.com", "name": "Reader Two"},
        ],
        assignments=[
            {"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:00:00Z"},
            {"id": 56, "reader_id": 8, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:10:00Z"},
        ],
        essay_rankings=[
            {
                "id": 1,
                "assignment_id": 55,
                "reader_id": 7,
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 1,
                "reader_name": "Reader One",
                "reader_email": "reader1@example.com",
                "created_at": "2026-03-22T10:00:00Z",
                "updated_at": "2026-03-22T10:00:00Z",
            },
            {
                "id": 2,
                "assignment_id": 55,
                "reader_id": 7,
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 2,
                "reader_name": "Reader One",
                "reader_email": "reader1@example.com",
                "created_at": "2026-03-22T10:00:00Z",
                "updated_at": "2026-03-22T10:00:00Z",
            },
            {
                "id": 3,
                "assignment_id": 56,
                "reader_id": 8,
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 2,
                "reader_name": "Reader Two",
                "reader_email": "reader2@example.com",
                "created_at": "2026-03-22T10:10:00Z",
                "updated_at": "2026-03-22T10:10:00Z",
            },
            {
                "id": 4,
                "assignment_id": 56,
                "reader_id": 8,
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 1,
                "reader_name": "Reader Two",
                "reader_email": "reader2@example.com",
                "created_at": "2026-03-22T10:10:00Z",
                "updated_at": "2026-03-22T10:10:00Z",
            },
        ],
    )

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get("/admin/ranking-results?grade=2&school=De%20La%20Salle%20Institute")

    assert res.status_code == 200
    data = res.get_json()
    assert data["grade"] == "2"
    assert len(data["results"]) == 2
    first = data["results"][0]
    second = data["results"][1]
    assert first["submissionId"] == "sub-1"
    assert first["finalPosition"] == 1
    assert first["numRanks"] == 2
    assert first["averageRank"] == 1.5
    assert first["firstPlaceVotes"] == 1
    assert len(first["readerBreakdown"]) == 2
    assert second["submissionId"] == "sub-2"
    assert second["finalPosition"] == 2
    assert second["averageRank"] == 1.5
    assert second["firstPlaceVotes"] == 1


def test_admin_rankings_page_shows_winner_and_reader_breakdown(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Alice",
                "needs_review": False,
                "review_reason_codes": "",
            },
            {
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": 2,
                "student_name": "Bob",
                "needs_review": False,
                "review_reason_codes": "",
            },
        ],
        readers=[
            {"id": 7, "email": "reader1@example.com", "name": "Reader One"},
            {"id": 8, "email": "reader2@example.com", "name": "Reader Two"},
        ],
        assignments=[
            {"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:00:00Z"},
            {"id": 56, "reader_id": 8, "school_name": "De La Salle Institute", "grade": "2", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:10:00Z"},
        ],
        essay_rankings=[
            {
                "id": 1,
                "assignment_id": 55,
                "reader_id": 7,
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 1,
                "reader_name": "Reader One",
                "reader_email": "reader1@example.com",
                "created_at": "2026-03-22T10:00:00Z",
                "updated_at": "2026-03-22T10:00:00Z",
            },
            {
                "id": 2,
                "assignment_id": 56,
                "reader_id": 8,
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 2,
                "reader_name": "Reader Two",
                "reader_email": "reader2@example.com",
                "created_at": "2026-03-22T10:10:00Z",
                "updated_at": "2026-03-22T10:10:00Z",
            },
            {
                "id": 3,
                "assignment_id": 55,
                "reader_id": 7,
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 2,
                "reader_name": "Reader One",
                "reader_email": "reader1@example.com",
                "created_at": "2026-03-22T10:00:00Z",
                "updated_at": "2026-03-22T10:00:00Z",
            },
            {
                "id": 4,
                "assignment_id": 56,
                "reader_id": 8,
                "submission_id": "sub-2",
                "school_name": "De La Salle Institute",
                "grade": "2",
                "batch_number": 1,
                "rank_position": 3,
                "reader_name": "Reader Two",
                "reader_email": "reader2@example.com",
                "created_at": "2026-03-22T10:10:00Z",
                "updated_at": "2026-03-22T10:10:00Z",
            },
        ],
    )

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get("/admin/rankings?grade=2&school=De%20La%20Salle%20Institute")

    assert res.status_code == 200
    page = res.get_data(as_text=True)
    assert "Rankings" in page
    assert "Grade 2 Winner" in page
    assert "Alice" in page
    assert "Grade 2 Second Place" in page
    assert "Bob" in page
    assert "Reader One: rank 1" in page
    assert "Reader Two: rank 2" in page
    assert "Winner" in page


def test_admin_rankings_page_shows_provisional_leader_when_only_one_ranked_essay(client):
    _set_admin_session(client)
    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": 10,
                "student_name": "Abby Castaneda",
                "needs_review": False,
                "review_reason_codes": "",
            },
        ],
        readers=[
            {"id": 7, "email": "reader1@example.com", "name": "Reader One"},
        ],
        assignments=[
            {"id": 55, "reader_id": 7, "school_name": "De La Salle Institute", "grade": "10", "batch_number": 1, "total_batches": 1, "created_at": "2026-03-22T10:00:00Z"},
        ],
        essay_rankings=[
            {
                "id": 1,
                "assignment_id": 55,
                "reader_id": 7,
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": "10",
                "batch_number": 1,
                "rank_position": 8,
                "reader_name": "Reader One",
                "reader_email": "reader1@example.com",
                "created_at": "2026-03-22T10:00:00Z",
                "updated_at": "2026-03-22T10:00:00Z",
            },
        ],
    )

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get("/admin/rankings?grade=10&school=De%20La%20Salle%20Institute")

    assert res.status_code == 200
    page = res.get_data(as_text=True)
    assert "Grade 10 Provisional Leader" in page
    assert "A final winner is not declared until at least two essays have ranking data" in page
    assert "Leader" in page
    assert "Winner" not in page


def test_reader_access_page_shows_assignment_and_ranking_instructions(client, app):
    from admin import routes as admin_routes

    sb = _FakeSupabase(
        submissions=[
            {
                "submission_id": "sub-1",
                "student_name": "Abby Castaneda",
                "school_name": "De La Salle Institute",
                "grade": "10",
                "created_at": "2026-03-18T04:19:00Z",
                "needs_review": False,
                "status": "approved",
            }
        ],
        readers=[{"id": 7, "email": "reader@example.com", "name": "Reader One"}],
        assignments=[
            {
                "id": 55,
                "reader_id": 7,
                "school_name": "De La Salle Institute",
                "grade": "10",
                "batch_number": 1,
                "total_batches": 1,
                "created_at": "2026-03-22T10:00:00Z",
            }
        ],
        essay_rankings=[
            {
                "id": 1,
                "assignment_id": 55,
                "reader_id": 7,
                "submission_id": "sub-1",
                "school_name": "De La Salle Institute",
                "grade": "10",
                "batch_number": 1,
                "rank_position": 1,
                "reader_name": "Reader One",
                "reader_email": "reader@example.com",
                "created_at": "2026-03-22T10:00:00Z",
                "updated_at": "2026-03-22T10:00:00Z",
            }
        ],
    )
    token = admin_routes._generate_reader_portal_token("reader@example.com")
    _set_reader_portal_session(client, "reader@example.com")

    with patch("admin.routes._get_service_role_client", return_value=sb):
        res = client.get(f"/admin/reader-access?token={token}")

    assert res.status_code == 200
    page = res.get_data(as_text=True)
    assert "Assigned Batches" in page
    assert "Review &amp; Rank" in page
    assert "Open a batch with <strong>Review &amp; Rank</strong>" in page
    assert "Use <strong>1</strong> for the best essay in the batch" in page
    assert "save that essay" in page
    assert "Unrank</strong> moves an essay back to unranked" in page
    assert "De La Salle Institute" in page
    assert "Grade 10" in page


def test_assignment_email_includes_ranking_instructions():
    from utils import email_notification

    with patch("utils.email_notification.send_smtp_email", return_value=True) as send_mock:
        ok = email_notification.send_assignment_batch_email(
            to_email="reader@example.com",
            school="De La Salle Institute",
            grade="10",
            batch_number=1,
            total_batches=2,
            essay_count=30,
            portal_url="https://example.com/admin/reader-access?token=abc",
        )

    assert ok is True
    send_mock.assert_called_once()
    to_email, subject, html_body, text_body = send_mock.call_args.args
    assert to_email == "reader@example.com"
    assert "IFI Essay Batch Assignment" in subject
    assert "Open your reader access page" in html_body
    assert "Ranking instructions" in html_body
    assert "1 = best essay in your batch" in html_body
    assert "30 = lowest-ranked essay in your batch" in html_body
    assert "Save each essay's rank with its own Save button" in html_body
    assert "Use Unrank" in html_body
    assert "Only one essay can hold each rank number" in html_body
    assert "Open your reader access page" in text_body
    assert "- Save each essay with its own Save button" in text_body
    assert "- Use Unrank to move an essay back to unranked" in text_body
