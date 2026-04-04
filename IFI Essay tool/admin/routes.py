"""
Admin Blueprint: view all submissions, download files securely.
Admin-controlled access via Bearer token or session.
"""

import csv
import io
import html
import os
import re
import uuid
import zipfile
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.utils import secure_filename

from pipeline.grouping import normalize_key
from pipeline.supabase_db import _get_service_role_client
from pipeline.supabase_storage import BUCKET_NAME, delete_artifact_dir, download_original_with_service_role
from pipeline.validate import ALLOWED_REASON_CODES
from pipeline.grouping import normalize_key
from auth.app_admin import is_app_admin_email
from admin.assignments_service import (
    STANDARD_SCHOOL_OPTIONS,
    GRADE_LEVEL_ASSIGNMENT_SCHOOL_LABEL,
    calculate_assignment_batch_count,
    compute_ranking_results,
    compute_round2_ranking_results,
    get_grade_batch_progress,
    count_approved_essays_for_batch,
    delete_single_assignment_ranking,
    get_batch_bounds,
    get_assignment_with_reader,
    is_grade_level_assignment_school,
    list_approved_batches_by_school,
    list_approved_grade_level_summaries,
    list_approved_submissions_for_batch,
    list_assignment_submission_rows,
    list_assignment_finalist_rows,
    assignment_has_finalists,
    create_round2_assignment_from_top_results,
    list_assignments_for_reader,
    list_batch_assignments_for_school_grade,
    list_rankings_for_assignment,
    list_assignment_records,
    normalize_school_to_standard,
    parse_and_validate_reader_emails,
    add_batch_assignment,
    remove_assignment,
    resolve_or_create_readers,
    save_single_assignment_ranking,
    get_reader_by_email,
    replace_assignment_rankings,
    mark_assignment_ranking_completed,
    upsert_reader_name,
)
from utils.email_notification import (
    send_assignment_batch_email,
    send_reader_ranking_confirmation_email,
    send_reader_ranking_completion_email,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Human-readable labels for review reason codes
_REVIEW_REASON_MAP = {
    "MISSING_STUDENT_NAME": "Missing Student Name",
    "MISSING_SCHOOL_NAME": "Missing School Name",
    "MISSING_GRADE": "Missing Grade",
    "EMPTY_ESSAY": "Empty Essay (extraction failed)",
    "SHORT_ESSAY": "Short Essay (< 50 words)",
    "LOW_CONFIDENCE": "Low OCR Confidence",
    "OCR_LOW_CONFIDENCE": "Low OCR Confidence",
    "TEMPLATE_ONLY": "Template Only (no submission)",
    "FIELD_ATTRIBUTION_RISK": "Field Attribution Risk",
    "EXTRACTION_FALLBACK_USED": "Fallback extraction used (review fields)",
    "DOC_TYPE_UNKNOWN": "Document type unknown",
    "INVALID_GRADE_RANGE": "Invalid grade (not K–12 / recognized)",
    "UNKNOWN_SCHOOL": "School not in reference list",
    "POSSIBLE_FIELD_SWAP": "Possible student/school mix-up",
    "CONTENT_MISMATCH": "Content mismatch (wrong/partial page attached)",
    "BLANK_SUBMISSION": "Blank submission (no essay written)",
}


def _is_missing_assignment_schema_error(exc: Exception) -> bool:
    msg = str(exc or "").lower()
    return (
        "public.assignments" in msg
        or "public.readers" in msg
        or "public.essay_rankings" in msg
        or "batch_number" in msg
        or "total_batches" in msg
        or "ranking_completed_at" in msg
        or "ranking_completed_by_name" in msg
        or "ranking_completed_by_email" in msg
        or "assignment_finalists" in msg
        or "pgrst205" in msg
        or "could not find the table" in msg
    )


def _assignment_schema_error_response() -> tuple:
    return jsonify(
        {
            "error": "Assignment schema is missing in Supabase. Run migrations 008, 009, 010, 011, 013, and 014, then reload the page."
        }
    ), 500


def _format_review_reasons(reason_codes: str) -> str:
    """Convert review reason codes to human-readable format."""
    if not reason_codes or not (reason_codes or "").strip():
        return "—"
    codes = [
        c.strip()
        for c in (reason_codes or "").split(";")
        if c.strip() and c.strip() in ALLOWED_REASON_CODES
    ]
    readable = [_REVIEW_REASON_MAP.get(c, c.replace("_", " ").title()) for c in codes]
    return " • ".join(readable) if readable else "—"


def _coerce_reason_codes(reason_codes: str | None) -> set[str]:
    raw = (reason_codes or "").strip()
    if raw in {"[]", "{}", "null", "None"}:
        return set()
    return {
        c.strip()
        for c in (reason_codes or "").split(";")
        if c.strip() and c.strip() in ALLOWED_REASON_CODES
    }


def _row_has_reason_codes(row: dict) -> bool:
    return bool(_coerce_reason_codes(row.get("review_reason_codes")))


def _is_excluded_submission_row(row: dict) -> bool:
    codes = _coerce_reason_codes(row.get("review_reason_codes"))
    return bool(codes & {"CONTENT_MISMATCH", "BLANK_SUBMISSION"})


def _format_human_datetime(value: str | None) -> str:
    if not value:
        return "—"
    try:
        normalized = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%B %-d, %Y %-I:%M %p")
    except Exception:
        return str(value)


def _normalize_grade_value(grade_raw):
    grade_text = str(grade_raw or "").strip()
    if not grade_text:
        return None
    upper = grade_text.upper()
    if upper in {"K", "KINDER", "KINDERGARTEN"}:
        return "K"
    if upper in {"PRE-K", "PREK", "PRE-KINDERGARTEN"}:
        return "Pre-K"

    m = re.search(r"\d+", grade_text)
    if not m:
        return grade_text
    grade_num = int(m.group())
    if 1 <= grade_num <= 12:
        return grade_num
    return grade_text


def _sync_required_field_reason_codes(
    *,
    student_name: str | None,
    school_name: str | None,
    grade,
    existing_reason_codes: str | None,
) -> tuple[str, bool]:
    """Keep required-field reason codes aligned to current metadata."""
    reason_codes = _coerce_reason_codes(existing_reason_codes)
    reason_codes.discard("MISSING_STUDENT_NAME")
    reason_codes.discard("MISSING_SCHOOL_NAME")
    reason_codes.discard("MISSING_GRADE")

    if not (student_name or "").strip():
        reason_codes.add("MISSING_STUDENT_NAME")
    if not (school_name or "").strip():
        reason_codes.add("MISSING_SCHOOL_NAME")
    if grade is None or str(grade).strip() == "":
        reason_codes.add("MISSING_GRADE")

    normalized = ";".join(sorted(reason_codes))
    return normalized, bool(reason_codes)

# Admin token from env – set ADMIN_TOKEN in production
ADMIN_TOKEN = (os.environ.get("ADMIN_TOKEN") or "").strip()


def _require_admin() -> None:
    """Require valid admin auth: Bearer token or admin session. Aborts 403 if unauthorized."""
    # Check Bearer token
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token and token == ADMIN_TOKEN:
            return
    # Check session (set by /admin/login)
    if session.get("admin_authenticated"):
        return
    abort(403, description="Admin access required")


@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    """Admin login: validate token and set session."""
    if not ADMIN_TOKEN:
        return (
            "<h1>Admin Not Configured</h1><p>Set ADMIN_TOKEN in environment.</p>",
            500,
        )
    if request.method == "POST":
        token = (request.form.get("token") or "").strip()
        if token == ADMIN_TOKEN:
            session["admin_authenticated"] = True
            return redirect(url_for("admin.admin_dashboard"))
        return render_template("admin_login.html", error="Invalid token"), 401
    return render_template("admin_login.html")


@admin_bp.route("/logout")
def admin_logout():
    """Clear token-based admin session, or return to app if logged in as app admin."""
    if session.get("user_id") and is_app_admin_email(session.get("user_email")):
        return redirect(url_for("index"))
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin.admin_login"))


def _fetch_all_submissions(limit: int = 1000) -> list:
    """Fetch submissions using service role (bypasses RLS)."""
    sb = _get_service_role_client()
    if not sb:
        return []

    cap = min(max(int(limit), 1), 2000)
    select_full = (
        "submission_id, student_name, school_name, grade, filename, "
        "artifact_dir, needs_review, review_reason_codes, created_at, owner_user_id, "
        "parent_submission_id, chunk_index, chunk_page_start, chunk_page_end, "
        "is_chunk, is_container_parent, essay_linked_from_submission_id"
    )
    select_fallback = (
        "submission_id, student_name, school_name, grade, filename, "
        "artifact_dir, needs_review, review_reason_codes, created_at, owner_user_id, "
        "parent_submission_id, chunk_index, chunk_page_start, chunk_page_end, "
        "is_chunk, is_container_parent"
    )
    try:
        result = (
            sb.table("submissions")
            .select(select_full)
            .order("created_at", desc=True)
            .limit(cap)
            .execute()
        )
    except Exception:
        try:
            result = (
                sb.table("submissions")
                .select(select_fallback)
                .order("created_at", desc=True)
                .limit(cap)
                .execute()
            )
        except Exception:
            return []
    rows = result.data if result.data else []
    return [row for row in rows if not _is_excluded_submission_row(row)]


def _apply_school_grade_filters(
    rows: list,
    school: str,
    grade: str,
    status: str = "",
    submission_id: str = "",
) -> list:
    """Filter rows by normalized school/grade and optional status."""
    school_key = normalize_key(school) if (school or "").strip() else ""
    grade_key = normalize_key(grade) if (grade or "").strip() else ""
    status_key = (status or "").strip().lower()
    submission_key = str(submission_id or "").strip().lower()

    def _row_status(r: dict) -> str:
        if r.get("is_container_parent"):
            return "needs_review"
        has_all = bool(
            (r.get("student_name") or "").strip()
            and (r.get("school_name") or "").strip()
            and str(r.get("grade") or "").strip()
        )
        has_reason = _row_has_reason_codes(r)
        if has_all and not has_reason and not r.get("needs_review"):
            return "approved"
        return "needs_review"

    if not school_key and not grade_key:
        out = []
        for r in rows:
            if status_key == "approved" and _row_status(r) != "approved":
                continue
            if status_key == "needs_review" and _row_status(r) != "needs_review":
                continue
            if submission_key and str(r.get("submission_id") or "").strip().lower() != submission_key:
                continue
            out.append(r)
        return out
    out = []
    for r in rows:
        if status_key == "approved" and _row_status(r) != "approved":
            continue
        if status_key == "needs_review" and _row_status(r) != "needs_review":
            continue
        if submission_key and str(r.get("submission_id") or "").strip().lower() != submission_key:
            continue
        normalized_school = normalize_school_to_standard(r.get("school_name"))
        if school_key and normalize_key(normalized_school or "") != school_key:
            continue
        if grade_key and normalize_key(str(r.get("grade") or "")) != grade_key:
            continue
        out.append(r)
    return out


def _apply_multi_entry_only_filter(all_rows: list, submissions: list, multi_entry_only: bool) -> list:
    """When multi_entry_only, keep only rows whose filename appears more than once in all_rows."""
    if not multi_entry_only:
        return submissions
    fn_counts: Counter[str] = Counter()
    for r in all_rows:
        fn = (r.get("filename") or "").strip()
        if fn:
            fn_counts[fn] += 1
    multi_filenames = {fn for fn, n in fn_counts.items() if n > 1}
    return [s for s in submissions if (s.get("filename") or "").strip() in multi_filenames]


def _apply_duplicates_only_filter(submissions: list, duplicates_only: bool) -> list:
    """
    When True, keep only rows that share the same duplicate fingerprint as at least one other
    eligible standalone row (same logic as Remove duplicate uploads). Chunk rows and container
    parents are excluded from grouping.
    """
    if not duplicates_only:
        return submissions
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for row in submissions:
        if not _eligible_for_duplicate_scan(row):
            continue
        fp = _duplicate_fingerprint(row)
        if not fp[3]:
            continue
        groups.setdefault(fp, []).append(row)
    dup_ids: set[str] = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        for m in members:
            sid = str(m.get("submission_id") or "").strip()
            if sid:
                dup_ids.add(sid)
    return [r for r in submissions if str(r.get("submission_id") or "").strip() in dup_ids]


def _duplicate_fingerprint(row: dict) -> tuple[str, str, str, str]:
    stud = normalize_key((row.get("student_name") or "").strip())
    school_raw = row.get("school_name")
    school = normalize_key(normalize_school_to_standard(school_raw) or (school_raw or "").strip())
    grade = normalize_key(str(row.get("grade") or "").strip())
    fn = normalize_key((row.get("filename") or "").strip())
    return (stud, school, grade, fn)


def _eligible_for_duplicate_scan(row: dict) -> bool:
    """Standalone uploads only — not chunks, linked essays, or multi-entry container parents."""
    if row.get("parent_submission_id") or row.get("is_chunk"):
        return False
    if row.get("essay_linked_from_submission_id"):
        return False
    if row.get("is_container_parent"):
        return False
    if not (row.get("filename") or "").strip():
        return False
    return True


def _parse_created_at_ts(row: dict) -> float:
    try:
        raw = row.get("created_at")
        if not raw:
            return 0.0
        normalized = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return float(dt.timestamp())
    except Exception:
        return 0.0


def _plan_duplicate_removals(rows: list) -> tuple[list[dict], list[dict]]:
    """
    Group by student + school + grade + filename; keep newest created_at, mark older rows for deletion.
    Returns (group_summaries, rows_to_delete).
    """
    groups: dict[tuple[str, str, str, str], list[dict]] = {}
    for row in rows:
        if not _eligible_for_duplicate_scan(row):
            continue
        fp = _duplicate_fingerprint(row)
        if not fp[3]:
            continue
        groups.setdefault(fp, []).append(row)

    summaries: list[dict] = []
    to_delete: list[dict] = []
    for fp, members in groups.items():
        if len(members) < 2:
            continue
        sorted_members = sorted(members, key=_parse_created_at_ts, reverse=True)
        keep = sorted_members[0]
        dupes = sorted_members[1:]
        to_delete.extend(dupes)
        created_raw = keep.get("created_at")
        kept_date_display = ""
        if created_raw:
            kept_date_display = str(created_raw).replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(kept_date_display)
                kept_date_display = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                kept_date_display = str(created_raw)[:19].replace("T", " ")
        summaries.append(
            {
                "kept_submission_id": keep.get("submission_id"),
                "kept_created_at": keep.get("created_at"),
                "kept_date_display": kept_date_display,
                "student_name": (keep.get("student_name") or "").strip(),
                "school_name": (keep.get("school_name") or "").strip(),
                "grade": "" if keep.get("grade") is None else str(keep.get("grade")).strip(),
                "deleted_submission_ids": [d.get("submission_id") for d in dupes],
                "deleted_count": len(dupes),
                "filename": (keep.get("filename") or "").strip(),
            }
        )
    return summaries, to_delete


def _admin_delete_submission_row(sb, row: dict) -> tuple[bool, str | None]:
    """Remove storage files then DB row (service role)."""
    sid = str(row.get("submission_id") or "").strip()
    if not sid:
        return False, "missing submission_id"
    ad = (row.get("artifact_dir") or "").strip()
    if ad and not delete_artifact_dir(ad, sb):
        return False, "storage delete failed"
    try:
        sb.table("submissions").delete().eq("submission_id", sid).execute()
        return True, None
    except Exception as e:
        return False, str(e)


_MAX_PEER_FETCH = 5000
_PEER_SELECT = (
    "submission_id, student_name, school_name, grade, filename, created_at, "
    "artifact_dir, parent_submission_id, is_chunk, essay_linked_from_submission_id, is_container_parent"
)


def _fetch_submission_by_id(sb, submission_id: str) -> dict | None:
    sid = str(submission_id or "").strip()
    if not sid:
        return None
    try:
        res = (
            sb.table("submissions")
            .select(_PEER_SELECT)
            .eq("submission_id", sid)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return None


def _fetch_peer_rows_same_fingerprint(sb, sample_row: dict) -> list:
    """
    All DB rows that share the same duplicate fingerprint as sample_row (by filename query + filter).
    Uses exact filename match first, then case-insensitive match if fewer than two peers.
    """
    fn = (sample_row.get("filename") or "").strip()
    if not fn:
        return []
    target_fp = _duplicate_fingerprint(sample_row)
    merged: dict[str, dict] = {}

    def _merge_from_rows(rows: list | None) -> None:
        for r in rows or []:
            sid = str(r.get("submission_id") or "").strip()
            if sid:
                merged[sid] = r

    try:
        res = (
            sb.table("submissions")
            .select(_PEER_SELECT)
            .eq("filename", fn)
            .limit(_MAX_PEER_FETCH)
            .execute()
        )
        _merge_from_rows(res.data)
    except Exception:
        pass

    matched = [
        r
        for r in merged.values()
        if _duplicate_fingerprint(r) == target_fp and _eligible_for_duplicate_scan(r)
    ]
    if len(matched) >= 2:
        return matched

    try:
        res2 = (
            sb.table("submissions")
            .select(_PEER_SELECT)
            .ilike("filename", fn)
            .limit(_MAX_PEER_FETCH)
            .execute()
        )
        _merge_from_rows(res2.data)
    except Exception:
        pass

    return [
        r
        for r in merged.values()
        if _duplicate_fingerprint(r) == target_fp and _eligible_for_duplicate_scan(r)
    ]


def _selected_duplicate_deletes_for_group(
    peers: list[dict],
    selected_ids_in_group: set[str],
) -> tuple[list[str], list[dict]]:
    """
    peers: all rows sharing a fingerprint. selected_ids_in_group: submission IDs the user checked.
    Returns (submission_ids safe to delete, skipped with reason).
    Never deletes the newest row (keeper); requires at least two peers to delete anything.
    """
    skipped: list[dict] = []
    if len(peers) < 2:
        for sid in selected_ids_in_group:
            skipped.append(
                {
                    "submission_id": sid,
                    "reason": "not a duplicate (no other matching row for this student/school/grade/file)",
                }
            )
        return [], skipped

    peers_sorted = sorted(peers, key=_parse_created_at_ts, reverse=True)
    keeper_id = str(peers_sorted[0].get("submission_id") or "").strip()
    peer_ids = {str(p.get("submission_id") or "").strip() for p in peers_sorted}

    to_delete: list[str] = []
    for sid in selected_ids_in_group:
        sid = str(sid).strip()
        if sid not in peer_ids:
            skipped.append({"submission_id": sid, "reason": "submission not in duplicate set"})
            continue
        if sid == keeper_id:
            skipped.append(
                {
                    "submission_id": sid,
                    "reason": "cannot delete (newest submission — one copy must remain; unselect this row)",
                }
            )
            continue
        to_delete.append(sid)

    return to_delete, skipped


def _resolve_delete_selected_duplicates(sb, selected_ids: list[str]) -> tuple[list[dict], list[dict]]:
    """
    Resolve which selected rows may be deleted. Returns (rows_to_delete, skipped).
    Only deletes older duplicate rows; never the newest per fingerprint; never if only one peer exists.
    """
    cleaned = sorted({str(s).strip() for s in selected_ids if str(s).strip()})
    if not cleaned:
        return [], [{"submission_id": "", "reason": "no submission_ids provided"}]

    rows_by_id: dict[str, dict] = {}
    skipped: list[dict] = []

    for sid in cleaned:
        row = _fetch_submission_by_id(sb, sid)
        if not row:
            skipped.append({"submission_id": sid, "reason": "submission not found"})
            continue
        if not _eligible_for_duplicate_scan(row):
            skipped.append(
                {
                    "submission_id": sid,
                    "reason": "not eligible (chunk, linked essay, container parent, or missing filename)",
                }
            )
            continue
        rows_by_id[sid] = row

    by_fp: dict[tuple, list[str]] = defaultdict(list)
    for sid, row in rows_by_id.items():
        by_fp[_duplicate_fingerprint(row)].append(sid)

    to_delete_rows: list[dict] = []
    seen_delete: set[str] = set()

    for _fp, sids in by_fp.items():
        sample = rows_by_id[sids[0]]
        peers = _fetch_peer_rows_same_fingerprint(sb, sample)
        selected_set = set(sids)
        ids_ok, part_skipped = _selected_duplicate_deletes_for_group(peers, selected_set)
        skipped.extend(part_skipped)
        for did in ids_ok:
            if did not in seen_delete:
                seen_delete.add(did)
                to_delete_rows.append(rows_by_id[did])

    return to_delete_rows, skipped


def _submissions_for_duplicate_scan(
    *,
    limit: int,
    school: str,
    grade: str,
    status: str,
    submission_id: str,
    multi_entry: str,
) -> tuple[list, list]:
    """Return (all_rows, filtered_submissions) using the same rules as the dashboard."""
    cap = min(max(int(limit), 1), 2000)
    all_rows = _fetch_all_submissions(limit=cap)
    submissions = _apply_school_grade_filters(all_rows, school, grade, status, submission_id)
    multi_entry_only = (multi_entry or "").strip().lower() in ("1", "true", "yes", "on")
    submissions = _apply_multi_entry_only_filter(all_rows, submissions, multi_entry_only)
    return all_rows, submissions


# Max originals in one ZIP (memory + timeout safety during contest)
_ADMIN_BULK_DOWNLOAD_MAX = 50
_ADMIN_BULK_DOWNLOAD_MAX_BYTES = 120 * 1024 * 1024  # 120 MB soft cap
_READER_PORTAL_TOKEN_SALT = "reader-portal-access"
_READER_PORTAL_MAX_AGE_SECONDS = 60 * 60 * 24 * 14


def _assignment_zip_cache_dir() -> Path:
    root = Path(current_app.instance_path or "/tmp")
    cache_dir = root / "assignment_zip_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _assignment_zip_cache_path(
    *, school: str, grade: str, batch_number: int, submission_ids: list[str]
) -> Path:
    key_source = "|".join(
        [
            str(school or "").strip(),
            str(grade or "").strip(),
            str(batch_number),
            ",".join(submission_ids),
        ]
    )
    digest = hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:16]
    safe_school = secure_filename(school) or "school"
    safe_grade = secure_filename(str(grade)) or "grade"
    filename = f"{safe_school}_grade_{safe_grade}_batch_{batch_number}_{digest}.zip"
    return _assignment_zip_cache_dir() / filename


