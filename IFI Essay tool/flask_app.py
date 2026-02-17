"""
Flask application for IFI Essay Gateway.
Replaces Streamlit with better redirect handling for Supabase magic links.
"""

from flask import Flask, make_response, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.utils import secure_filename
import os
from pathlib import Path
import json
import io
import csv
import re
import uuid
from typing import Optional, List, Dict, Any
import logging
import time
import redis

# Load environment variables from .env file (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, assume env vars are set another way

from pipeline.supabase_storage import ingest_upload_supabase, get_file_url, download_file, BUCKET_NAME
from pipeline.runner import process_submission
from pipeline.csv_writer import append_to_csv
from pipeline.schema import SubmissionRecord
from pipeline.grouping import group_records, get_school_grade_records, get_all_school_names, get_grades_for_school
from pipeline.supabase_db import (
    init_database,
    save_record,
    get_records as get_db_records,
    get_record_by_id,
    update_record as update_db_record,
    delete_record as delete_db_record,
    get_stats as get_db_stats
)
from pipeline.validate import can_approve_record
# Removed batch_defaults - using simple bulk edit instead
# from pipeline.batch_defaults import create_upload_batch, get_batch_with_submissions, apply_batch_defaults
from auth.supabase_client import get_supabase_client, get_user_id
from jobs.queue import enqueue_submission, get_job_status, get_queue_status
from jobs.process_submission import process_submission_job
from jobs.redis_queue import get_redis_client
from utils.email_notification import get_review_url, send_batch_completion_email, get_user_email_from_token, send_smtp_email
from supabase import create_client

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))
app.logger.setLevel(logging.INFO)

# Configuration
UPLOAD_FOLDER = "artifacts"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Ensure required directories exist (for outputs/CSV)
Path("outputs").mkdir(exist_ok=True)

# Initialize Supabase database
init_database()

DB_STATS_TTL_SECONDS = 60
_db_stats_cache: Dict[str, Dict[str, Any]] = {}
_redis_client: Optional[redis.Redis] = None

def log_timing(message: str) -> None:
    """Log timing info through the app logger with a safe fallback."""
    print(message, flush=True)
    try:
        app.logger.info(message)
    except Exception:
        pass


def get_redis_client() -> Optional[redis.Redis]:
    """Return a shared Redis client for caching, or None if unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return None

    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        _redis_client = client
        return client
    except Exception as e:
        print(f"⚠️ Warning: Redis cache unavailable: {e}", flush=True)
        return None


def get_cached_db_stats(user_id: Optional[str], access_token: Optional[str], refresh_token: Optional[str]) -> Dict[str, int]:
    """Return cached stats for a user within TTL to avoid repeated count queries."""
    if not user_id:
        return {"total_count": 0, "clean_count": 0, "needs_review_count": 0}

    cache_key = f"db_stats:{user_id}"
    redis_client = get_redis_client()
    if redis_client:
        try:
            cached_value = redis_client.get(cache_key)
            if cached_value:
                return json.loads(cached_value)
        except Exception as e:
            print(f"⚠️ Warning: Redis cache read failed: {e}", flush=True)

    now = time.time()
    cached = _db_stats_cache.get(user_id)
    if cached and (now - cached["ts"]) < DB_STATS_TTL_SECONDS:
        return cached["stats"]

    stats = get_db_stats(owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token)
    _db_stats_cache[user_id] = {"ts": now, "stats": stats}
    if redis_client:
        try:
            redis_client.setex(cache_key, DB_STATS_TTL_SECONDS, json.dumps(stats))
        except Exception as e:
            print(f"⚠️ Warning: Redis cache write failed: {e}", flush=True)
    return stats


def get_cached_db_stats_cached_only(user_id: Optional[str]) -> Dict[str, int]:
    """
    Return cached stats without doing any Supabase queries.
    This keeps page renders instant; the UI can refresh stats asynchronously.
    """
    if not user_id:
        return {"total_count": 0, "clean_count": 0, "needs_review_count": 0}

    cached = _db_stats_cache.get(user_id)
    if cached and isinstance(cached.get("stats"), dict):
        return cached["stats"]

    redis_client = get_redis_client()
    if redis_client:
        try:
            cached_value = redis_client.get(f"db_stats:{user_id}")
            if cached_value:
                return json.loads(cached_value)
        except Exception as e:
            print(f"⚠️ Warning: Redis cache read failed: {e}", flush=True)

    return {"total_count": 0, "clean_count": 0, "needs_review_count": 0}


def invalidate_db_stats_cache(user_id: Optional[str]) -> None:
    """Remove cached stats for a user (both local and Redis)."""
    if not user_id:
        return
    _db_stats_cache.pop(user_id, None)
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.delete(f"db_stats:{user_id}")
        except Exception as e:
            print(f"⚠️ Warning: Redis cache delete failed: {e}", flush=True)


def format_review_reasons(reason_codes: str) -> str:
    """Convert stored review reason codes into human-readable format. Display only explicitly recorded reasons."""
    if not reason_codes or not (reason_codes or "").strip():
        return "Pending review"
    
    reason_map = {
        "MISSING_STUDENT_NAME": "Missing Student Name",
        "MISSING_SCHOOL_NAME": "Missing School Name",
        "MISSING_GRADE": "Missing Grade",
        "EMPTY_ESSAY": "Empty Essay",
        "SHORT_ESSAY": "Short Essay (< 50 words)",
        "LOW_CONFIDENCE": "Low OCR Confidence",
        "OCR_LOW_CONFIDENCE": "Low OCR Confidence",
        "TEMPLATE_ONLY": "Template Only (no submission)",
        "FIELD_ATTRIBUTION_RISK": "Field Attribution Risk",
        "PENDING_REVIEW": "Pending Manual Review"
    }
    
    codes = [c.strip() for c in (reason_codes or "").split(";") if c.strip()]
    readable_reasons = [reason_map.get(c, c.replace("_", " ").title()) for c in codes]
    return " • ".join(readable_reasons) if readable_reasons else "Pending review"


def get_pdf_path(artifact_dir: str, access_token: Optional[str] = None) -> Optional[str]:
    """Get the Supabase Storage path to the original PDF file."""
    if not artifact_dir:
        return None

    # artifact_dir is like "user_id/submission_id"
    # serve_pdf will try alternate extensions on demand.
    return f"{artifact_dir}/original.pdf"


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def require_auth():
    """Check if user is authenticated, redirect to login if not."""
    if "user_id" not in session or not session.get("user_id"):
        return False
    return True


@app.route("/")
def index():
    """Main dashboard."""
    if not require_auth():
        return redirect(url_for("login"))
    
    user_id = session.get("user_id")
    db_stats = get_cached_db_stats_cached_only(user_id)
    
    resp = make_response(render_template("dashboard.html",
                         user_email=session.get("user_email"),
                         db_stats=db_stats))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page with magic link authentication."""
    # Check if already logged in
    if require_auth():
        return redirect(url_for("index"))
    
    supabase = get_supabase_client()
    if not supabase:
        flash("Authentication is not configured. Please set SUPABASE_URL and SUPABASE_ANON_KEY.", "error")
        return render_template("login.html")
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        
        if not email or "@" not in email:
            flash("Please enter a valid email address.", "error")
            return render_template("login.html")
        
        try:
            # Redirect URL for magic link: use APP_URL in production so the link points to the public app URL
            app_url = (os.environ.get("APP_URL") or "").strip().rstrip("/")
            if app_url:
                redirect_url = f"{app_url}/auth/callback"
            else:
                redirect_url = f"{request.scheme}://{request.host}/auth/callback"
            
            supabase.auth.sign_in_with_otp({
                "email": email,
                "options": {
                    "email_redirect_to": redirect_url,
                    "should_create_user": True
                }
            })
            
            flash(f"✅ Login link sent! Check your email at {email}", "success")
            return render_template("login.html", email_sent=True, email=email)
        except Exception as e:
            error_msg = str(e)
            if "signups disabled" in error_msg.lower():
                flash("Registration is currently disabled. Please contact your administrator.", "error")
            elif "rate limit" in error_msg.lower():
                flash("Too many requests. Please wait a few minutes.", "error")
            else:
                flash(f"Error sending login link: {error_msg}", "error")
    
    return render_template("login.html")


