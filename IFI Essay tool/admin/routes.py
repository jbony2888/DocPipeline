"""
Admin Blueprint: view all submissions, download files securely.
Admin-controlled access via Bearer token or session.
"""

import io
import os
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

    return jsonify({
        "data": [
            {
                "id": s["submission_id"],
                "student_name": s.get("student_name") or "",
                "school_name": s.get("school_name") or "",
                "grade": s.get("grade"),
                "file_name": s.get("filename") or "",
                "status": "needs_review" if s.get("needs_review") else "approved",
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
