"""Tests for admin duplicate-upload detection (standalone rows only)."""

from admin.routes import _apply_duplicates_only_filter, _plan_duplicate_removals


def _base_row(**kwargs):
    base = {
        "submission_id": "s1",
        "student_name": "Jane",
        "school_name": "Edwards",
        "grade": "5",
        "filename": "Essay.pdf",
        "created_at": "2026-01-02T12:00:00Z",
        "parent_submission_id": None,
        "is_chunk": False,
        "essay_linked_from_submission_id": None,
        "is_container_parent": False,
    }
    base.update(kwargs)
    return base


def test_keeps_newest_duplicate():
    rows = [
        _base_row(submission_id="old", created_at="2026-01-01T10:00:00Z"),
        _base_row(submission_id="new", created_at="2026-01-03T10:00:00Z"),
    ]
    summaries, to_delete = _plan_duplicate_removals(rows)
    assert len(summaries) == 1
    assert summaries[0]["kept_submission_id"] == "new"
    assert [r["submission_id"] for r in to_delete] == ["old"]


def test_chunk_rows_not_grouped():
    parent = "p1"
    rows = [
        _base_row(submission_id="c1", parent_submission_id=parent, is_chunk=True, filename="m.pdf"),
        _base_row(submission_id="c2", parent_submission_id=parent, is_chunk=True, filename="m.pdf"),
    ]
    summaries, to_delete = _plan_duplicate_removals(rows)
    assert summaries == []
    assert to_delete == []


def test_container_parent_not_grouped():
    rows = [
        _base_row(submission_id="p1", is_container_parent=True),
        _base_row(submission_id="p2", is_container_parent=True),
    ]
    summaries, to_delete = _plan_duplicate_removals(rows)
    assert summaries == []
    assert to_delete == []


def test_duplicates_only_filter_shows_both_rows_in_group():
    rows = [
        _base_row(submission_id="a", created_at="2026-01-01T10:00:00Z"),
        _base_row(submission_id="b", created_at="2026-01-03T10:00:00Z"),
        _base_row(submission_id="other", student_name="Bob", created_at="2026-01-02T10:00:00Z"),
    ]
    filtered = _apply_duplicates_only_filter(rows, True)
    ids = {r["submission_id"] for r in filtered}
    assert ids == {"a", "b"}


def test_duplicates_only_filter_off_passes_through():
    rows = [
        _base_row(submission_id="a"),
        _base_row(submission_id="b"),
    ]
    assert _apply_duplicates_only_filter(rows, False) == rows