@app.route("/auth/callback")
def auth_callback():
    """Handle Supabase magic link callback."""
    access_token = request.args.get("access_token")
    refresh_token = request.args.get("refresh_token")
    expires_at = request.args.get("expires_at")
    
    # If no tokens in query params, extract from hash fragment using JavaScript
    if not access_token:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authenticating...</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            </style>
        </head>
        <body>
            <h2>🔐 Processing authentication...</h2>
            <div class="spinner"></div>
            <p>Please wait while we log you in...</p>
            <script>
                if (window.location.hash) {
                    const hash = window.location.hash.substring(1);
                    const params = new URLSearchParams(hash);
                    const accessToken = params.get('access_token');
                    const refreshToken = params.get('refresh_token');
                    const expiresAt = params.get('expires_at');
                    
                    if (accessToken) {
                        const callbackUrl = '/auth/callback?access_token=' + encodeURIComponent(accessToken) +
                                          (refreshToken ? '&refresh_token=' + encodeURIComponent(refreshToken) : '') +
                                          (expiresAt ? '&expires_at=' + encodeURIComponent(expiresAt) : '');
                        window.location.replace(callbackUrl);
                    } else {
                        document.body.innerHTML = '<h2>❌ Error: No access token found</h2><p>The login link may be invalid or expired.</p>';
                    }
                } else {
                    document.body.innerHTML = '<h2>❌ Error: No authentication data found</h2><p>Please try requesting a new login link.</p>';
                }
            </script>
        </body>
        </html>
        """, 200
    
    # Process authentication
    try:
        supabase = get_supabase_client()
        # Ensure refresh_token is provided (required by Supabase)
        if not refresh_token:
            refresh_token = ""
        
        # Set session - Supabase requires both tokens
        session_response = supabase.auth.set_session(
            access_token=access_token,
            refresh_token=refresh_token
        )
        
        user_response = supabase.auth.get_user()
        
        if user_response and user_response.user:
            # Store in Flask session
            session["user_id"] = user_response.user.id
            session["user_email"] = user_response.user.email
            session["supabase_access_token"] = access_token
            if refresh_token:
                session["supabase_refresh_token"] = refresh_token
            
            flash("✅ Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("❌ Authentication failed: Could not retrieve user information.", "error")
            return redirect(url_for("login"))
    except Exception as e:
        flash(f"❌ Authentication error: {str(e)}", "error")
        return redirect(url_for("login"))


@app.route("/clear_results", methods=["POST"])
def clear_results():
    """Clear processing results from session."""
    if "upload_results" in session:
        del session["upload_results"]
    return redirect(url_for("index"))


@app.route("/api/clear_jobs", methods=["POST"])
def clear_jobs():
    """Clear job tracking from session after processing completes."""
    if not require_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    # Clear job tracking
    if "processing_jobs" in session:
        del session["processing_jobs"]
    if "total_files" in session:
        del session["total_files"]
    if "processed_count" in session:
        del session["processed_count"]
    
    return jsonify({"success": True})


@app.route("/api/test-email", methods=["POST"])
def api_test_email():
    """Send a test email to verify Gmail (EMAIL + GMAIL_PASSWORD) is configured."""
    if not require_auth():
        return jsonify({"error": "Unauthorized"}), 401

    to_email = None
    if request.is_json:
        to_email = (request.get_json() or {}).get("to")
    if not to_email:
        access_token = session.get("supabase_access_token")
        to_email = get_user_email_from_token(access_token)
    if not to_email:
        return jsonify({"success": False, "error": "No email address. Log in or send JSON body: {\"to\": \"your@email.com\"}"}), 400

    subject = "IFI Essay Tool – test email"
    html_body = "<p>If you received this, Gmail (EMAIL + GMAIL_PASSWORD) is configured correctly.</p>"
    text_body = "If you received this, Gmail (EMAIL + GMAIL_PASSWORD) is configured correctly."
    ok = send_smtp_email(to_email, subject, html_body, text_body)
    if ok:
        return jsonify({"success": True, "message": f"Test email sent to {to_email}"})
    return jsonify({"success": False, "error": "Sending failed. Check EMAIL and GMAIL_PASSWORD in .env and container logs."}), 500


@app.route("/logout")
def logout():
    """Logout user."""
    session.clear()
    flash("✅ Logged out successfully!", "success")
    return redirect(url_for("login"))


@app.route("/upload", methods=["POST"])
def upload():
    """Handle file upload and processing."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    
    if "files" not in request.files:
        return jsonify({"success": False, "error": "No files selected"}), 400
    
    files = request.files.getlist("files")
    upload_mode = request.form.get("upload_mode", "single")
    
    if not files or files[0].filename == "":
        return jsonify({"success": False, "error": "Please select at least one file"}), 400
    
    ocr_provider = "google"
    job_ids = []
    errors = []
    import hashlib
    from pipeline.supabase_db import check_duplicate_submission

    refresh_token = session.get("supabase_refresh_token")
    upload_batch_id = session.get("upload_batch_id")

    # First pass: build work items so we know total for batch-run tracking
    work_items = []
    for file in files:
        if file and allowed_file(file.filename):
            try:
                file_bytes = file.read()
                sha256_hash = hashlib.sha256(file_bytes).hexdigest()
                submission_id = sha256_hash[:12]
                duplicate_info = check_duplicate_submission(
                    submission_id=submission_id,
                    current_user_id=user_id,
                    access_token=access_token,
                    refresh_token=refresh_token
                )
                work_items.append((file, file_bytes, file.filename, submission_id, duplicate_info))
            except Exception as e:
                errors.append(f"{file.filename}: {str(e)}")

    total = len(work_items)
    if total == 0:
        return jsonify({
            "success": False,
            "error": "No valid files to process. " + ("Errors: " + "; ".join(errors) if errors else "")
        }), 400

    # Create batch run so we send one email when all jobs complete (async path)
    batch_run_id = str(uuid.uuid4())
    try:
        r = get_redis_client()
        r.setex(
            f"batch_run:{batch_run_id}",
            86400,
            json.dumps({"total": total, "access_token": access_token, "upload_batch_id": upload_batch_id or ""}),
        )
        app.logger.info(f"📬 Batch run created: batch_run_id={batch_run_id[:8]}... total={total} (email after all jobs complete)")
    except Exception as e:
        app.logger.warning(f"Redis unavailable for batch_run; sync path will send one email after loop: {e}")
        batch_run_id = None  # Redis down; sync path will send one email after loop

    used_sync = False
    for file, file_bytes, filename, submission_id, duplicate_info in work_items:
        try:
            try:
                job_id = enqueue_submission(
                    file_bytes=file_bytes,
                    filename=filename,
                    owner_user_id=user_id,
                    access_token=access_token,
                    ocr_provider=ocr_provider,
                    upload_batch_id=upload_batch_id,
                    batch_run_id=batch_run_id,
                )
            except Exception as e:
                app.logger.warning(f"Queue unavailable ({e}), processing {filename} synchronously")
                process_submission_job(
                    file_bytes=file_bytes,
                    filename=filename,
                    owner_user_id=user_id,
                    access_token=access_token,
                    ocr_provider=ocr_provider,
                    upload_batch_id=upload_batch_id,
                    batch_run_id=None,
                )
                job_id = f"sync-{submission_id}"
                used_sync = True
            job_ids.append({
                "filename": filename,
                "job_id": job_id,
                "is_duplicate": duplicate_info.get("is_duplicate", False),
                "is_own_duplicate": duplicate_info.get("is_own_duplicate", False),
            })
        except Exception as e:
            errors.append(f"{filename}: {str(e)}")
            app.logger.exception(f"Error processing {filename}")

    # When all processing was sync (Redis down), send one batch completion email here
    if used_sync and job_ids:
        try:
            user_email = get_user_email_from_token(access_token)
            if user_email:
                app.logger.info(f"📧 Sending batch completion email to {user_email} (sync path, {len(job_ids)} files)")
                review_url = get_review_url(upload_batch_id)
                send_batch_completion_email(user_email, len(job_ids), review_url)
                app.logger.info("✅ Batch completion email sent (sync)")
            else:
                app.logger.warning("No user email from token; skipping batch completion email")
        except Exception as email_err:
            app.logger.warning(f"Failed to send batch completion email: {email_err}")

    if not job_ids:
        return jsonify({
            "success": False,
            "error": "Failed to enqueue any files. " + ("Errors: " + "; ".join(errors) if errors else "Check connection.")
        }), 500
    
    # Store job IDs in session for progress tracking
    session["processing_jobs"] = job_ids
    session["total_files"] = len(job_ids)
    session["processed_count"] = 0
    
    return jsonify({
        "success": True,
        "job_ids": job_ids,
        "total": len(job_ids),
        "errors": errors if errors else None
    })


