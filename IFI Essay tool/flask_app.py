"""
Flask application for IFI Essay Gateway.
Replaces Streamlit with better redirect handling for Supabase magic links.
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.utils import secure_filename
import os
from pathlib import Path
import json
import io
import csv
import re
from typing import Optional, List, Dict, Any

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
from jobs.pg_queue import enqueue_submission, get_job_status, get_queue_status
from supabase import create_client

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))

# Configuration
UPLOAD_FOLDER = "artifacts"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size

# Ensure required directories exist (for outputs/CSV)
Path("outputs").mkdir(exist_ok=True)

# Initialize Supabase database
init_database()


def format_review_reasons(reason_codes: str) -> str:
    """Convert review reason codes into human-readable format."""
    if not reason_codes:
        return "Pending review"
    
    reason_map = {
        "MISSING_STUDENT_NAME": "Missing Student Name",
        "MISSING_SCHOOL_NAME": "Missing School Name",
        "MISSING_GRADE": "Missing Grade",
        "EMPTY_ESSAY": "Empty Essay",
        "SHORT_ESSAY": "Short Essay (< 50 words)",
        "LOW_CONFIDENCE": "Low OCR Confidence",
        "PENDING_REVIEW": "Pending Manual Review"
    }
    
    codes = reason_codes.split(";")
    readable_reasons = []
    for code in codes:
        code = code.strip()
        if code:
            readable_reasons.append(reason_map.get(code, code.replace("_", " ").title()))
    
    return " • ".join(readable_reasons) if readable_reasons else "Pending review"


def get_pdf_path(artifact_dir: str, access_token: Optional[str] = None) -> Optional[str]:
    """Get the Supabase Storage path to the original PDF file."""
    if not artifact_dir:
        return None
    
    # artifact_dir is like "user_id/submission_id"
    # Try common extensions - return the first one that likely exists
    # We'll let serve_pdf handle the actual file existence check
    for ext in [".pdf", ".png", ".jpg", ".jpeg"]:
        file_path = f"{artifact_dir}/original{ext}"
        # Try to get URL with access token for RLS
        url = get_file_url(file_path, access_token=access_token)
        if url:
            return file_path
    
    # If no URL found, still return the PDF path as fallback (most common)
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
    access_token = session.get("supabase_access_token")
    db_stats = get_db_stats(owner_user_id=user_id, access_token=access_token)
    
    return render_template("dashboard.html",
                         user_email=session.get("user_email"),
                         db_stats=db_stats)


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
            # Get redirect URL - Flask handles the callback
            # Use full URL including port if specified
            port = request.environ.get('SERVER_PORT', '')
            host = request.host
            if port and port not in ['80', '443']:
                redirect_url = f"{request.scheme}://{host}/auth/callback"
            else:
                redirect_url = f"{request.scheme}://{host}/auth/callback"
            
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
    
    # Enqueue all files for background processing
    for file in files:
        if file and allowed_file(file.filename):
            try:
                file_bytes = file.read()
                job_id = enqueue_submission(
                    file_bytes=file_bytes,
                    filename=file.filename,
                    owner_user_id=user_id,
                    access_token=access_token,
                    ocr_provider=ocr_provider
                )
                job_ids.append({
                    "filename": file.filename,
                    "job_id": job_id
                })
            except Exception as e:
                errors.append(f"{file.filename}: {str(e)}")
                print(f"❌ Error enqueueing {file.filename}: {e}")
                import traceback
                traceback.print_exc()
    
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


@app.route("/review")
def review():
    """Review and approval workflow page with School→Grade grouping."""
    if not require_auth():
        return redirect(url_for("login"))
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    review_mode = request.args.get("mode", "needs_review")
    
    # Get current batch ID from session (if available), or find most recent batch with submissions needing review
    upload_batch_id = session.get("upload_batch_id")
    batch_info = None
    
    # If no batch in session, try to find the most recent batch with submissions needing review
    if not upload_batch_id and review_mode == "needs_review":
        # Get all records needing review
        needs_review_records = get_db_records(needs_review=True, owner_user_id=user_id, access_token=access_token)
        # Find batches that have submissions needing review
        batch_ids = set()
        for record in needs_review_records:
            if record.get("upload_batch_id"):
                batch_ids.add(record["upload_batch_id"])
        
        # Get the most recent batch
        if batch_ids:
            try:
                supabase = get_supabase_client(access_token=access_token)
                if supabase and access_token:
                    try:
                        supabase.auth.set_session(access_token=access_token, refresh_token="")
                    except:
                        pass
                
                # Get the most recent batch from the list
                batches_result = supabase.table("upload_batches").select("*").eq("owner_user_id", user_id).in_("id", list(batch_ids)).order("created_at", desc=True).limit(1).execute()
                
                if batches_result.data and len(batches_result.data) > 0:
                    upload_batch_id = str(batches_result.data[0]["id"])
                    batch_info = get_batch_with_submissions(upload_batch_id, owner_user_id=user_id, access_token=access_token)
            except Exception as e:
                print(f"⚠️ Warning: Could not fetch batch: {e}")
                import traceback
                traceback.print_exc()
    
    # If we have a batch_id from session, get its info
    if upload_batch_id and not batch_info:
        batch_info = get_batch_with_submissions(upload_batch_id, owner_user_id=user_id, access_token=access_token)
    
    # Get all records (both needs_review and approved)
    all_records = get_db_records(needs_review=None, owner_user_id=user_id, access_token=access_token)
    
    # Group records
    grouped = group_records(all_records)
    
    if review_mode == "needs_review":
        records = grouped["needs_review"]
        # Add pdf_url (direct Supabase Storage URL) to each record
        for record in records:
            pdf_path = get_pdf_path(record.get("artifact_dir", ""), access_token=access_token)
            record["pdf_url"] = get_file_url(pdf_path, access_token=access_token) if pdf_path else None
        action_label = "Approve"
        schools_data = None
    else:
        # For approved records, show grouped by school and grade
        records = []  # Not used when showing grouped view
        # Sort schools_data for consistent display
        schools_data = dict(sorted(grouped["schools"].items()))
        # Sort grades within each school and add pdf_url to each record
        for school_name in schools_data:
            schools_data[school_name] = dict(sorted(schools_data[school_name].items(), 
                                                   key=lambda x: (str(x[0]).isdigit(), str(x[0]).lower())))
            # Add pdf_url (direct Supabase Storage URL) to each record in each grade
            for grade in schools_data[school_name]:
                for record in schools_data[school_name][grade]:
                    pdf_path = get_pdf_path(record.get("artifact_dir", ""), access_token=access_token)
                    record["pdf_url"] = get_file_url(pdf_path, access_token=access_token) if pdf_path else None
        action_label = "Send for Review"
    
    db_stats = get_db_stats(owner_user_id=user_id, access_token=access_token)
    
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


@app.route("/record/<submission_id>", methods=["GET", "POST"])
def record_detail(submission_id):
    """View and edit a specific record."""
    if not require_auth():
        return redirect(url_for("login"))
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    record = get_record_by_id(submission_id, owner_user_id=user_id, access_token=access_token)
    
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
        if update_db_record(submission_id, updates, owner_user_id=user_id, access_token=access_token):
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
    pdf_url = get_file_url(pdf_path, access_token=access_token) if pdf_path else None
    
    return render_template("record_detail.html",
                         record=record,
                         pdf_path=pdf_path,
                         pdf_url=pdf_url,
                         format_review_reasons=format_review_reasons)


@app.route("/record/<submission_id>/approve", methods=["POST"])
def approve_record(submission_id):
    """Approve a record (move to clean)."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    record = get_record_by_id(submission_id, owner_user_id=user_id, access_token=access_token)
    
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
    
    if update_db_record(submission_id, {"needs_review": False}, owner_user_id=user_id, access_token=access_token):
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
    
    if update_db_record(submission_id, {"needs_review": True}, owner_user_id=user_id, access_token=access_token):
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
            if update_db_record(submission_id, updates, owner_user_id=user_id, access_token=access_token):
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
    
    return jsonify({
        "success": True,
        "updated_count": updated_count,
        "message": f"Successfully updated {updated_count} records."
    })


