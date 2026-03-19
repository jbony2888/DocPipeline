"""
Admin Blueprint: view all submissions, download files securely.
Admin-controlled access via Bearer token or session.
"""

import io
import os
import uuid
import zipfile
from collections import Counter
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

from pipeline.supabase_db import _get_service_role_client
from pipeline.supabase_storage import BUCKET_NAME, download_original_with_service_role
from pipeline.validate import ALLOWED_REASON_CODES
from pipeline.grouping import normalize_key
from auth.app_admin import is_app_admin_email

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
}


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
    try:
        result = (
            sb.table("submissions")
            .select(
                "submission_id, student_name, school_name, grade, filename, "
                "artifact_dir, needs_review, review_reason_codes, created_at, owner_user_id"
            )
            .order("created_at", desc=True)
            .limit(cap)
            .execute()
        )
        return result.data if result.data else []
    except Exception:
        return []


def _apply_school_grade_filters(rows: list, school: str, grade: str) -> list:
    """Filter rows by normalized school and/or grade (exact match to chosen dropdown value)."""
    school_key = normalize_key(school) if (school or "").strip() else ""
    grade_key = normalize_key(grade) if (grade or "").strip() else ""
    if not school_key and not grade_key:
        return list(rows)
    out = []
    for r in rows:
        if school_key and normalize_key(r.get("school_name")) != school_key:
            continue
        if grade_key and normalize_key(str(r.get("grade") or "")) != grade_key:
            continue
        out.append(r)
    return out


# Max originals in one ZIP (memory + timeout safety during contest)
_ADMIN_BULK_DOWNLOAD_MAX = 50
_ADMIN_BULK_DOWNLOAD_MAX_BYTES = 120 * 1024 * 1024  # 120 MB soft cap


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
    schools = sorted(
        {str(r.get("school_name") or "").strip() for r in rows if str(r.get("school_name") or "").strip()},
        key=lambda s: s.casefold(),
    )
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

    school_options, grade_options = _distinct_schools_and_grades(all_rows)
    submissions = _apply_school_grade_filters(all_rows, selected_school, selected_grade)

    return render_template(
        "admin_dashboard.html",
        submissions=submissions,
        total=len(submissions),
        total_loaded=len(all_rows),
        school_options=school_options,
        grade_options=grade_options,
        selected_school=selected_school,
        selected_grade=selected_grade,
        fetch_limit=fetch_limit,
        format_review_reasons=_format_review_reasons,
    )


@admin_bp.route("/submissions", methods=["GET"])
def get_submissions():
    """API: list submissions (JSON), optional ?school=&grade=&limit=."""
    _require_admin()

    fetch_limit = min(int(request.args.get("limit", 1000)), 2000)
    all_rows = _fetch_all_submissions(limit=fetch_limit)
    selected_school = (request.args.get("school") or "").strip()
    selected_grade = (request.args.get("grade") or "").strip()
    submissions = _apply_school_grade_filters(all_rows, selected_school, selected_grade)

    def _display_status(s):
        has_all = s.get("student_name") and s.get("school_name") and s.get("grade")
        has_reason = (s.get("review_reason_codes") or "").strip()
        if has_all and not has_reason:
            return "approved"
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