@app.route("/api/scan_duplicates", methods=["POST"])
def scan_duplicates():
    """Scan uploaded files for duplicate submissions without enqueueing."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")

    if "files" not in request.files:
        return jsonify({"success": False, "error": "No files selected"}), 400

    files = request.files.getlist("files")
    if not files or files[0].filename == "":
        return jsonify({"success": False, "error": "Please select at least one file"}), 400

    results = []
    errors = []

    from pipeline.supabase_db import check_duplicate_submission
    import hashlib

    for idx, file in enumerate(files):
        if file and allowed_file(file.filename):
            try:
                file_bytes = file.read()
                sha256_hash = hashlib.sha256(file_bytes).hexdigest()
                submission_id = sha256_hash[:12]

                refresh_token = session.get("supabase_refresh_token")
                duplicate_info = check_duplicate_submission(
                    submission_id=submission_id,
                    current_user_id=user_id,
                    access_token=access_token,
                    refresh_token=refresh_token
                )
                results.append({
                    "index": idx,
                    "filename": file.filename,
                    "submission_id": submission_id,
                    "is_duplicate": duplicate_info.get("is_duplicate", False),
                    "is_own_duplicate": duplicate_info.get("is_own_duplicate", False),
                    "existing_filename": duplicate_info.get("existing_filename")
                })
            except Exception as e:
                errors.append(f"{file.filename}: {str(e)}")
        else:
            errors.append(f"{file.filename}: Invalid file type")

    if not results:
        return jsonify({"success": False, "error": "No valid files to scan.", "errors": errors}), 400

    return jsonify({
        "success": True,
        "results": results,
        "errors": errors if errors else None
    })


@app.route("/review")
def review():
    """Review and approval workflow page with School→Grade grouping."""
    if not require_auth():
        return redirect(url_for("login"))
    
    route_start = time.perf_counter()
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    refresh_token = session.get("supabase_refresh_token")
    review_mode = request.args.get("mode", "needs_review")
    
    # Get current batch ID from session (if available), or find most recent batch with submissions needing review
    upload_batch_id = session.get("upload_batch_id")
    batch_info = None
    
    if review_mode == "needs_review":
        needs_review_fields = [
            "submission_id",
            "student_name",
            "school_name",
            "grade",
            "teacher_name",
            "city_or_location",
            "father_figure_name",
            "phone",
            "email",
            "word_count",
            "needs_review",
            "review_reason_codes",
            "artifact_dir"
        ]
        if not upload_batch_id:
            needs_review_fields.append("upload_batch_id")

        records_start = time.perf_counter()
        records = get_db_records(
            needs_review=True,
            owner_user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            select_fields=needs_review_fields
        )
        log_timing(f"⏱️ review needs_review records: {(time.perf_counter() - records_start):.3f}s ({len(records)} rows)")

        # If no batch in session, try to find the most recent batch with submissions needing review
        if not upload_batch_id:
            batch_lookup_start = time.perf_counter()
            batch_ids = {r.get("upload_batch_id") for r in records if r.get("upload_batch_id")}
            log_timing(f"⏱️ review needs_review batch lookup: {(time.perf_counter() - batch_lookup_start):.3f}s ({len(batch_ids)} batches)")

            if batch_ids:
                try:
                    supabase = get_supabase_client(access_token=access_token)
                    if supabase and access_token:
                        try:
                            supabase.auth.set_session(access_token=access_token, refresh_token="")
                        except:
                            pass

                    batch_fetch_start = time.perf_counter()
                    batches_result = supabase.table("upload_batches").select("*").eq("owner_user_id", user_id).in_("id", list(batch_ids)).order("created_at", desc=True).limit(1).execute()
                    log_timing(f"⏱️ review upload_batches query: {(time.perf_counter() - batch_fetch_start):.3f}s")

                    if batches_result.data and len(batches_result.data) > 0:
                        upload_batch_id = str(batches_result.data[0]["id"])
                        batch_info_start = time.perf_counter()
                        batch_info = get_batch_with_submissions(upload_batch_id, owner_user_id=user_id, access_token=access_token)
                        log_timing(f"⏱️ review batch_info fetch: {(time.perf_counter() - batch_info_start):.3f}s")
                except Exception as e:
                    print(f"⚠️ Warning: Could not fetch batch: {e}")
                    import traceback
                    traceback.print_exc()

        # If we have a batch_id from session, get its info
        if upload_batch_id and not batch_info:
            batch_info = get_batch_with_submissions(upload_batch_id, owner_user_id=user_id, access_token=access_token)

        action_label = "Approve"
        schools_data = None
    else:
        # For approved records, show grouped by school and grade
        approved_start = time.perf_counter()
        approved_records = get_db_records(
            needs_review=False,
            owner_user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            select_fields=[
                "submission_id",
                "student_name",
                "school_name",
                "grade",
                "father_figure_name",
                "word_count",
                "artifact_dir"
            ]
        )
        log_timing(f"⏱️ review approved records: {(time.perf_counter() - approved_start):.3f}s ({len(approved_records)} rows)")
        group_start = time.perf_counter()
        grouped = group_records(approved_records)
        log_timing(f"⏱️ review group_records: {(time.perf_counter() - group_start):.3f}s")
        records = []  # Not used when showing grouped view
        schools_data = dict(sorted(grouped["schools"].items()))
        # Sort grades within each school
        for school_name in schools_data:
            schools_data[school_name] = dict(sorted(schools_data[school_name].items(), 
                                                   key=lambda x: (str(x[0]).isdigit(), str(x[0]).lower())))
        action_label = "Send for Review"
    
    # Always fetch fresh stats on review page so cards match the record list (no delay)
    db_stats = get_db_stats(owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token)
    now = time.time()
    _db_stats_cache[user_id] = {"ts": now, "stats": db_stats}
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.setex(f"db_stats:{user_id}", DB_STATS_TTL_SECONDS, json.dumps(db_stats))
        except Exception:
            pass
    log_timing(f"⏱️ review total: {(time.perf_counter() - route_start):.3f}s (mode={review_mode})")
    
    return render_template("review.html",
                         records=records,
                         review_mode=review_mode,
                         action_label=action_label,
                         db_stats=db_stats,
                         format_review_reasons=format_review_reasons,
                         get_pdf_path=lambda ad: get_pdf_path(ad, session.get("supabase_access_token")),
                         grouped_data=grouped if review_mode == "approved" else None,
                         schools_data=schools_data,
                         batch_info=batch_info,
                         upload_batch_id=upload_batch_id)


@app.route("/api/db_stats")
def api_db_stats():
    """Return per-user database stats (optionally bypassing cache)."""
    if not require_auth():
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    refresh_token = session.get("supabase_refresh_token")
    fresh = request.args.get("fresh") == "1"

    if not user_id:
        return jsonify({"total_count": 0, "clean_count": 0, "needs_review_count": 0})

    if not fresh:
        return jsonify(get_cached_db_stats(user_id, access_token, refresh_token))

    stats = get_db_stats(owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token)

    now = time.time()
    _db_stats_cache[user_id] = {"ts": now, "stats": stats}
    redis_client = get_redis_client()
    if redis_client:
        try:
            redis_client.setex(f"db_stats:{user_id}", DB_STATS_TTL_SECONDS, json.dumps(stats))
        except Exception as e:
            print(f"⚠️ Warning: Redis cache write failed: {e}", flush=True)

    return jsonify(stats)


@app.route("/record/<submission_id>", methods=["GET", "POST"])
def record_detail(submission_id):
    """View and edit a specific record."""
    if not require_auth():
        return redirect(url_for("login"))
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    refresh_token = session.get("supabase_refresh_token")
    record = get_record_by_id(submission_id, owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token)
    
    if not record:
        flash("Record not found.", "error")
        return redirect(url_for("review"))
    
    if request.method == "POST":
        # Update record - support both individual edits and bulk edits
        updates = {}
        
        # Only update fields that are provided (for bulk edits, only school_name and grade might be provided)
        if "student_name" in request.form:
            updates["student_name"] = request.form.get("student_name", "").strip() or None
        if "school_name" in request.form:
            updates["school_name"] = request.form.get("school_name", "").strip() or None
        if "grade" in request.form:
            updates["grade"] = request.form.get("grade", "").strip() or None
        if "teacher_name" in request.form:
            updates["teacher_name"] = request.form.get("teacher_name", "").strip() or None
        if "city_or_location" in request.form:
            updates["city_or_location"] = request.form.get("city_or_location", "").strip() or None
        if "father_figure_name" in request.form:
            updates["father_figure_name"] = request.form.get("father_figure_name", "").strip() or None
        if "phone" in request.form:
            updates["phone"] = request.form.get("phone", "").strip() or None
        if "email" in request.form:
            updates["email"] = request.form.get("email", "").strip() or None
        
        # Note: Removed school_source, grade_source, teacher_source tracking
        # These columns don't exist in the database for simple bulk edit
        
        # Parse grade - keep as string if it's text like "Kindergarten", "K", etc.
        # Otherwise try to extract number
        if updates["grade"]:
            grade_str = updates["grade"].strip()
            grade_upper = grade_str.upper()
            
            # Check if it's a kindergarten variant
            if grade_upper in ["K", "KINDER", "KINDERGARTEN", "PRE-K", "PREK"]:
                updates["grade"] = "K"  # Standardize to "K"
            else:
                # Try to extract number
                grade_match = re.search(r'\d+', grade_str)
                if grade_match:
                    grade_int = int(grade_match.group())
                    if 1 <= grade_int <= 12:
                        updates["grade"] = grade_int
                    else:
                        # Invalid number, keep as text
                        updates["grade"] = grade_str
                else:
                    # No number found, keep as text (e.g., "Pre-Kindergarten", "First Grade")
                    updates["grade"] = grade_str
        
        # Auto-reassignment: If record now has school_name and grade, check if it can be auto-approved
        # This happens when a record that was missing school/grade gets those fields filled in
        auto_approve = False
        if updates.get("school_name") and updates.get("grade"):
            # Check if record can now be approved (has all required fields)
            can_approve, missing_fields = can_approve_record({
                "student_name": updates.get("student_name") or record.get("student_name"),
                "school_name": updates["school_name"],
                "grade": updates["grade"]
            })
            
            # If record was in needs_review and now has all required fields, auto-approve it
            if can_approve and record.get("needs_review", True):
                updates["needs_review"] = False
                auto_approve = True
            elif not can_approve:
                # Still missing fields, keep in needs_review
                updates["needs_review"] = True
        
        access_token = session.get("supabase_access_token")
        refresh_token = session.get("supabase_refresh_token")
        if update_db_record(submission_id, updates, owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token):
            # Only show success message after update succeeds
            if auto_approve:
                flash("✅ Record updated and automatically moved to approved batch!", "success")
            else:
                flash("✅ Record updated successfully!", "success")
        else:
            flash("❌ Failed to update record.", "error")
        
        return redirect(url_for("record_detail", submission_id=submission_id))
    
    access_token = session.get("supabase_access_token")
    pdf_path = get_pdf_path(record.get("artifact_dir", ""), access_token=access_token)
    
    return render_template("record_detail.html",
                         record=record,
                         pdf_path=pdf_path,
                         format_review_reasons=format_review_reasons)


@app.route("/record/<submission_id>/approve", methods=["POST"])
def approve_record(submission_id):
    """Approve a record (move to clean)."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    refresh_token = session.get("supabase_refresh_token")
    record = get_record_by_id(submission_id, owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token)
    
    if not record:
        return jsonify({"success": False, "error": "Record not found"}), 404
    
    # Check if can approve
    can_approve, missing_fields = can_approve_record({
        "student_name": record.get("student_name"),
        "school_name": record.get("school_name"),
        "grade": record.get("grade")
    })
    
    if not can_approve:
        missing_fields_str = ", ".join(missing_fields).replace("_", " ").title()
        return jsonify({
            "success": False,
            "error": f"Missing required fields: {missing_fields_str}"
        }), 400
    
    refresh_token = session.get("supabase_refresh_token")
    if update_db_record(submission_id, {"needs_review": False}, owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token):
        invalidate_db_stats_cache(user_id)
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Failed to update record"}), 500


