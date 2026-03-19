"""
Admin Blueprint: view all submissions, download files securely.
Admin-controlled access via Bearer token or session.
"""

import os
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

from pipeline.supabase_db import _get_service_role_client
from pipeline.supabase_storage import BUCKET_NAME
from pipeline.validate import ALLOWED_REASON_CODES
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


def _get_storage_path(artifact_dir: str, filename: str) -> str:
    """Build storage path for original file from artifact_dir and filename."""
    if not artifact_dir:
        return ""
    ext = Path(filename or "").suffix.lower()
    if not ext:
        ext = ".pdf"
    return f"{artifact_dir.rstrip('/')}/original{ext}"


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


@admin_bp.route("/dashboard")
def admin_dashboard():
    """Admin dashboard: view all submissions."""
    _require_admin()

    limit = min(int(request.args.get("limit", 100)), 500)
    submissions = _fetch_all_submissions(limit=limit)

    return render_template(
        "admin_dashboard.html",
        submissions=submissions,
        total=len(submissions),
        format_review_reasons=_format_review_reasons,
    )


@admin_bp.route("/submissions", methods=["GET"])
def get_submissions():
    """API: list all submissions (JSON)."""
    _require_admin()

    limit = min(int(request.args.get("limit", 100)), 500)
    submissions = _fetch_all_submissions(limit=limit)

    return jsonify({
        "data": [
            {
                "id": s["submission_id"],
                "student_name": s.get("student_name") or "",
                "school_name": s.get("school_name") or "",
                "file_name": s.get("filename") or "",
                "status": "needs_review" if s.get("needs_review") else "approved",
                "review_reasons": _format_review_reasons(s.get("review_reason_codes", "")),
                "created_at": s.get("created_at", ""),
                "owner_user_id": s.get("owner_user_id", ""),
            }
            for s in submissions
        ],
    })


@admin_bp.route("/submissions/<submission_id>/download", methods=["GET"])
def download_submission(submission_id: str):
    """Download submission file via signed URL redirect."""
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

    storage_path = _get_storage_path(artifact_dir, filename)

    try:
        # Create signed URL (60 seconds)
        resp = sb.storage.from_(BUCKET_NAME).create_signed_url(storage_path, 60)
        signed_url = resp.get("signedUrl") or resp.get("signedURL")
        if signed_url:
            return redirect(signed_url)
    except Exception as e:
        # Fallback: try common extensions if primary fails
        for ext in [".pdf", ".png", ".jpg", ".jpeg"]:
            alt_path = f"{artifact_dir.rstrip('/')}/original{ext}"
            if alt_path == storage_path:
                continue
            try:
                resp = sb.storage.from_(BUCKET_NAME).create_signed_url(alt_path, 60)
                signed_url = resp.get("signedUrl") or resp.get("signedURL")
                if signed_url:
                    return redirect(signed_url)
            except Exception:
                continue
        abort(404, description=f"File not found in storage: {e}")

    abort(404, description="Could not generate download URL")


def _fetch_all_submissions(limit: int = 100) -> list:
    """Fetch all submissions using service role (bypasses RLS)."""
    sb = _get_service_role_client()
    if not sb:
        return []

    try:
        result = (
            sb.table("submissions")
            .select(
                "submission_id, student_name, school_name, grade, filename, "
                "artifact_dir, needs_review, review_reason_codes, created_at, owner_user_id"
            )
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data if result.data else []
    except Exception:
        return []