def _build_zip_for_submission_rows(
    sb,
    rows: list[dict],
    *,
    max_files: int = _ADMIN_BULK_DOWNLOAD_MAX,
    max_bytes: int = _ADMIN_BULK_DOWNLOAD_MAX_BYTES,
) -> tuple[io.BytesIO, list[str], int]:
    """
    Build a ZIP from submission rows containing artifact_dir/filename/submission_id.
    """
    buffer = io.BytesIO()
    total_bytes = 0
    skipped: list[str] = []
    added_count = 0
    used_arcnames: set[str] = set()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows[:max_files]:
            submission_id = str(row.get("submission_id") or "").strip()
            artifact_dir = row.get("artifact_dir", "")
            filename = row.get("filename", "unknown.pdf")
            if not submission_id or not artifact_dir:
                skipped.append(submission_id or "(missing-id)")
                continue
            file_bytes, used_path = download_original_with_service_role(sb, artifact_dir, filename)
            if not file_bytes:
                skipped.append(submission_id)
                continue
            if total_bytes + len(file_bytes) > max_bytes:
                skipped.append(submission_id)
                continue
            total_bytes += len(file_bytes)
            ext = Path(used_path or filename).suffix or ".bin"
            base = secure_filename(filename) or "file"
            stem = Path(base).stem
            arcname = f"{submission_id}_{stem}{ext}"
            if arcname in used_arcnames:
                arcname = f"{submission_id}_{stem}_{len(used_arcnames)}{ext}"
            used_arcnames.add(arcname)
            zf.writestr(arcname, file_bytes)
            added_count += 1

    if added_count <= 0:
        raise FileNotFoundError("No files could be added to ZIP (missing storage or paths).")

    buffer.seek(0)
    return buffer, skipped, added_count