@app.route("/record/<submission_id>/delete", methods=["POST"])
def delete_record(submission_id):
    """Delete a record."""
    if not require_auth():
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    
    user_id = session.get("user_id")
    access_token = session.get("supabase_access_token")
    
    if delete_db_record(submission_id, owner_user_id=user_id, access_token=access_token):
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Failed to delete record"}), 500


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
    
    # Get access token from session for authenticated storage access
    access_token = session.get("supabase_access_token")
    
    # file_path is like "user_id/submission_id/original.pdf"
    # Try to download from Supabase Storage
    file_bytes = download_file(file_path, access_token=access_token)
    
    # If file not found, try alternative extensions
    if not file_bytes and file_path.endswith((".pdf", ".png", ".jpg", ".jpeg")):
        # Extract base path without extension
        base_path = file_path.rsplit(".", 1)[0]
        # Try other common extensions
        for ext in [".pdf", ".png", ".jpg", ".jpeg"]:
            if not file_path.endswith(ext):
                alt_path = f"{base_path}{ext}"
                file_bytes = download_file(alt_path, access_token=access_token)
                if file_bytes:
                    file_path = alt_path
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


@app.route("/api/job_status/<job_id>")
def job_status(job_id):
    """Get the status of a processing job."""
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
    """Get status of all jobs in current batch."""
    if not require_auth():
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session.get("user_id")
    job_ids_in_session = session.get("processing_jobs", [])
    
    # Extract job IDs from session
    job_ids = [job_info.get("job_id") for job_info in job_ids_in_session if job_info.get("job_id")]
    
    # If no job IDs in session, try to get recent jobs for this user from database
    if not job_ids and user_id:
        try:
            from supabase import create_client
            supabase_url = os.environ.get("SUPABASE_URL")
            service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            if supabase_url and service_role_key:
                supabase = create_client(supabase_url, service_role_key)
                # Get recent jobs for this user (last 10, ordered by created_at desc)
                result = supabase.table("jobs").select("id, status, created_at, job_data").order("created_at", desc=True).limit(10).execute()
                if result.data:
                    # Filter jobs for this user and get IDs
                    user_jobs = [job for job in result.data if job.get("job_data", {}).get("owner_user_id") == user_id]
                    job_ids = [job["id"] for job in user_jobs[:5]]  # Get up to 5 most recent
                    # Update session with found job IDs
                    if job_ids:
                        session["processing_jobs"] = [{"job_id": jid} for jid in job_ids]
        except Exception as e:
            print(f"Error fetching jobs from database: {e}")
    
    if not job_ids:
        return jsonify({
            "total": 0,
            "completed": 0,
            "failed": 0,
            "pending": 0,
            "in_progress": 0,
            "estimated_remaining_seconds": 0
        })
    
    # Get aggregated status using PostgreSQL queue
    access_token = session.get("supabase_access_token")
    status = get_queue_status(job_ids, access_token=access_token)
    
    return jsonify(status)


if __name__ == "__main__":
    # Render sets PORT environment variable, fallback to FLASK_PORT or 5000
    port = int(os.environ.get("PORT", os.environ.get("FLASK_PORT", 5000)))
    app.run(host="0.0.0.0", port=port, debug=False)  # debug=False for production