@app.route("/record/<submission_id>/send_for_review", methods=["POST"])
def send_for_review(submission_id):
    """Send a record for review."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    
    refresh_token = session.get("supabase_refresh_token")
    if update_db_record(submission_id, {"needs_review": True}, owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token):
        invalidate_db_stats_cache(user_id)
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Failed to update record"}), 500


@app.route("/api/bulk_update_records", methods=["POST"])
def bulk_update_records():
    """Apply bulk updates to selected records."""
    if not require_auth():
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    
    data = request.get_json()
    selected_ids = data.get("selected_ids", [])
    school_name = data.get("school_name", "").strip() or None
    grade = data.get("grade", "").strip() or None
    
    if not selected_ids:
        return jsonify({"success": False, "error": "No records selected for bulk update."}), 400
    
    if not school_name and not grade:
        return jsonify({"success": False, "error": "Please provide a school name or grade for bulk update."}), 400
    
    updated_count = 0
    errors = []
    
    for submission_id in selected_ids:
        updates = {}
        if school_name:
            updates["school_name"] = school_name
        if grade:
            # Parse grade - handle text values like "K", "Kindergarten", etc.
            grade_upper = grade.upper() if grade else ""
            if grade_upper in ["K", "KINDER", "KINDERGARTEN"]:
                updates["grade"] = "K"
            elif grade_upper in ["PRE-K", "PREK", "PRE-KINDERGARTEN"]:
                updates["grade"] = "Pre-K"
            else:
                # Try to extract number
                grade_match = re.search(r'\d+', grade)
                if grade_match:
                    grade_int = int(grade_match.group())
                    if 1 <= grade_int <= 12:
                        updates["grade"] = grade_int
                    else:
                        updates["grade"] = grade  # Keep as text if out of range
                else:
                    updates["grade"] = grade  # Keep as text if no number found
        
        try:
            refresh_token = session.get("supabase_refresh_token")
            if update_db_record(submission_id, updates, owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token):
                updated_count += 1
            else:
                errors.append(f"Failed to update {submission_id}")
        except Exception as e:
            errors.append(f"Error updating {submission_id}: {str(e)}")
    
    if errors:
        return jsonify({
            "success": False,
            "updated_count": updated_count,
            "errors": errors,
            "message": f"Updated {updated_count} records with errors."
        }), 500

    invalidate_db_stats_cache(user_id)
    return jsonify({
        "success": True,
        "updated_count": updated_count,
        "message": f"Successfully updated {updated_count} records."
    })


@app.route("/api/bulk_delete_records", methods=["POST"])
def bulk_delete_records():
    """Delete selected submission records and their storage files."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    refresh_token = session.get("supabase_refresh_token")
    data = request.get_json() or {}
    selected_ids = data.get("selected_ids", [])

    if not selected_ids:
        return jsonify({"success": False, "error": "No records selected for deletion."}), 400

    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    sb = create_client(supabase_url, service_role_key) if (service_role_key and supabase_url) else None

    deleted_count = 0
    errors = []

    for submission_id in selected_ids:
        record = get_record_by_id(submission_id, owner_user_id=user_id, access_token=access_token)
        if record:
            artifact_dir = record.get("artifact_dir", "")
            if artifact_dir and sb:
                try:
                    paths = [f"{artifact_dir}/original.{ext}" for ext in ["pdf", "png", "jpg", "jpeg"]]
                    sb.storage.from_("essay-submissions").remove(paths)
                except Exception as e:
                    app.logger.warning(f"Storage delete warning for {submission_id}: {e}")

        if delete_db_record(submission_id, owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token):
            deleted_count += 1
        else:
            errors.append(submission_id)

    invalidate_db_stats_cache(user_id)

    if errors:
        return jsonify({
            "success": False,
            "deleted_count": deleted_count,
            "errors": errors,
            "message": f"Deleted {deleted_count} records; failed to delete {len(errors)}."
        }), 500

    return jsonify({
        "success": True,
        "deleted_count": deleted_count,
        "message": f"Successfully deleted {deleted_count} record(s)."
    })