def _build_assignment_batch_payload(sb, *, school: str, grade: str, batch_number: int) -> dict:
    """
    Resolve approved submissions for one batch (school+grade or grade-level across all schools) and package ZIP data.
    """
    submissions = list_approved_submissions_for_batch(sb, school=school, grade=grade)
    total_essays = len(submissions)
    total_batches = calculate_assignment_batch_count(total_essays)
    scope_label = f"Grade {grade} (all schools)" if is_grade_level_assignment_school(school) else f"{school}, Grade {grade}"
    if total_batches <= 0:
        raise ValueError(f"No approved essays found for {scope_label}.")
    if batch_number < 1 or batch_number > total_batches:
        raise ValueError(f"Batch {batch_number} is out of range for {scope_label}.")

    start, end = get_batch_bounds(batch_number, total_essays)
    batch_rows = submissions[start:end]
    if not batch_rows:
        raise ValueError(f"Batch {batch_number} has no approved essays.")

    submission_ids = [
        str(row.get("submission_id") or "").strip()
        for row in batch_rows
        if str(row.get("submission_id") or "").strip()
    ]
    cache_path = _assignment_zip_cache_path(
        school=school,
        grade=grade,
        batch_number=batch_number,
        submission_ids=submission_ids,
    )
    if is_grade_level_assignment_school(school):
        safe_school = "grade_level_all_schools"
    else:
        safe_school = secure_filename(school) or "school"
    safe_grade = secure_filename(str(grade)) or "grade"
    zip_filename = f"{safe_school}_grade_{safe_grade}_batch_{batch_number}_of_{total_batches}.zip"
    if cache_path.exists():
        return {
            "totalEssays": total_essays,
            "totalBatches": total_batches,
            "batchNumber": batch_number,
            "batchEssayCount": len(batch_rows),
            "zipFilename": zip_filename,
            "zipBytes": cache_path.read_bytes(),
            "skippedCount": 0,
            "cachePath": str(cache_path),
            "fromCache": True,
        }

    zip_buffer, skipped, added_count = _build_zip_for_submission_rows(sb, batch_rows)
    zip_bytes = zip_buffer.getvalue()
    cache_path.write_bytes(zip_bytes)
    return {
        "totalEssays": total_essays,
        "totalBatches": total_batches,
        "batchNumber": batch_number,
        "batchEssayCount": len(batch_rows),
        "zipFilename": zip_filename,
        "zipBytes": zip_bytes,
        "skippedCount": len(skipped),
        "zipEntryCount": added_count,
        "cachePath": str(cache_path),
        "fromCache": False,
    }


def _reader_portal_serializer() -> URLSafeTimedSerializer:
    secret = (
        os.environ.get("FLASK_SECRET_KEY")
        or os.environ.get("SECRET_KEY")
        or current_app.config.get("SECRET_KEY")
        or "reader-portal-secret"
    )
    return URLSafeTimedSerializer(secret_key=secret, salt=_READER_PORTAL_TOKEN_SALT)


def _generate_reader_portal_token(reader_email: str) -> str:
    return _reader_portal_serializer().dumps({"email": str(reader_email or "").strip().lower()})


def _verify_reader_portal_token(token: str) -> str | None:
    if not token:
        return None
    try:
        payload = _reader_portal_serializer().loads(token, max_age=_READER_PORTAL_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    email = str((payload or {}).get("email") or "").strip().lower()
    return email or None


def _reader_portal_url(token: str) -> str:
    base_url = (os.environ.get("APP_URL") or "").strip().rstrip("/")
    if not base_url:
        base_url = request.url_root.rstrip("/")
    return f"{base_url}/admin/reader-access?token={token}"


def _verified_reader_email_from_request(token: str) -> str | None:
    token_email = _verify_reader_portal_token(token)
    session_email = str(session.get("reader_portal_email") or "").strip().lower()
    if not token_email or token_email != session_email:
        return None
    return token_email


def _load_verified_assignment(sb, *, assignment_id: int, token: str) -> tuple[str | None, dict | None]:
    reader_email = _verified_reader_email_from_request(token)
    if not reader_email:
        return None, None

    assignment = get_assignment_with_reader(sb, assignment_id)
    if not assignment:
        return reader_email, None

    reader = assignment.get("readers") or {}
    if str(reader.get("email") or "").strip().lower() != reader_email:
        abort(403, description="Assignment does not belong to this reader.")

    return reader_email, assignment


def _resolve_assignment_essay_rows(sb, assignment: dict) -> tuple[list[dict], bool]:
    assignment_id = int(assignment.get("id") or 0)
    has_finalists = assignment_has_finalists(sb, assignment_id=assignment_id)
    if has_finalists:
        return list_assignment_finalist_rows(sb, assignment_id=assignment_id), True
    return (
        list_assignment_submission_rows(
            sb,
            school=str(assignment.get("school_name") or ""),
            grade=str(assignment.get("grade") or ""),
            batch_number=int(assignment.get("batch_number") or 1),
        ),
        False,
    )


def _validate_forced_rankings(essay_rows: list[dict], ranking_map: dict[str, int]) -> tuple[bool, str | None]:
    expected_ids = [
        str(row.get("submission_id") or "").strip()
        for row in essay_rows
        if str(row.get("submission_id") or "").strip()
    ]
    submitted_ids = sorted(ranking_map.keys())
    if sorted(expected_ids) != submitted_ids:
        return False, "You must rank every assigned essay exactly once."

    expected_ranks = list(range(1, len(expected_ids) + 1))
    actual_ranks = sorted(ranking_map.values())
    if actual_ranks != expected_ranks:
        return False, "Ranks must use every position from 1 through N with no duplicates."

    return True, None


def _warm_assignment_zip_cache(app, *, school: str, grade: str, batch_number: int) -> None:
    try:
        with app.app_context():
            sb = _get_service_role_client()
            if not sb:
                return
            _build_assignment_batch_payload(
                sb,
                school=school,
                grade=grade,
                batch_number=batch_number,
            )
    except Exception as exc:
        app.logger.warning(
            "Failed to warm assignment ZIP cache for %s grade %s batch %s: %s",
            school,
            grade,
            batch_number,
            exc,
        )


def _failure_reason_stats(rows: list) -> dict:
    """
    Aggregate review reason codes for contest triage.
    Counts are per-code occurrences (one row can increment multiple codes).
    Treat as approved when all data present and no reason codes (avoids stale needs_review).
    """
    needs = 0
    appr = 0
    no_code = 0
    code_counts: Counter[str] = Counter()
    for r in rows:
        has_all = r.get("student_name") and r.get("school_name") and r.get("grade")
        raw = (r.get("review_reason_codes") or "").strip()
        # All data + no reason → approved (even if DB says needs_review)
        if has_all and not raw:
            appr += 1
            continue
        if r.get("needs_review"):
            needs += 1
            if not raw:
                no_code += 1
            else:
                for part in raw.split(";"):
                    c = part.strip()
                    if c in ALLOWED_REASON_CODES:
                        code_counts[c] += 1
        else:
            appr += 1
    codes_out = [
        {
            "code": code,
            "count": cnt,
            "label": _REVIEW_REASON_MAP.get(code, code.replace("_", " ").title()),
        }
        for code, cnt in code_counts.most_common()
    ]
    return {
        "needs_review_count": needs,
        "approved_count": appr,
        "missing_reason_codes_count": no_code,
        "codes": codes_out,
        "total_rows": len(rows),
    }


def _duplicate_filename_hints(rows: list, top_n: int = 12) -> list[dict]:
    """Same filename with multiple rows → re-uploads / chunks / duplicates."""
    fn_counts: Counter[str] = Counter()
    for r in rows:
        fn = (r.get("filename") or "").strip() or "(no filename)"
        fn_counts[fn] += 1
    out = []
    for fn, n in fn_counts.most_common(top_n * 2):
        if n < 2:
            break
        out.append({"filename": fn if len(fn) <= 80 else fn[:77] + "...", "count": n})
        if len(out) >= top_n:
            break
    return out


def _distinct_schools_and_grades(rows: list) -> tuple[list[str], list[str]]:
    schools = list(STANDARD_SCHOOL_OPTIONS)
    grades = sorted(
        {str(r.get("grade") or "").strip() for r in rows if str(r.get("grade") or "").strip()},
        key=lambda g: (not str(g).isdigit(), str(g).casefold()),
    )
    return schools, grades


@admin_bp.route("/dashboard")
def admin_dashboard():
    """Admin dashboard: view all submissions with optional school/grade filters."""
    _require_admin()

    fetch_limit = min(int(request.args.get("limit", 1000)), 2000)
    all_rows = _fetch_all_submissions(limit=fetch_limit)

    selected_school = (request.args.get("school") or "").strip()
    selected_grade = (request.args.get("grade") or "").strip()
    selected_status = (request.args.get("status") or "").strip()
    selected_submission_id = (request.args.get("submission_id") or "").strip()
    selected_multi_entry = (request.args.get("multi_entry") or "").strip()
    multi_entry_only = selected_multi_entry in ("1", "true", "yes", "on")
    selected_duplicates = (request.args.get("duplicates") or "").strip()
    duplicates_only = selected_duplicates in ("1", "true", "yes", "on")

    school_options, grade_options = _distinct_schools_and_grades(all_rows)
    submissions = _apply_school_grade_filters(
        all_rows,
        selected_school,
        selected_grade,
        selected_status,
        selected_submission_id,
    )
    submissions = _apply_multi_entry_only_filter(all_rows, submissions, multi_entry_only)
    submissions = _apply_duplicates_only_filter(submissions, duplicates_only)
    for s in submissions:
        has_all = bool(
            (s.get("student_name") or "").strip()
            and (s.get("school_name") or "").strip()
            and str(s.get("grade") or "").strip()
        )
        has_reason = _row_has_reason_codes(s)
        s["has_reason"] = has_reason
        s["status"] = "approved" if (has_all and not has_reason and not s.get("needs_review")) else "needs_review"

    return render_template(
        "admin_dashboard.html",
        submissions=submissions,
        total=len(submissions),
        total_loaded=len(all_rows),
        school_options=school_options,
        grade_options=grade_options,
        selected_school=selected_school,
        selected_grade=selected_grade,
        selected_status=selected_status,
        selected_submission_id=selected_submission_id,
        selected_multi_entry=selected_multi_entry,
        selected_duplicates=selected_duplicates,
        fetch_limit=fetch_limit,
        format_review_reasons=_format_review_reasons,
    )


@admin_bp.route("/submissions/duplicate-report", methods=["POST"])
def admin_duplicate_report():
    """JSON: count duplicate groups and rows that would be removed (same filters as dashboard)."""
    _require_admin()
    payload = request.get_json(silent=True) or {}
    limit = min(int(payload.get("limit", 1000)), 2000)
    school = (payload.get("school") or "").strip()
    grade = (payload.get("grade") or "").strip()
    status = (payload.get("status") or "").strip()
    submission_id = (payload.get("submission_id") or "").strip()
    multi_entry = (payload.get("multi_entry") or "").strip()

    _, submissions = _submissions_for_duplicate_scan(
        limit=limit,
        school=school,
        grade=grade,
        status=status,
        submission_id=submission_id,
        multi_entry=multi_entry,
    )
    summaries, to_delete = _plan_duplicate_removals(submissions)
    summaries.sort(
        key=lambda s: (
            (s.get("student_name") or "").casefold(),
            (s.get("filename") or "").casefold(),
        )
    )
    preview = summaries[:40]
    return jsonify(
        {
            "duplicate_groups": len(summaries),
            "rows_to_delete": len(to_delete),
            "preview_groups": preview,
            "preview_truncated": len(summaries) > len(preview),
        }
    )


@admin_bp.route("/submissions/delete-duplicates", methods=["POST"])
def admin_delete_duplicates():
    """
    Delete only checked duplicate rows: requires submission_ids.
    Never deletes the newest submission for a student/school/grade/file (one copy always remains).
    Skips chunks, linked rows, and container parents.
    """
    _require_admin()
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("submission_ids")
    if not isinstance(raw_ids, list):
        return jsonify({"error": "submission_ids is required (array of submission IDs to delete)."}), 400
    submission_ids = [str(x).strip() for x in raw_ids if str(x).strip()]
    if not submission_ids:
        return jsonify({"error": "Select at least one submission (checkbox) to delete."}), 400

    dry_run = bool(payload.get("dry_run"))
    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    to_delete, skipped = _resolve_delete_selected_duplicates(sb, submission_ids)

    if dry_run:
        return jsonify(
            {
                "dry_run": True,
                "would_delete_count": len(to_delete),
                "would_delete_ids": [str(r.get("submission_id") or "").strip() for r in to_delete],
                "skipped": skipped,
            }
        )

    deleted_ids: list[str] = []
    errors: list[dict] = []
    for row in to_delete:
        sid = str(row.get("submission_id") or "").strip()
        ok, err = _admin_delete_submission_row(sb, row)
        if ok:
            deleted_ids.append(sid)
        else:
            errors.append({"submission_id": sid, "error": err or "delete failed"})

    return jsonify(
        {
            "success": not errors,
            "deleted_count": len(deleted_ids),
            "deleted_submission_ids": deleted_ids,
            "skipped": skipped,
            "errors": errors,
        }
    )


@admin_bp.route("/assignments", methods=["GET"])
def admin_assignments():
    """Admin assignments page shell."""
    _require_admin()
    return render_template("admin_assignments.html")


def _list_ranking_filter_options(sb) -> tuple[list[str], list[str]]:
    """Return distinct school and grade values that currently have saved rankings."""
    rows = (
        sb.table("essay_rankings")
        .select("school_name, grade")
        .limit(10000)
        .execute()
        .data
        or []
    )
    schools = sorted(
        {
            str(row.get("school_name") or "").strip()
            for row in rows
            if str(row.get("school_name") or "").strip()
        },
        key=str.casefold,
    )
    grades = sorted(
        {
            str(row.get("grade") or "").strip()
            for row in rows
            if str(row.get("grade") or "").strip()
        },
        key=lambda g: (not str(g).isdigit(), str(g).casefold()),
    )
    return schools, grades


def _list_round1_reader_choices(sb, *, grade: str, school: str | None = None) -> list[dict[str, str]]:
    """
    Return unique reader choices from Round 1 assignments for a grade/school scope.
    Round 2 finalist assignments are excluded.
    """
    query = (
        sb.table("assignments")
        .select("id, school_name, grade, readers(id, email, name)")
        .eq("grade", str(grade).strip())
        .limit(2000)
    )
    if school:
        query = query.eq("school_name", str(school).strip())
    rows = query.execute().data or []
    if not rows:
        return []

    assignment_ids = [
        int(row.get("id"))
        for row in rows
        if row.get("id") is not None
    ]
    finalist_assignment_ids: set[int] = set()
    if assignment_ids:
        finalist_rows = (
            sb.table("assignment_finalists")
            .select("assignment_id")
            .in_("assignment_id", assignment_ids)
            .limit(max(1, len(assignment_ids) * 20))
            .execute()
            .data
            or []
        )
        finalist_assignment_ids = {
            int(row.get("assignment_id"))
            for row in finalist_rows
            if row.get("assignment_id") is not None
        }

    by_email: dict[str, dict[str, str]] = {}
    for row in rows:
        assignment_id = int(row.get("id") or 0)
        if assignment_id in finalist_assignment_ids:
            continue
        reader = row.get("readers") or {}
        email = str(reader.get("email") or "").strip().lower()
        if not email:
            continue
        name = str(reader.get("name") or "").strip()
        by_email[email] = {
            "email": email,
            "name": name,
            "label": f"{name} ({email})" if name else email,
        }
    return sorted(by_email.values(), key=lambda item: (str(item.get("name") or "").casefold(), item["email"]))


@admin_bp.route("/rankings", methods=["GET"])
def admin_rankings():
    """Admin rankings page with winners and all reader score breakdowns."""
    _require_admin()

    sb = _get_service_role_client()
    if not sb:
        return render_template(
            "admin_rankings.html",
            selected_grade="",
            selected_school="",
            grade_options=[],
            school_options=[],
            sections=[],
            schema_error="Database not configured.",
        )

    selected_grade = str(request.args.get("grade") or "").strip()
    selected_school = str(request.args.get("school") or "").strip()

    try:
        school_options, grade_options = _list_ranking_filter_options(sb)
        grades_to_render = [selected_grade] if selected_grade else grade_options
        sections = []
        for grade in grades_to_render:
            results = compute_ranking_results(sb, grade=grade, school=selected_school or None)
            round2_results = compute_round2_ranking_results(sb, grade=grade, school=selected_school or None)
            if not results and not round2_results:
                continue
            school_scope = selected_school or (results[0].get("schoolName") if results else None)
            round1_reader_choices = _list_round1_reader_choices(
                sb,
                grade=grade,
                school=str(school_scope or "").strip() or None,
            )
            top_ten = results[:10]
            batch_progress = get_grade_batch_progress(sb, grade=grade, school=selected_school or None)
            sections.append(
                {
                    "grade": grade,
                    "winner": top_ten[0] if top_ten else None,
                    "topTen": top_ten,
                    "round2Winner": round2_results[0] if round2_results else None,
                    "round2Results": round2_results,
                    "round1ReaderChoices": round1_reader_choices,
                    "batchProgress": batch_progress,
                    "results": results,
                }
            )
        return render_template(
            "admin_rankings.html",
            selected_grade=selected_grade,
            selected_school=selected_school,
            grade_options=grade_options,
            school_options=school_options,
            sections=sections,
            schema_error="",
        )
    except Exception as exc:
        if _is_missing_assignment_schema_error(exc):
            return render_template(
                "admin_rankings.html",
                selected_grade=selected_grade,
                selected_school=selected_school,
                grade_options=[],
                school_options=[],
                sections=[],
                schema_error="Ranking schema is missing in Supabase. Run migrations 008, 009, 010, 011, 013, and 014.",
            )
        raise


@admin_bp.route("/essays/summary", methods=["GET"])
def essays_summary():
    """API: approved essay summary for a grade-level batch or a single-school+grade batch."""
    _require_admin()

    scope = (request.args.get("scope") or "").strip().lower()
    school = (request.args.get("school") or "").strip()
    grade = (request.args.get("grade") or "").strip()
    if not grade:
        return jsonify({"error": "Grade is required."}), 400
    if scope == "grade":
        school = GRADE_LEVEL_ASSIGNMENT_SCHOOL_LABEL
    elif not school:
        return jsonify({"error": "School is required unless scope=grade."}), 400

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    try:
        approved_count = count_approved_essays_for_batch(sb, school=school, grade=grade)
        batch_count = calculate_assignment_batch_count(approved_count)
        existing_assignments = list_batch_assignments_for_school_grade(sb, school=school, grade=grade)
        assignments_by_batch: dict[int, list[dict]] = {}
        for row in existing_assignments:
            batch_key = int(row.get("batchNumber") or 0)
            assignments_by_batch.setdefault(batch_key, []).append(row)
        batches = []
        for batch_number in range(1, batch_count + 1):
            start, end = get_batch_bounds(batch_number, approved_count)
            assigned_rows = assignments_by_batch.get(batch_number) or []
            reader_emails = [str(r.get("readerEmail") or "").strip() for r in assigned_rows if str(r.get("readerEmail") or "").strip()]
            reader_names = [str(r.get("readerName") or "").strip() for r in assigned_rows if str(r.get("readerName") or "").strip()]
            batches.append(
                {
                    "batchNumber": batch_number,
                    "startEssay": start + 1 if approved_count else 0,
                    "endEssay": end,
                    "essayCount": max(0, end - start),
                    "readerEmails": reader_emails,
                    "readerNames": reader_names,
                    "assignedCount": len(reader_emails),
                }
            )
        return jsonify(
            {
                "school": school,
                "grade": grade,
                "scope": "grade" if is_grade_level_assignment_school(school) else "school",
                "approvedCount": approved_count,
                "batchCount": batch_count,
                "batches": batches,
            }
        )
    except Exception as exc:
        return jsonify({"error": f"Failed to fetch batch summary: {exc}"}), 500


@admin_bp.route("/essays/batches", methods=["GET"])
def essays_batches():
    """API: list approved essay batches by school, plus grade-level aggregates for assignment."""
    _require_admin()

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    try:
        batches = list_approved_batches_by_school(sb)
        grade_levels = list_approved_grade_level_summaries(sb)
        return jsonify({"schools": batches, "gradeLevels": grade_levels})
    except Exception as exc:
        return jsonify({"error": f"Failed to fetch school batches: {exc}"}), 500


@admin_bp.route("/assign-and-send", methods=["POST"])
def assign_and_send():
    """API: resolve readers and create grade-level or school+grade batch assignments."""
    _require_admin()

    payload = request.get_json(silent=True) or {}
    scope = str(payload.get("scope") or "").strip().lower()
    school = str(payload.get("school") or "").strip()
    grade = str(payload.get("grade") or "").strip()
    if scope == "grade":
        school = GRADE_LEVEL_ASSIGNMENT_SCHOOL_LABEL
    elif not school:
        return jsonify({"error": "School is required unless scope is grade."}), 400
    if not grade:
        return jsonify({"error": "Grade is required."}), 400

    batch_number_raw = payload.get("batchNumber")
    try:
        batch_number = int(batch_number_raw)
    except Exception:
        return jsonify({"error": "Batch number is required."}), 400

    reader_emails, invalid_emails = parse_and_validate_reader_emails(payload.get("readerEmail"))
    if invalid_emails:
        return jsonify(
            {
                "error": "One or more reader emails are invalid.",
                "invalidEmails": invalid_emails,
            }
        ), 400
    if not reader_emails:
        return jsonify({"error": "At least one valid reader email is required."}), 400

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    try:
        essay_count = count_approved_essays_for_batch(sb, school=school, grade=grade)
        if essay_count <= 0:
            err_scope = f"Grade {grade} (all schools)" if is_grade_level_assignment_school(school) else f"{school}, Grade {grade}"
            return jsonify({"error": f"No approved essays found for {err_scope}."}), 400
        batch_count = calculate_assignment_batch_count(essay_count)
        if len(reader_emails) != 1:
            return jsonify(
                {
                    "error": "Enter exactly one reader email for the selected batch.",
                    "essayCount": essay_count,
                    "batchCount": batch_count,
                }
            ), 400
        if batch_number < 1 or batch_number > batch_count:
            err_scope = f"Grade {grade} (all schools)" if is_grade_level_assignment_school(school) else f"{school}, Grade {grade}"
            return jsonify({"error": f"Batch {batch_number} is out of range for {err_scope}."}), 400

        start, end = get_batch_bounds(batch_number, essay_count)
        batch_essay_count = max(0, end - start)
        if is_grade_level_assignment_school(school):
            safe_school = "grade_level_all_schools"
        else:
            safe_school = secure_filename(school) or "school"
        safe_grade = secure_filename(str(grade)) or "grade"
        zip_filename = f"{safe_school}_grade_{safe_grade}_batch_{batch_number}_of_{batch_count}.zip"
        readers = resolve_or_create_readers(sb, reader_emails)
        reader_ids = [r["id"] for r in readers if r.get("id") is not None]
        if len(reader_ids) != 1:
            return jsonify({"error": "Failed to resolve the requested reader."}), 500
        add_batch_assignment(
            sb,
            reader_id=reader_ids[0],
            school=school,
            grade=grade,
            batch_number=batch_number,
            total_batches=batch_count,
        )
        Thread(
            target=_warm_assignment_zip_cache,
            args=(current_app._get_current_object(),),
            kwargs={
                "school": school,
                "grade": grade,
                "batch_number": batch_number,
            },
            daemon=True,
        ).start()
        token = _generate_reader_portal_token(reader_emails[0])
        portal_url = _reader_portal_url(token)
        email_sent = send_assignment_batch_email(
            to_email=reader_emails[0],
            school=school,
            grade=grade,
            batch_number=batch_number,
            total_batches=batch_count,
            essay_count=batch_essay_count,
            portal_url=portal_url,
            grade_level_scope=is_grade_level_assignment_school(school),
        )
        if not email_sent:
            return jsonify({"error": "Reader access email could not be sent. Check SMTP configuration."}), 500

        return jsonify(
            {
                "school": school,
                "grade": grade,
                "scope": "grade" if is_grade_level_assignment_school(school) else "school",
                "essayCount": essay_count,
                "batchCount": batch_count,
                "batchNumber": batch_number,
                "batchEssayCount": batch_essay_count,
                "assignedReaders": len(reader_ids),
                "readerEmail": reader_emails[0],
                "portalUrl": portal_url,
                "queued": False,
            }
        )
    except Exception as exc:
        if _is_missing_assignment_schema_error(exc):
            return _assignment_schema_error_response()
        return jsonify({"error": f"Failed to assign readers: {exc}"}), 500


@admin_bp.route("/round2/assign-and-send", methods=["POST"])
def assign_round2_and_send():
    """API: create a Round 2 finalist assignment for one reader and send access link."""
    _require_admin()

    payload = request.get_json(silent=True) or {}
    grade = str(payload.get("grade") or "").strip()
    school = str(payload.get("school") or "").strip()
    if not grade:
        return jsonify({"error": "Grade is required."}), 400

    reader_emails, invalid_emails = parse_and_validate_reader_emails(payload.get("readerEmail"))
    if invalid_emails:
        return jsonify({"error": "One or more reader emails are invalid.", "invalidEmails": invalid_emails}), 400
    if len(reader_emails) != 1:
        return jsonify({"error": "Enter exactly one reader email for Round 2 assignment."}), 400

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    try:
        readers = resolve_or_create_readers(sb, reader_emails)
        reader_ids = [r.get("id") for r in readers if r.get("id") is not None]
        if len(reader_ids) != 1:
            return jsonify({"error": "Failed to resolve the requested reader."}), 500

        school_label = school or "Round 2 Finalists"
        assignment_id, finalist_count = create_round2_assignment_from_top_results(
            sb,
            grade=grade,
            school=school or None,
            reader_id=reader_ids[0],
            top_n=10,
        )
        token = _generate_reader_portal_token(reader_emails[0])
        portal_url = _reader_portal_url(token)
        email_sent = send_assignment_batch_email(
            to_email=reader_emails[0],
            school=school_label,
            grade=grade,
            batch_number=1,
            total_batches=1,
            essay_count=finalist_count,
            portal_url=portal_url,
        )
        if not email_sent:
            return jsonify({"error": "Reader access email could not be sent. Check SMTP configuration."}), 500

        return jsonify(
            {
                "success": True,
                "assignmentId": assignment_id,
                "grade": grade,
                "school": school_label,
                "essayCount": finalist_count,
                "batchCount": 1,
                "batchNumber": 1,
                "readerEmail": reader_emails[0],
                "portalUrl": portal_url,
                "round": 2,
            }
        )
    except Exception as exc:
        if _is_missing_assignment_schema_error(exc):
            return _assignment_schema_error_response()
        return jsonify({"error": f"Failed to assign Round 2 reader: {exc}"}), 500


@admin_bp.route("/assignment-records", methods=["GET"])
def assignment_records():
    """API: list assignment records for admin portal."""
    _require_admin()
    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500
    try:
        records = list_assignment_records(sb)
        for record in records:
            record["formattedCreatedAt"] = _format_human_datetime(record.get("createdAt"))
        return jsonify({"records": records})
    except Exception as exc:
        if _is_missing_assignment_schema_error(exc):
            return _assignment_schema_error_response()
        return jsonify({"error": f"Failed to fetch assignment records: {exc}"}), 500


@admin_bp.route("/ranking-results", methods=["GET"])
def ranking_results():
    """API: compute ranking results for a grade, optionally filtered by school."""
    _require_admin()
    grade = str(request.args.get("grade") or "").strip()
    school = str(request.args.get("school") or "").strip()
    if not grade:
        return jsonify({"error": "Grade is required."}), 400

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    try:
        results = compute_ranking_results(sb, grade=grade, school=school or None)
        return jsonify(
            {
                "grade": grade,
                "school": school or None,
                "results": results,
            }
        )
    except Exception as exc:
        if _is_missing_assignment_schema_error(exc):
            return _assignment_schema_error_response()
        return jsonify({"error": f"Failed to compute ranking results: {exc}"}), 500


@admin_bp.route("/reader-access", methods=["GET", "POST"])
def reader_access():
    """
    Reader portal entry. Email contains a signed link; reader confirms email to view assignments.
    """
    token = (request.values.get("token") or "").strip()
    token_email = _verify_reader_portal_token(token)
    if not token_email:
        return render_template(
            "reader_portal.html",
            invalid_link=True,
            email_verified=False,
            token=token,
            reader_email="",
            assignments=[],
        )

    email_verified = False
    submitted_email = ""
    if request.method == "POST":
        submitted_email = str(request.form.get("email") or "").strip().lower()
        if submitted_email == token_email:
            session["reader_portal_email"] = token_email
            email_verified = True
    elif session.get("reader_portal_email") == token_email:
        email_verified = True

    assignments_out: list[dict] = []
    if email_verified:
        sb = _get_service_role_client()
        if sb:
            reader = get_reader_by_email(sb, token_email)
            if reader:
                for row in list_assignments_for_reader(sb, reader.get("id")):
                    essay_rows, is_finalist_round = _resolve_assignment_essay_rows(sb, row)
                    total_essays = len(essay_rows)
                    if is_finalist_round:
                        start, end = 0, total_essays
                    else:
                        approved_total = count_approved_essays_for_batch(
                            sb,
                            school=str(row.get("school_name") or ""),
                            grade=str(row.get("grade") or ""),
                        )
                        start, end = get_batch_bounds(int(row.get("batch_number") or 1), approved_total)
                    assignment_id = int(row.get("id"))
                    saved_rankings = list_rankings_for_assignment(
                        sb,
                        assignment_id=assignment_id,
                        reader_id=reader.get("id"),
                    )
                    saved_rank_by_submission = {
                        str(rank_row.get("submission_id") or "").strip(): int(rank_row.get("rank_position") or 0)
                        for rank_row in saved_rankings
                        if str(rank_row.get("submission_id") or "").strip()
                    }
                    assignments_out.append(
                        {
                            "id": assignment_id,
                            "school": row.get("school_name"),
                            "grade": row.get("grade"),
                            "batchNumber": row.get("batch_number"),
                            "totalBatches": row.get("total_batches"),
                            "isFinalistRound": is_finalist_round,
                            "essayCount": max(0, end - start),
                            "essayRange": f"{start + 1}-{end}" if end > start else "0-0",
                            "createdAt": row.get("created_at"),
                            "formattedCreatedAt": _format_human_datetime(row.get("created_at")),
                            "downloadUrl": url_for("admin.reader_assignment_download", assignment_id=assignment_id, token=token),
                            "reviewUrl": url_for("admin.reader_assignment_review", assignment_id=assignment_id, token=token),
                            "essays": [
                                {
                                    "submissionId": str(essay_row.get("submission_id") or "").strip(),
                                    "studentName": essay_row.get("student_name") or "Unknown student",
                                    "createdAt": _format_human_datetime(essay_row.get("created_at")),
                                    "rankPosition": saved_rank_by_submission.get(str(essay_row.get("submission_id") or "").strip()),
                                    "viewUrl": url_for(
                                        "admin.reader_assignment_submission_view",
                                        assignment_id=assignment_id,
                                        submission_id=str(essay_row.get("submission_id") or "").strip(),
                                        token=token,
                                    ),
                                }
                                for essay_row in essay_rows
                                if str(essay_row.get("submission_id") or "").strip()
                            ],
                        }
                    )

    return render_template(
        "reader_portal.html",
        invalid_link=False,
        email_verified=email_verified,
        token=token,
        reader_email=token_email,
        submitted_email=submitted_email,
        assignments=assignments_out,
    )


@admin_bp.route("/reader-assignments/<int:assignment_id>/download", methods=["GET"])
def reader_assignment_download(assignment_id: int):
    """
    Reader download for one assigned batch ZIP.
    """
    token = (request.args.get("token") or "").strip()
    token_email = _verify_reader_portal_token(token)
    session_email = str(session.get("reader_portal_email") or "").strip().lower()
    if not token_email or token_email != session_email:
        abort(403, description="Reader access not verified.")

    sb = _get_service_role_client()
    if not sb:
        abort(500, description="Database not configured")

    result = (
        sb.table("assignments")
        .select("id, school_name, grade, batch_number, total_batches, readers(id, email)")
        .eq("id", assignment_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        abort(404, description="Assignment not found")
    row = rows[0]
    reader = row.get("readers") or {}
    if str(reader.get("email") or "").strip().lower() != token_email:
        abort(403, description="Assignment does not belong to this reader.")

    payload = _build_assignment_batch_payload(
        sb,
        school=str(row.get("school_name") or ""),
        grade=str(row.get("grade") or ""),
        batch_number=int(row.get("batch_number") or 1),
    )
    return send_file(
        io.BytesIO(payload["zipBytes"]),
        mimetype="application/zip",
        as_attachment=True,
        download_name=payload["zipFilename"],
    )


@admin_bp.route("/reader-assignments/<int:assignment_id>/review", methods=["GET", "POST"])
def reader_assignment_review(assignment_id: int):
    """
    Reader-facing essay list and forced-ranking form for one assignment batch.
    """
    token = (request.values.get("token") or "").strip()
    sb = _get_service_role_client()
    if not sb:
        abort(500, description="Database not configured")

    reader_email, assignment = _load_verified_assignment(sb, assignment_id=assignment_id, token=token)
    if not reader_email:
        abort(403, description="Reader access not verified.")
    if not assignment:
        abort(404, description="Assignment not found")

    reader = assignment.get("readers") or {}
    essay_rows, is_finalist_round = _resolve_assignment_essay_rows(sb, assignment)
    saved_rankings = list_rankings_for_assignment(
        sb,
        assignment_id=assignment_id,
        reader_id=assignment.get("reader_id"),
    )
    saved_by_submission = {
        str(row.get("submission_id") or "").strip(): int(row.get("rank_position") or 0)
        for row in saved_rankings
        if str(row.get("submission_id") or "").strip()
    }
    total_essays = len(essay_rows)
    ranking_finalized_at = assignment.get("ranking_completed_at")
    ranking_finalized = bool(ranking_finalized_at)

    submitted_name = str(reader.get("name") or "").strip()
    submitted_email = reader_email
    error_message = ""
    success_message = ""

    if request.method == "POST":
        if ranking_finalized:
            error_message = "Ranking for this batch is finalized and read-only."
        if error_message:
            essays_out = []
            for index, row in enumerate(essay_rows, start=1):
                submission_id = str(row.get("submission_id") or "").strip()
                essays_out.append(
                    {
                        "index": index,
                        "submissionId": submission_id,
                        "studentName": row.get("student_name") or f"Essay {index}",
                        "schoolName": row.get("school_name") or assignment.get("school_name"),
                        "createdAt": _format_human_datetime(row.get("created_at")),
                        "rankPosition": saved_by_submission.get(submission_id, ""),
                        "viewUrl": url_for(
                            "admin.reader_assignment_submission_view",
                            assignment_id=assignment_id,
                            submission_id=submission_id,
                            token=token,
                        ),
                        "downloadUrl": url_for(
                            "admin.reader_assignment_submission_download",
                            assignment_id=assignment_id,
                            submission_id=submission_id,
                            token=token,
                        ),
                    }
                )

            return render_template(
                "reader_assignment_review.html",
                token=token,
                assignment_id=assignment_id,
                assignment={
                    "school": assignment.get("school_name"),
                    "grade": assignment.get("grade"),
                    "batchNumber": assignment.get("batch_number"),
                    "totalBatches": assignment.get("total_batches"),
                    "essayCount": total_essays,
                },
                reader_name=submitted_name,
                reader_email=reader_email,
                essays=essays_out,
                error_message=error_message,
                success_message=success_message,
                ranking_finalized=ranking_finalized,
                ranking_finalized_at=_format_human_datetime(ranking_finalized_at),
            )

        submitted_name = str(request.form.get("reader_name") or "").strip()
        submitted_email = str(request.form.get("reader_email") or "").strip().lower()
        ranking_map: dict[str, int] = {}
        save_submission_id = str(request.form.get("save_submission_id") or "").strip()
        unrank_submission_id = str(request.form.get("unrank_submission_id") or "").strip()

        for row in essay_rows:
            submission_id = str(row.get("submission_id") or "").strip()
            if not submission_id:
                continue
            raw_value = str(request.form.get(f"rank_{submission_id}") or "").strip()
            if not raw_value:
                continue
            try:
                ranking_map[submission_id] = int(raw_value)
            except Exception:
                error_message = "Each essay rank must be a whole number."
                break

        if not error_message and submitted_email != reader_email:
            error_message = "Submitted email must match the verified assignment email."
        if not error_message and not submitted_name:
            error_message = "Your name is required before rankings can be submitted."

        if not error_message and (save_submission_id or unrank_submission_id):
            target_submission_id = save_submission_id or unrank_submission_id
            valid_submission_ids = {
                str(row.get("submission_id") or "").strip()
                for row in essay_rows
                if str(row.get("submission_id") or "").strip()
            }
            if target_submission_id not in valid_submission_ids:
                error_message = "Essay not found in this assignment."

        if not error_message and save_submission_id:
            raw_value = str(request.form.get(f"rank_{save_submission_id}") or "").strip()
            if not raw_value:
                error_message = "Enter a rank before saving this essay."
            else:
                try:
                    rank_position = int(raw_value)
                except Exception:
                    error_message = "Each essay rank must be a whole number."
                else:
                    if rank_position < 1 or rank_position > total_essays:
                        error_message = f"Ranks must be between 1 and {total_essays}."
                    else:
                        existing_submission = next(
                            (
                                submission_id
                                for submission_id, saved_rank in saved_by_submission.items()
                                if submission_id != save_submission_id and int(saved_rank or 0) == rank_position
                            ),
                            None,
                        )
                        if existing_submission:
                            error_message = f"Rank {rank_position} is already used by another essay. Unrank or change that essay first."

            if not error_message:
                upsert_reader_name(sb, email=reader_email, name=submitted_name)
                save_single_assignment_ranking(
                    sb,
                    assignment_id=assignment_id,
                    reader_id=assignment.get("reader_id"),
                    school=str(assignment.get("school_name") or ""),
                    grade=str(assignment.get("grade") or ""),
                    batch_number=int(assignment.get("batch_number") or 1),
                    submission_id=save_submission_id,
                    rank_position=rank_position,
                    reader_name=submitted_name,
                    reader_email=reader_email,
                )
                saved_by_submission[save_submission_id] = rank_position
                success_message = f"Saved rank {rank_position} for this essay."

        if not error_message and unrank_submission_id:
            delete_single_assignment_ranking(
                sb,
                assignment_id=assignment_id,
                reader_id=assignment.get("reader_id"),
                submission_id=unrank_submission_id,
            )
            saved_by_submission.pop(unrank_submission_id, None)
            success_message = "Essay moved back to unranked."

        if not error_message and not save_submission_id and not unrank_submission_id:
            is_valid, validation_message = _validate_forced_rankings(essay_rows, ranking_map)
            if not is_valid:
                error_message = validation_message or "Ranking submission is invalid."

        if not error_message and not save_submission_id and not unrank_submission_id:
            upsert_reader_name(sb, email=reader_email, name=submitted_name)
            replace_assignment_rankings(
                sb,
                assignment_id=assignment_id,
                reader_id=assignment.get("reader_id"),
                school=str(assignment.get("school_name") or ""),
                grade=str(assignment.get("grade") or ""),
                batch_number=int(assignment.get("batch_number") or 1),
                reader_name=submitted_name,
                reader_email=reader_email,
                rankings=[
                    {"submission_id": submission_id, "rank_position": rank_position}
                    for submission_id, rank_position in ranking_map.items()
                ],
            )
            saved_by_submission = ranking_map
            mark_assignment_ranking_completed(
                sb,
                assignment_id=assignment_id,
                reader_name=submitted_name,
                reader_email=reader_email,
            )
            ranking_finalized = True
            ranking_finalized_at = datetime.now(timezone.utc).isoformat()
            try:
                send_reader_ranking_completion_email(
                    reader_name=submitted_name,
                    reader_email=reader_email,
                    school=str(assignment.get("school_name") or ""),
                    grade=str(assignment.get("grade") or ""),
                    batch_number=int(assignment.get("batch_number") or 1),
                    total_batches=int(assignment.get("total_batches") or 1),
                    essay_count=total_essays,
                )
            except Exception as email_exc:
                current_app.logger.warning(
                    "Failed to send reader ranking completion email for assignment %s: %s",
                    assignment_id,
                    email_exc,
                )
            try:
                send_reader_ranking_confirmation_email(
                    reader_name=submitted_name,
                    reader_email=reader_email,
                    school=str(assignment.get("school_name") or ""),
                    grade=str(assignment.get("grade") or ""),
                    batch_number=int(assignment.get("batch_number") or 1),
                    total_batches=int(assignment.get("total_batches") or 1),
                    essay_count=total_essays,
                )
            except Exception as email_exc:
                current_app.logger.warning(
                    "Failed to send volunteer ranking confirmation email for assignment %s: %s",
                    assignment_id,
                    email_exc,
                )
            success_message = "Rankings saved."

    essays_out = []
    for index, row in enumerate(essay_rows, start=1):
        submission_id = str(row.get("submission_id") or "").strip()
        essays_out.append(
            {
                "index": index,
                "submissionId": submission_id,
                "studentName": row.get("student_name") or f"Essay {index}",
                "schoolName": row.get("school_name") or assignment.get("school_name"),
                "createdAt": _format_human_datetime(row.get("created_at")),
                "rankPosition": saved_by_submission.get(submission_id, ""),
                "viewUrl": url_for(
                    "admin.reader_assignment_submission_view",
                    assignment_id=assignment_id,
                    submission_id=submission_id,
                    token=token,
                ),
                "downloadUrl": url_for(
                    "admin.reader_assignment_submission_download",
                    assignment_id=assignment_id,
                    submission_id=submission_id,
                    token=token,
                ),
            }
        )

    return render_template(
        "reader_assignment_review.html",
        token=token,
        assignment_id=assignment_id,
        assignment={
            "school": assignment.get("school_name"),
            "grade": assignment.get("grade"),
            "batchNumber": assignment.get("batch_number"),
            "totalBatches": assignment.get("total_batches"),
            "isFinalistRound": is_finalist_round,
            "essayCount": total_essays,
        },
        reader_name=submitted_name,
        reader_email=reader_email,
        essays=essays_out,
        error_message=error_message,
        success_message=success_message,
        ranking_finalized=ranking_finalized,
        ranking_finalized_at=_format_human_datetime(ranking_finalized_at),
    )


def _load_assignment_submission_or_404(sb, *, assignment_id: int, submission_id: str, token: str) -> dict:
    reader_email, assignment = _load_verified_assignment(sb, assignment_id=assignment_id, token=token)
    if not reader_email:
        abort(403, description="Reader access not verified.")
    if not assignment:
        abort(404, description="Assignment not found")

    submission_id_value = str(submission_id or "").strip()
    essay_rows, _ = _resolve_assignment_essay_rows(sb, assignment)
    for row in essay_rows:
        if str(row.get("submission_id") or "").strip() == submission_id_value:
            return row
    abort(404, description="Essay not found in this assignment.")


@admin_bp.route("/reader-assignments/<int:assignment_id>/submissions/<submission_id>/view", methods=["GET"])
def reader_assignment_submission_view(assignment_id: int, submission_id: str):
    """
    Stream one assigned essay inline for a verified reader.
    """
    token = (request.args.get("token") or "").strip()
    sb = _get_service_role_client()
    if not sb:
        abort(500, description="Database not configured")

    row = _load_assignment_submission_or_404(sb, assignment_id=assignment_id, submission_id=submission_id, token=token)
    artifact_dir = row.get("artifact_dir", "")
    filename = row.get("filename", "original.pdf")
    if not artifact_dir:
        abort(404, description="Original file is not stored for this submission.")

    file_bytes, used_path = download_original_with_service_role(sb, artifact_dir, filename)
    if not file_bytes or not used_path:
        abort(404, description="Original file not found in storage for this submission.")

    safe_name = secure_filename(filename) or "original"
    response = send_file(
        io.BytesIO(file_bytes),
        mimetype=_mimetype_for_storage_path(used_path),
        as_attachment=False,
        download_name=safe_name,
    )
    response.headers["Content-Disposition"] = f'inline; filename="{safe_name}"'
    return response


@admin_bp.route("/reader-assignments/<int:assignment_id>/submissions/<submission_id>/download", methods=["GET"])
def reader_assignment_submission_download(assignment_id: int, submission_id: str):
    """
    Download one assigned essay file for a verified reader.
    """
    token = (request.args.get("token") or "").strip()
    sb = _get_service_role_client()
    if not sb:
        abort(500, description="Database not configured")

    row = _load_assignment_submission_or_404(sb, assignment_id=assignment_id, submission_id=submission_id, token=token)
    artifact_dir = row.get("artifact_dir", "")
    filename = row.get("filename", "original.pdf")
    if not artifact_dir:
        abort(404, description="Original file is not stored for this submission.")

    file_bytes, used_path = download_original_with_service_role(sb, artifact_dir, filename)
    if not file_bytes or not used_path:
        abort(404, description="Original file not found in storage for this submission.")

    safe_name = secure_filename(filename) or "download"
    return send_file(
        io.BytesIO(file_bytes),
        mimetype=_mimetype_for_storage_path(used_path),
        as_attachment=True,
        download_name=safe_name,
    )


@admin_bp.route("/unassign", methods=["POST"])
def unassign():
    """API: remove a single assignment by id."""
    _require_admin()
    payload = request.get_json(silent=True) or {}
    assignment_id = payload.get("assignmentId")
    if assignment_id is None:
        return jsonify({"error": "assignmentId is required."}), 400
    try:
        assignment_id_int = int(assignment_id)
    except Exception:
        return jsonify({"error": "assignmentId must be a number."}), 400

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    try:
        removed = remove_assignment(sb, assignment_id_int)
        if not removed:
            return jsonify({"error": "Assignment not found."}), 404
        return jsonify({"success": True, "assignmentId": assignment_id_int})
    except Exception as exc:
        if _is_missing_assignment_schema_error(exc):
            return _assignment_schema_error_response()
        return jsonify({"error": f"Failed to unassign: {exc}"}), 500


@admin_bp.route("/submissions", methods=["GET"])
def get_submissions():
    """API: list submissions (JSON), optional ?school=&grade=&limit=."""
    _require_admin()

    fetch_limit = min(int(request.args.get("limit", 1000)), 2000)
    all_rows = _fetch_all_submissions(limit=fetch_limit)
    selected_school = (request.args.get("school") or "").strip()
    selected_grade = (request.args.get("grade") or "").strip()
    selected_status = (request.args.get("status") or "").strip()
    selected_multi_entry = (request.args.get("multi_entry") or "").strip()
    selected_submission_id = (request.args.get("submission_id") or "").strip()
    multi_entry_only = selected_multi_entry in ("1", "true", "yes", "on")
    submissions = _apply_school_grade_filters(
        all_rows, selected_school, selected_grade, selected_status, selected_submission_id
    )
    submissions = _apply_multi_entry_only_filter(all_rows, submissions, multi_entry_only)
    selected_duplicates = (request.args.get("duplicates") or "").strip()
    duplicates_only = selected_duplicates in ("1", "true", "yes", "on")
    submissions = _apply_duplicates_only_filter(submissions, duplicates_only)

    def _display_status(s):
        if s.get("is_container_parent"):
            return "needs_review"
        has_all = s.get("student_name") and s.get("school_name") and s.get("grade")
        has_reason = _row_has_reason_codes(s)
        if has_all and not has_reason:
            return "approved"
        if has_reason:
            return "needs_review"
        return "needs_review" if s.get("needs_review") else "approved"

    return jsonify({
        "data": [
            {
                "id": s["submission_id"],
                "student_name": s.get("student_name") or "",
                "school_name": s.get("school_name") or "",
                "grade": s.get("grade"),
                "file_name": s.get("filename") or "",
                "status": _display_status(s),
                "review_reasons": _format_review_reasons(s.get("review_reason_codes", "")),
                "created_at": s.get("created_at", ""),
                "owner_user_id": s.get("owner_user_id", ""),
            }
            for s in submissions
        ],
        "meta": {
            "count": len(submissions),
            "loaded": len(all_rows),
            "limit": fetch_limit,
            "duplicates_only": duplicates_only,
        },
    })


def _mimetype_for_storage_path(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".doc"):
        return "application/msword"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


@admin_bp.route("/submissions/<submission_id>/download", methods=["GET"])
def download_submission(submission_id: str):
    """Download original file (service role + same path resolution as /pdf)."""
    _require_admin()

    sb = _get_service_role_client()
    if not sb:
        abort(500, description="Database not configured")

    result = (
        sb.table("submissions")
        .select("artifact_dir, filename")
        .eq("submission_id", submission_id)
        .limit(1)
        .execute()
    )

    if not result.data or len(result.data) == 0:
        abort(404, description="Submission not found")

    record = result.data[0]
    artifact_dir = record.get("artifact_dir", "")
    filename = record.get("filename", "unknown.pdf")

    if not artifact_dir:
        abort(404, description="No file path for this submission")

    file_bytes, used_path = download_original_with_service_role(sb, artifact_dir, filename)
    if not file_bytes or not used_path:
        abort(404, description="Original file not found in storage for this submission.")

    safe_name = secure_filename(filename) or "download"
    if used_path and Path(used_path).suffix:
        # Prefer original stored extension in download name
        ext = Path(used_path).suffix
        if safe_name and not Path(safe_name).suffix:
            safe_name = f"{Path(safe_name).stem}{ext}"
        elif not safe_name:
            safe_name = Path(used_path).name

    return send_file(
        io.BytesIO(file_bytes),
        mimetype=_mimetype_for_storage_path(used_path),
        as_attachment=True,
        download_name=safe_name,
    )


@admin_bp.route("/submissions/<submission_id>/view", methods=["GET"])
def view_submission_file(submission_id: str):
    """Stream original file inline for side-by-side review."""
    _require_admin()

    sb = _get_service_role_client()
    if not sb:
        abort(500, description="Database not configured")

    result = (
        sb.table("submissions")
        .select("artifact_dir, filename, essay_text, student_name")
        .eq("submission_id", submission_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        abort(404, description="Submission not found")

    record = result.data[0]
    artifact_dir = record.get("artifact_dir", "")
    filename = record.get("filename", "original.pdf")
    essay_text = (record.get("essay_text") or "").strip()
    student_name = (record.get("student_name") or "").strip()

    def _render_essay_text_only_fallback() -> tuple:
        """When the PDF is missing but essay_text exists — single clear page (no empty essay placeholder)."""
        title_bits = [b for b in [student_name, filename] if b]
        title = " - ".join(title_bits) if title_bits else submission_id
        body = html.escape(essay_text)
        fallback_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }}
    .wrap {{ padding: 24px; max-width: 52rem; }}
    .meta {{ color: #64748b; margin-bottom: 16px; font-size: 14px; }}
    .essay {{ white-space: pre-wrap; background: white; border: 1px solid #cbd5e1; border-radius: 8px; padding: 16px; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1 style="margin:0 0 8px 0; font-size: 18px;">Essay text only</h1>
    <div class="meta">Original upload is not available in storage; showing extracted essay text from the database.</div>
    <div class="essay">{body}</div>
  </div>
</body>
</html>"""
        return fallback_html, 200, {"Content-Type": "text/html; charset=utf-8"}

    if not artifact_dir:
        if essay_text:
            return _render_essay_text_only_fallback()
        abort(
            404,
            description="No original file in storage for this submission and no essay text on file.",
        )

    file_bytes, used_path = download_original_with_service_role(sb, artifact_dir, filename)
    if not file_bytes or not used_path:
        if essay_text:
            return _render_essay_text_only_fallback()
        abort(
            404,
            description="Original file not found in storage for this submission and no essay text on file.",
        )

    safe_name = secure_filename(filename) or "original"
    mimetype = _mimetype_for_storage_path(used_path)
    response = send_file(
        io.BytesIO(file_bytes),
        mimetype=mimetype,
        as_attachment=False,
        download_name=safe_name,
    )
    response.headers["Content-Disposition"] = f'inline; filename="{safe_name}"'
    return response


@admin_bp.route("/submissions/<submission_id>/metadata", methods=["POST"])
def update_submission_metadata(submission_id: str):
    """Update editable metadata fields and re-evaluate review status."""
    _require_admin()

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid request body"}), 400

    allowed_keys = {"student_name", "school_name", "grade"}
    if not any(key in payload for key in allowed_keys):
        return jsonify({"error": "Provide at least one of student_name, school_name, or grade"}), 400

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    current_res = (
        sb.table("submissions")
        .select("submission_id, student_name, school_name, grade, needs_review, review_reason_codes")
        .eq("submission_id", submission_id)
        .limit(1)
        .execute()
    )
    if not current_res.data:
        return jsonify({"error": "Submission not found"}), 404
    current = current_res.data[0]

    updates = {}
    if "student_name" in payload:
        updates["student_name"] = (str(payload.get("student_name") or "").strip() or None)
    if "school_name" in payload:
        updates["school_name"] = (str(payload.get("school_name") or "").strip() or None)
    if "grade" in payload:
        updates["grade"] = _normalize_grade_value(payload.get("grade"))

    effective_student = updates.get("student_name", current.get("student_name"))
    effective_school = updates.get("school_name", current.get("school_name"))
    effective_grade = updates.get("grade", current.get("grade"))
    synced_codes_db, synced_needs_review = _sync_required_field_reason_codes(
        student_name=effective_student,
        school_name=effective_school,
        grade=effective_grade,
        existing_reason_codes=current.get("review_reason_codes"),
    )
    updates["review_reason_codes"] = synced_codes_db
    updates["needs_review"] = synced_needs_review

    (
        sb.table("submissions")
        .update(updates)
        .eq("submission_id", submission_id)
        .execute()
    )

    refreshed_res = (
        sb.table("submissions")
        .select("submission_id, student_name, school_name, grade, needs_review, review_reason_codes")
        .eq("submission_id", submission_id)
        .limit(1)
        .execute()
    )
    if not refreshed_res.data:
        return jsonify({"error": "Update failed"}), 500
    updated = refreshed_res.data[0]
    has_all_data = bool(
        (updated.get("student_name") or "").strip()
        and (updated.get("school_name") or "").strip()
        and str(updated.get("grade") or "").strip()
    )
    has_reason = bool(_coerce_reason_codes(updated.get("review_reason_codes")))
    status = "approved" if has_all_data and not has_reason else "needs_review"
    return jsonify(
        {
            "success": True,
            "submission_id": submission_id,
            "student_name": updated.get("student_name") or "",
            "school_name": updated.get("school_name") or "",
            "grade": "" if updated.get("grade") is None else str(updated.get("grade")),
            "needs_review": status == "needs_review",
            "status": status,
            "review_reason_codes": updated.get("review_reason_codes") or "",
            "review_reasons": _format_review_reasons(updated.get("review_reason_codes") or ""),
        }
    )


@admin_bp.route("/submissions/<submission_id>/force-approve", methods=["POST"])
def force_approve_submission(submission_id: str):
    """Admin override: approve a submission if required metadata is present."""
    _require_admin()

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    result = (
        sb.table("submissions")
        .select("submission_id, student_name, school_name, grade")
        .eq("submission_id", submission_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return jsonify({"error": "Submission not found"}), 404
    rec = result.data[0]

    missing = []
    if not (rec.get("student_name") or "").strip():
        missing.append("student_name")
    if not (rec.get("school_name") or "").strip():
        missing.append("school_name")
    if str(rec.get("grade") or "").strip() == "":
        missing.append("grade")
    if missing:
        return jsonify(
            {
                "error": "Cannot force approve while required metadata is missing.",
                "missing_fields": missing,
            }
        ), 400

    sb.table("submissions").update(
        {
            "needs_review": False,
            "review_reason_codes": "",
        }
    ).eq("submission_id", submission_id).execute()

    return jsonify(
        {
            "success": True,
            "submission_id": submission_id,
            "status": "approved",
            "review_reasons": "—",
        }
    )


@admin_bp.route("/submissions/<submission_id>/send-to-review", methods=["POST"])
def send_submission_to_review(submission_id: str):
    """Admin: explicitly move a submission back to needs_review."""
    _require_admin()

    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    current_res = (
        sb.table("submissions")
        .select("submission_id, review_reason_codes")
        .eq("submission_id", submission_id)
        .limit(1)
        .execute()
    )
    if not current_res.data:
        return jsonify({"error": "Submission not found"}), 404

    existing_codes = _coerce_reason_codes(current_res.data[0].get("review_reason_codes"))
    if reason and reason in ALLOWED_REASON_CODES:
        existing_codes.add(reason)

    sb.table("submissions").update(
        {
            "needs_review": True,
            "review_reason_codes": ";".join(sorted(existing_codes)) if existing_codes else "",
        }
    ).eq("submission_id", submission_id).execute()

    return jsonify({
        "success": True,
        "submission_id": submission_id,
        "status": "needs_review",
        "review_reasons": _format_review_reasons(";".join(sorted(existing_codes))) if existing_codes else "Pending review",
    })


@admin_bp.route("/submissions/bulk-send-to-review", methods=["POST"])
def bulk_send_to_review():
    """Admin: move multiple submissions back to needs_review by ID."""
    _require_admin()

    payload = request.get_json(silent=True) or {}
    submission_ids = payload.get("submission_ids")
    if not isinstance(submission_ids, list) or not submission_ids:
        return jsonify({"error": "submission_ids (non-empty list) is required"}), 400

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    clean_ids = [str(sid).strip() for sid in submission_ids if str(sid).strip()][:500]
    updated_count = 0
    errors = []

    for sid in clean_ids:
        try:
            sb.table("submissions").update(
                {"needs_review": True}
            ).eq("submission_id", sid).execute()
            updated_count += 1
        except Exception as exc:
            errors.append(f"{sid}: {exc}")

    return jsonify({
        "success": updated_count > 0,
        "updated_count": updated_count,
        "error_count": len(errors),
        "errors": errors[:20] if errors else [],
    })


@admin_bp.route("/submissions/bulk-download", methods=["POST"])
def bulk_download_submissions():
    """ZIP originals for selected submission_ids (admin session or Bearer)."""
    _require_admin()

    data = request.get_json(silent=True) or {}
    raw_ids = data.get("submission_ids")
    if not isinstance(raw_ids, list):
        abort(400, description="JSON body must include submission_ids: []")

    ids = []
    for x in raw_ids[:_ADMIN_BULK_DOWNLOAD_MAX]:
        s = str(x).strip()
        if s and s not in ids:
            ids.append(s)
    if not ids:
        abort(400, description="No valid submission IDs")

    sb = _get_service_role_client()
    if not sb:
        abort(500, description="Database not configured")

    buffer = io.BytesIO()
    total_bytes = 0
    skipped: list[str] = []
    used_arcnames: set[str] = set()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for submission_id in ids:
            result = (
                sb.table("submissions")
                .select("artifact_dir, filename")
                .eq("submission_id", submission_id)
                .limit(1)
                .execute()
            )
            if not result.data:
                skipped.append(submission_id)
                continue
            record = result.data[0]
            artifact_dir = record.get("artifact_dir", "")
            filename = record.get("filename", "unknown.pdf")
            if not artifact_dir:
                skipped.append(submission_id)
                continue
            file_bytes, used_path = download_original_with_service_role(sb, artifact_dir, filename)
            if not file_bytes:
                skipped.append(submission_id)
                continue
            if total_bytes + len(file_bytes) > _ADMIN_BULK_DOWNLOAD_MAX_BYTES:
                skipped.append(submission_id)
                continue
            total_bytes += len(file_bytes)
            ext = Path(used_path or filename).suffix or ".bin"
            base = secure_filename(filename) or "file"
            stem = Path(base).stem
            arcname = f"{submission_id}_{stem}{ext}"
            if arcname in used_arcnames:
                arcname = f"{submission_id}_{stem}_{len(used_arcnames)}{ext}"
            used_arcnames.add(arcname)
            zf.writestr(arcname, file_bytes)

    if not used_arcnames:
        abort(404, description="No files could be added to ZIP (missing storage or paths).")

    buffer.seek(0)
    name = f"ifi_submissions_{uuid.uuid4().hex[:10]}.zip"
    resp = send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=name,
    )
    if skipped:
        resp.headers["X-Admin-Zip-Skipped-Count"] = str(len(skipped))
    return resp


@admin_bp.route("/submissions/bulk-update-selected", methods=["POST"])
def bulk_update_selected():
    """Update metadata fields on a selected set of submissions by ID."""
    _require_admin()

    payload = request.get_json(silent=True) or {}
    submission_ids = payload.get("submission_ids")
    if not isinstance(submission_ids, list) or not submission_ids:
        return jsonify({"error": "submission_ids (non-empty list) is required"}), 400

    updates: dict = {}
    if "student_name" in payload:
        updates["student_name"] = (str(payload["student_name"]).strip() or None)
    if "school_name" in payload:
        updates["school_name"] = (str(payload["school_name"]).strip() or None)
    if "grade" in payload:
        updates["grade"] = _normalize_grade_value(payload["grade"])
    if "teacher_name" in payload:
        updates["teacher_name"] = (str(payload["teacher_name"]).strip() or None)
    if "city_or_location" in payload:
        updates["city_or_location"] = (str(payload["city_or_location"]).strip() or None)
    if "father_figure_name" in payload:
        updates["father_figure_name"] = (str(payload["father_figure_name"]).strip() or None)

    if not updates:
        return jsonify({"error": "Provide at least one field to update"}), 400

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    clean_ids = [str(sid).strip() for sid in submission_ids if str(sid).strip()][:500]
    if not clean_ids:
        return jsonify({"error": "No valid submission IDs"}), 400

    updated_count = 0
    errors = []
    for sid in clean_ids:
        try:
            current_res = (
                sb.table("submissions")
                .select("submission_id, student_name, school_name, grade, needs_review, review_reason_codes")
                .eq("submission_id", sid)
                .limit(1)
                .execute()
            )
            if not current_res.data:
                errors.append(sid)
                continue
            current = current_res.data[0]

            row_updates = dict(updates)
            eff_student = row_updates.get("student_name", current.get("student_name"))
            eff_school = row_updates.get("school_name", current.get("school_name"))
            eff_grade = row_updates.get("grade", current.get("grade"))
            synced_codes, synced_needs_review = _sync_required_field_reason_codes(
                student_name=eff_student,
                school_name=eff_school,
                grade=eff_grade,
                existing_reason_codes=current.get("review_reason_codes"),
            )
            row_updates["review_reason_codes"] = synced_codes
            row_updates["needs_review"] = synced_needs_review

            sb.table("submissions").update(row_updates).eq("submission_id", sid).execute()
            updated_count += 1
        except Exception as exc:
            errors.append(f"{sid}: {exc}")

    return jsonify({
        "success": updated_count > 0,
        "updated_count": updated_count,
        "error_count": len(errors),
        "errors": errors[:20] if errors else [],
    })


@admin_bp.route("/submissions/bulk-rename", methods=["POST"])
def bulk_rename_field():
    """Rename a metadata value across all matching submissions (e.g. fix a school name globally)."""
    _require_admin()

    payload = request.get_json(silent=True) or {}
    field = str(payload.get("field") or "").strip()
    old_value = str(payload.get("old_value") or "").strip()
    new_value = str(payload.get("new_value") or "").strip()

    allowed_fields = {"student_name", "school_name", "teacher_name", "city_or_location", "father_figure_name"}
    if field not in allowed_fields:
        return jsonify({"error": f"Field must be one of: {', '.join(sorted(allowed_fields))}"}), 400
    if not old_value:
        return jsonify({"error": "old_value is required"}), 400
    if not new_value:
        return jsonify({"error": "new_value is required"}), 400
    if old_value == new_value:
        return jsonify({"error": "old_value and new_value are the same"}), 400

    sb = _get_service_role_client()
    if not sb:
        return jsonify({"error": "Database not configured"}), 500

    try:
        matching = (
            sb.table("submissions")
            .select("submission_id")
            .eq(field, old_value)
            .limit(5000)
            .execute()
        )
        matched_ids = [r["submission_id"] for r in (matching.data or [])]
        if not matched_ids:
            return jsonify({"error": f'No submissions found with {field} = "{old_value}"', "updated_count": 0}), 404

        update_payload = {field: new_value}

        (
            sb.table("submissions")
            .update(update_payload)
            .eq(field, old_value)
            .execute()
        )
        return jsonify({
            "success": True,
            "field": field,
            "old_value": old_value,
            "new_value": update_payload.get(field, new_value),
            "updated_count": len(matched_ids),
        })
    except Exception as exc:
        return jsonify({"error": f"Bulk rename failed: {exc}"}), 500


@admin_bp.route("/export/csv", methods=["GET"])
def admin_export_csv():
    """Export approved submissions to CSV for certificate mail merge."""
    _require_admin()

    sb = _get_service_role_client()
    if not sb:
        abort(500, description="Database not configured")

    school_filter = (request.args.get("school") or "").strip()
    grade_filter = (request.args.get("grade") or "").strip()
    status_filter = (request.args.get("status") or "").strip().lower()

    select_fields = (
        "submission_id, student_name, school_name, grade, "
        "teacher_name, city_or_location, father_figure_name, "
        "phone, email, word_count, filename, "
        "needs_review, review_reason_codes, created_at"
    )

    query = sb.table("submissions").select(select_fields).order("school_name").order("grade").order("student_name")

    if status_filter != "all":
        query = query.eq("needs_review", False)

    if school_filter:
        query = query.eq("school_name", school_filter)
    if grade_filter:
        query = query.eq("grade", grade_filter)

    try:
        result = query.limit(10000).execute()
    except Exception as exc:
        abort(500, description=f"Export query failed: {exc}")

    rows = result.data or []
    if status_filter != "all":
        rows = [r for r in rows if not _is_excluded_submission_row(r)]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Student Name",
        "School Name",
        "Grade",
        "Teacher Name",
        "City / Location",
        "Father Figure Name",
        "Phone",
        "Email",
        "Word Count",
        "File Name",
        "Submission ID",
        "Date Submitted",
    ])
    for row in rows:
        created = (row.get("created_at") or "")[:10]
        writer.writerow([
            row.get("student_name") or "",
            row.get("school_name") or "",
            row.get("grade") if row.get("grade") is not None else "",
            row.get("teacher_name") or "",
            row.get("city_or_location") or "",
            row.get("father_figure_name") or "",
            row.get("phone") or "",
            row.get("email") or "",
            row.get("word_count") or "",
            row.get("filename") or "",
            row.get("submission_id") or "",
            created,
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    parts = ["ifi_submissions"]
    if school_filter:
        parts.append(secure_filename(school_filter) or "school")
    if grade_filter:
        parts.append(f"grade_{secure_filename(str(grade_filter))}")
    parts.append(f"{len(rows)}_records")
    download_name = "_".join(parts) + ".csv"

    return send_file(
        io.BytesIO(csv_bytes),
        mimetype="text/csv",
        as_attachment=True,
        download_name=download_name,
    )


@admin_bp.route("/failure-stats", methods=["GET"])
def failure_stats_json():
    """JSON: same aggregates as dashboard (optional school/grade filter)."""
    _require_admin()
    fetch_limit = min(int(request.args.get("limit", 1000)), 2000)
    all_rows = _fetch_all_submissions(limit=fetch_limit)
    school = (request.args.get("school") or "").strip()
    grade = (request.args.get("grade") or "").strip()
    filtered = _apply_school_grade_filters(all_rows, school, grade)
    return jsonify({
        "loaded": len(all_rows),
        "limit": fetch_limit,
        "all": _failure_reason_stats(all_rows),
        "filtered": _failure_reason_stats(filtered),
        "duplicate_filenames": _duplicate_filename_hints(all_rows),
    })