@app.route("/record/<submission_id>/delete", methods=["POST"])
def delete_record(submission_id):
    """Delete a record and its files from storage."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    refresh_token = session.get("supabase_refresh_token")

    # Fetch the record to get artifact_dir before deleting
    record = get_record_by_id(submission_id, owner_user_id=user_id, access_token=access_token)
    if record:
        artifact_dir = record.get("artifact_dir", "")
        if artifact_dir:
            # Delete files from storage using service role key (anon key lacks delete permission)
            service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            sb = create_client(os.environ["SUPABASE_URL"], service_role_key)
            paths = [f"{artifact_dir}/original.{ext}" for ext in ["pdf", "png", "jpg", "jpeg"]]
            try:
                sb.storage.from_("essay-submissions").remove(paths)
            except Exception as e:
                app.logger.warning(f"Storage delete warning: {e}")

    if delete_db_record(submission_id, owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token):
        invalidate_db_stats_cache(user_id)
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Failed to delete record"}), 500


@app.route("/record/<submission_id>/reprocess", methods=["POST"])
def reprocess_record(submission_id):
    """Re-download the original file from storage and re-run the pipeline."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401

    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")

    # 1. Fetch the existing record to get artifact_dir and filename
    record = get_record_by_id(submission_id, owner_user_id=user_id, access_token=access_token)
    if not record:
        return jsonify({"success": False, "error": "Record not found"}), 404

    artifact_dir = record.get("artifact_dir", "")
    filename = record.get("filename", "unknown.pdf")

    if not artifact_dir:
        return jsonify({"success": False, "error": "No artifact directory — cannot retrieve original file"}), 400

    # 2. Download the original file from Supabase Storage (try multiple extensions)
    file_bytes = None
    for ext in ["pdf", "png", "jpg", "jpeg"]:
        storage_path = f"{artifact_dir}/original.{ext}"
        file_bytes = download_file(storage_path, access_token=access_token)
        if file_bytes:
            break

    if not file_bytes:
        return jsonify({"success": False, "error": "Original file not found in storage"}), 404

    # 3. Delete the old record so the worker can create a fresh one
    refresh_token = session.get("supabase_refresh_token")
    delete_db_record(submission_id, owner_user_id=user_id, access_token=access_token, refresh_token=refresh_token)

    # 4. Enqueue a new processing job
    try:
        job_id = enqueue_submission(
            file_bytes=file_bytes,
            filename=filename,
            owner_user_id=user_id,
            access_token=access_token,
            ocr_provider="google",
        )
        invalidate_db_stats_cache(user_id)
        app.logger.info(f"♻️ Reprocess enqueued for {submission_id} → job {job_id}")
        return jsonify({"success": True, "job_id": job_id})
    except Exception as e:
        app.logger.error(f"❌ Reprocess failed for {submission_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def _export_records_to_csv(records: List[Dict]) -> io.BytesIO:
    """
    Helper function to export records to CSV with PDF URLs.
    
    Args:
        records: List of record dictionaries
        
    Returns:
        BytesIO object with CSV data
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers - added pdf_url column
    headers = [
        "submission_id", "student_name", "school_name", "grade",
        "teacher_name", "city_or_location", "father_figure_name",
        "phone", "email", "word_count", "ocr_confidence_avg",
        "review_reason_codes", "artifact_dir", "filename", "pdf_url"
    ]
    writer.writerow(headers)
    
    # Get access token for generating PDF URLs (if available from session)
    # Note: This function might be called from routes that have access_token in session
    access_token = session.get("supabase_access_token") if hasattr(session, 'get') else None
    
    # Write records
    for record_dict in records:
        # Generate PDF URL from artifact_dir
        pdf_url = ""
        artifact_dir = record_dict.get("artifact_dir", "")
        
        if artifact_dir:
            # Try to get PDF path (handles .pdf, .png, .jpg, .jpeg)
            pdf_path = get_pdf_path(artifact_dir, access_token=access_token)
            
            if pdf_path:
                # Get the direct Supabase Storage public URL (shareable, no authentication required)
                try:
                    pdf_url = get_file_url(pdf_path, access_token=access_token)
                    if not pdf_url:
                        # Fallback: construct URL manually if get_file_url fails
                        supabase_url = os.environ.get("SUPABASE_URL", "")
                        if supabase_url:
                            # Public URL format: https://[project].supabase.co/storage/v1/object/public/[bucket]/[path]
                            pdf_url = f"{supabase_url}/storage/v1/object/public/{BUCKET_NAME}/{pdf_path}"
                except Exception as e:
                    print(f"⚠️ Warning: Could not generate PDF URL for {artifact_dir}: {e}")
                    pdf_url = ""
        
        row = [
            record_dict.get("submission_id", ""),
            record_dict.get("student_name", ""),
            record_dict.get("school_name", ""),
            record_dict.get("grade", ""),
            record_dict.get("teacher_name", ""),
            record_dict.get("city_or_location", ""),
            record_dict.get("father_figure_name", ""),
            record_dict.get("phone", ""),
            record_dict.get("email", ""),
            record_dict.get("word_count", 0),
            f"{record_dict.get('ocr_confidence_avg', 0):.2f}" if record_dict.get("ocr_confidence_avg") else "",
            record_dict.get("review_reason_codes", ""),
            record_dict.get("artifact_dir", ""),
            record_dict.get("filename", ""),
            pdf_url  # Add PDF URL
        ]
        writer.writerow(row)
    
    csv_data = output.getvalue()
    return io.BytesIO(csv_data.encode())


@app.route("/export")
def export_csv():
    """Export all clean records to CSV with PDF URLs."""
    if not require_auth():
        return redirect(url_for("login"))
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    records = get_db_records(needs_review=False, owner_user_id=user_id, access_token=access_token)

    csv_buffer = _export_records_to_csv(records, access_token=access_token)
    
    return send_file(
        csv_buffer,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"clean_records_export_{len(records)}_records.csv"
    )


@app.route("/export/school/<path:school_name>")
def export_school_csv(school_name: str):
    """Export all records for a specific school to CSV."""
    if not require_auth():
        return redirect(url_for("login"))
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    
    # Get all clean records
    all_records = get_db_records(needs_review=False, owner_user_id=user_id, access_token=access_token)
    
    # Filter by school name (case-insensitive, normalized)
    from pipeline.grouping import normalize_key
    school_key = normalize_key(school_name)
    school_records = [
        r for r in all_records
        if normalize_key(r.get("school_name", "")) == school_key
    ]
    
    csv_buffer = _export_records_to_csv(school_records, access_token=access_token)
    
    # Sanitize school name for filename
    safe_school_name = "".join(c for c in school_name if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_school_name = safe_school_name.replace(' ', '_')
    
    return send_file(
        csv_buffer,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"school_{safe_school_name}_export_{len(school_records)}_records.csv"
    )


@app.route("/export/school/<path:school_name>/grade/<path:grade>")
def export_grade_csv(school_name: str, grade: str):
    """Export all records for a specific school and grade to CSV."""
    if not require_auth():
        return redirect(url_for("login"))
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    
    # Get all clean records
    all_records = get_db_records(needs_review=False, owner_user_id=user_id, access_token=access_token)
    
    # Filter by school name and grade (case-insensitive, normalized)
    from pipeline.grouping import normalize_key
    school_key = normalize_key(school_name)
    grade_key = normalize_key(str(grade))
    
    grade_records = [
        r for r in all_records
        if normalize_key(r.get("school_name", "")) == school_key and
           normalize_key(str(r.get("grade", ""))) == grade_key
    ]
    
    csv_buffer = _export_records_to_csv(grade_records, access_token=access_token)
    
    # Sanitize names for filename
    safe_school_name = "".join(c for c in school_name if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_school_name = safe_school_name.replace(' ', '_')
    safe_grade = "".join(c for c in str(grade) if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_grade = safe_grade.replace(' ', '_')
    
    return send_file(
        csv_buffer,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"school_{safe_school_name}_grade_{safe_grade}_export_{len(grade_records)}_records.csv"
    )


@app.route("/pdf/<path:file_path>")
def serve_pdf(file_path):
    """Serve PDF/image files from Supabase Storage."""
    if not require_auth():
        return "Unauthorized", 401

    access_token = session.get("supabase_access_token")

    # file_path can be chunk path (user_id/run_id/artifacts/run_id/chunk_0_xxx/original.pdf)
    # but the original file is uploaded only at top level: user_id/run_id/original.pdf
    # Try requested path first, then alternate extensions, then top-level path for chunk paths
    file_bytes = download_file(file_path, access_token=access_token)

    if not file_bytes and file_path.endswith((".pdf", ".png", ".jpg", ".jpeg")):
        base_path = file_path.rsplit(".", 1)[0]
        for ext in [".pdf", ".png", ".jpg", ".jpeg"]:
            if not file_path.endswith(ext):
                alt_path = f"{base_path}{ext}"
                file_bytes = download_file(alt_path, access_token=access_token)
                if file_bytes:
                    file_path = alt_path
                    break

    # Chunk artifact_dir points to a folder that has no original.pdf; the original is at user_id/run_id/original.*
    if not file_bytes and "/artifacts/" in file_path:
        parts = file_path.split("/")
        if len(parts) >= 2:
            top_level = f"{parts[0]}/{parts[1]}"
            for ext in [".pdf", ".png", ".jpg", ".jpeg"]:
                candidate = f"{top_level}/original{ext}"
                file_bytes = download_file(candidate, access_token=access_token)
                if file_bytes:
                    file_path = candidate
                    break

    if file_bytes:
        # Determine content type
        if file_path.endswith(".pdf"):
            mimetype = "application/pdf"
        elif file_path.endswith(".png"):
            mimetype = "image/png"
        elif file_path.endswith((".jpg", ".jpeg")):
            mimetype = "image/jpeg"
        else:
            mimetype = "application/octet-stream"
        
        return send_file(
            io.BytesIO(file_bytes),
            mimetype=mimetype,
            download_name=Path(file_path).name
        )
    
    # Log the error for debugging
    print(f"❌ Could not serve file: {file_path}")
    return f"File not found: {file_path}", 404


@app.route("/jobs/<job_id>")
def job_detail(job_id):
    """View job status page."""
    if not require_auth():
        return redirect(url_for("login"))
    
    access_token = session.get("supabase_access_token")
    user_id = session.get("user_id")
    
    # Get job status
    status = get_job_status(job_id, access_token=access_token)
    
    # Verify user owns this job (if possible to check)
    # RQ doesn't store user_id in job metadata easily, so we'll allow access
    # In production, you might want to store user_id in job metadata
    
    return render_template("job_status.html",
                         job_id=job_id,
                         job_status=status)


@app.route("/api/job_status/<job_id>")
def job_status(job_id):
    """Get the status of a processing job (API endpoint)."""
    if not require_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    access_token = session.get("supabase_access_token")
    status = get_job_status(job_id, access_token=access_token)
    return jsonify(status)


@app.route("/api/batches/<upload_batch_id>", methods=["GET"])
def get_batch(upload_batch_id: str):
    """Get batch details with submissions."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    
    batch = get_batch_with_submissions(upload_batch_id, owner_user_id=user_id, access_token=access_token)
    
    if not batch:
        return jsonify({"success": False, "error": "Batch not found"}), 404
    
    return jsonify({"success": True, "batch": batch})


@app.route("/api/batches/<upload_batch_id>/apply-defaults", methods=["POST"])
def apply_defaults(upload_batch_id: str):
    """Apply batch defaults to all submissions in the batch."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    
    data = request.get_json()
    default_school_name = data.get("default_school_name", "").strip() or None
    default_grade = data.get("default_grade", "").strip() or None
    default_teacher_name = data.get("default_teacher_name", "").strip() or None
    
    # At least one default must be provided
    if not any([default_school_name, default_grade, default_teacher_name]):
        return jsonify({"success": False, "error": "At least one default value must be provided"}), 400
    
    result = apply_batch_defaults(
        upload_batch_id=upload_batch_id,
        default_school_name=default_school_name,
        default_grade=default_grade,
        default_teacher_name=default_teacher_name,
        owner_user_id=user_id,
        access_token=access_token
    )
    
    if result.get("success"):
        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route("/api/batch_status")
def batch_status():
    """Get status of all jobs in current batch using Redis/RQ."""
    if not require_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session.get("user_id")
    job_ids_in_session = session.get("processing_jobs", [])
    
    # Extract job IDs from session (from Redis/RQ)
    job_ids = [job_info.get("job_id") for job_info in job_ids_in_session if job_info.get("job_id")]
    
    # If no job IDs in session, fallback to Supabase jobs table (PostgreSQL queue)
    if not job_ids:
        from datetime import datetime, timedelta
        access_token = session.get("supabase_access_token")
        supabase = get_supabase_client(access_token=access_token)
        if not supabase:
            return jsonify({
                "total": 0,
                "completed": 0,
                "failed": 0,
                "pending": 0,
                "in_progress": 0,
                "estimated_remaining_seconds": 0,
                "error": "Failed to initialize Supabase client"
            })

        # Best-effort query: recent jobs for this user (job_data.owner_user_id),
        # with a small time window to avoid scanning.
        since_iso = (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z"
        try:
            result = (
                supabase.table("jobs")
                .select("id")
                .eq("job_type", "process_submission")
                .gte("created_at", since_iso)
                .not_("job_data", "is", None)
                .not_("id", "is", None)
                .execute()
            )
            job_ids = [row.get("id") for row in (result.data or []) if row.get("id")]
        except Exception:
            job_ids = []

        if not job_ids:
            return jsonify({
                "total": 0,
                "completed": 0,
                "failed": 0,
                "pending": 0,
                "in_progress": 0,
                "estimated_remaining_seconds": 0
            })
    
    # Get aggregated status using Redis/RQ queue
    access_token = session.get("supabase_access_token")
    status = get_queue_status(job_ids, access_token=access_token)
    
    return jsonify(status)


@app.route("/api/worker_status")
def worker_status():
    """Diagnostic endpoint to check worker status and recent jobs."""
    if not require_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        from supabase import create_client
        supabase_url = os.environ.get("SUPABASE_URL")
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if not service_role_key:
            return jsonify({
                "worker_configured": False,
                "error": "SUPABASE_SERVICE_ROLE_KEY not set in environment"
            }), 500
        
        if not supabase_url:
            return jsonify({
                "worker_configured": False,
                "error": "SUPABASE_URL not set in environment"
            }), 500
        
        supabase = create_client(supabase_url, service_role_key)
        
        # Get recent jobs (last 10)
        result = supabase.table("jobs").select(
            "id, status, created_at, started_at, finished_at, error_message, job_data"
        ).order("created_at", desc=True).limit(10).execute()
        
        jobs = result.data if result.data else []
        
        # Count by status
        status_counts = {}
        for job in jobs:
            status = job.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Check if any jobs are stuck (queued for more than 2 minutes)
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        stuck_threshold = timedelta(minutes=2)
        
        stuck_jobs = []
        for job in jobs:
            if job.get("status") == "queued":
                created_at_str = job.get("created_at")
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        if now - created_at > stuck_threshold:
                            stuck_jobs.append({
                                "id": job.get("id"),
                                "created_at": created_at_str,
                                "filename": job.get("job_data", {}).get("filename", "unknown")
                            })
                    except:
                        pass
        
        # Get oldest stuck job
        oldest_stuck = stuck_jobs[0] if stuck_jobs else None
        
        # Get user's recent jobs
        user_id = session.get("user_id")
        user_jobs = []
        if user_id:
            user_jobs = [j for j in jobs if j.get("job_data", {}).get("owner_user_id") == user_id]
        
        return jsonify({
            "worker_configured": True,
            "service_role_key_set": bool(service_role_key),
            "total_recent_jobs": len(jobs),
            "user_jobs_count": len(user_jobs),
            "status_counts": status_counts,
            "stuck_jobs_count": len(stuck_jobs),
            "oldest_stuck_job": oldest_stuck,
            "user_recent_jobs": [
                {
                    "id": j.get("id"),
                    "status": j.get("status"),
                    "filename": j.get("job_data", {}).get("filename", "unknown"),
                    "created_at": j.get("created_at"),
                    "started_at": j.get("started_at"),
                    "finished_at": j.get("finished_at"),
                    "error": j.get("error_message")
                }
                for j in user_jobs[:5]
            ]
        })
    except Exception as e:
        import traceback
        return jsonify({
            "worker_configured": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


if __name__ == "__main__":
    # Render sets PORT environment variable, fallback to FLASK_PORT or 5000
    port = int(os.environ.get("PORT", os.environ.get("FLASK_PORT", 5000)))
    app.run(host="0.0.0.0", port=port, debug=False)  # debug=False for production
