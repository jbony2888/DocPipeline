"""
Email notification system for job completion.
Supports Supabase SMTP and standard SMTP.
"""

import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from datetime import datetime

DEFAULT_APP_URL = "https://docpipeline.onrender.com"


def get_review_url(upload_batch_id: Optional[str] = None) -> str:
    """
    Generate URL to the review page (needs_review). Optionally include batch for direct link.
    """
    base_url = os.environ.get("APP_URL", DEFAULT_APP_URL)
    url = f"{base_url}/review?mode=needs_review"
    if upload_batch_id:
        url += f"&upload_batch_id={upload_batch_id}"
    return url


def send_job_completion_email(
    user_email: str,
    job_id: str,
    job_status: str,
    filename: str,
    job_url: Optional[str] = None,
    error_message: Optional[str] = None,
    review_url: Optional[str] = None,
) -> bool:
    """
    Send email notification when a job completes or fails.
    
    Args:
        user_email: User's email address
        job_id: Job ID
        job_status: "completed" or "failed"
        filename: Name of the processed file
        job_url: URL to view job details (optional)
        error_message: Error message if job failed (optional)
        review_url: URL to review page (optional; preferred CTA when provided)
        
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        # Determine if job succeeded
        is_success = job_status.lower() in ["completed", "finished", "success"]
        
        # Prepare email content
        subject = f"Processing {'Complete' if is_success else 'Failed'}: {filename}"
        
        # Build email body
        status_text = "completed successfully" if is_success else "failed"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {'#4CAF50' if is_success else '#f44336'}; color: white; padding: 20px; text-align: center; }}
                .content {{ background-color: #f9f9f9; padding: 20px; }}
                .info {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid {'#4CAF50' if is_success else '#f44336'}; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
                .button {{ display: inline-block; padding: 12px 24px; background-color: {'#4CAF50' if is_success else '#f44336'}; color: white; text-decoration: none; border-radius: 4px; margin: 10px 0; }}
                .error {{ color: #f44336; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Processing {'Complete' if is_success else 'Failed'}</h2>
                </div>
                <div class="content">
                    <p>Hello,</p>
                    <p>Your file processing job has {status_text}.</p>
                    
                    <div class="info">
                        <strong>File:</strong> {filename}<br>
                        <strong>Job ID:</strong> {job_id}<br>
                        <strong>Status:</strong> <span class="{'success' if is_success else 'error'}">{job_status.title()}</span><br>
                        <strong>Timestamp:</strong> {timestamp}
                    </div>
                    
                    {f'<div class="error"><strong>Error:</strong> {error_message}</div>' if error_message else ''}
                    
                    {f'<p><a href="{review_url or job_url}" class="button">View in Review Page</a></p>' if (review_url or job_url) else ''}
                    
                    <p>If you have any questions, please contact support.</p>
                </div>
                <div class="footer">
                    <p>IFI Essay Gateway<br>
                    This is an automated notification. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_body = f"""
        Processing {'Complete' if is_success else 'Failed'}
        
        Hello,
        
        Your file processing job has {status_text}.
        
        File: {filename}
        Job ID: {job_id}
        Status: {job_status.title()}
        Timestamp: {timestamp}
        
        {f'Error: {error_message}' if error_message else ''}
        
        {f'View in Review Page: {review_url or job_url}' if (review_url or job_url) else ''}
        
        If you have any questions, please contact support.
        
        --
        IFI Essay Gateway
        This is an automated notification. Please do not reply to this email.
        """
        
        # Try Supabase SMTP first, then fallback to standard SMTP
        if try_supabase_smtp(user_email, subject, html_body, text_body):
            return True
        
        # Fallback to standard SMTP
        return send_smtp_email(user_email, subject, html_body, text_body)
        
    except Exception as e:
        print(f"❌ Error sending email notification: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_batch_completion_email(
    user_email: str,
    total_count: int,
    review_url: str,
    failed_count: int = 0,
) -> bool:
    """
    Send one email after all submissions in a batch have been processed.
    """
    try:
        completed = total_count - failed_count
        is_multi = total_count > 1
        if is_multi:
            subject = "Your essays have been processed"
            header_text = "All files processed"
            intro = "Your essays have been processed. All files processed."
        else:
            subject = "Your essay has been processed"
            header_text = "Essay processed"
            intro = "Your file has been processed."
        status_line = f"{completed} of {total_count} essay(s) processed successfully."
        if failed_count:
            status_line += f" {failed_count} had errors (see Review page)."
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                .content {{ background-color: #f9f9f9; padding: 20px; }}
                .button {{ display: inline-block; padding: 12px 24px; background-color: #4CAF50; color: #ffffff !important; text-decoration: none; border-radius: 4px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header"><h2>{header_text}</h2></div>
                <div class="content">
                    <p>Hello,</p>
                    <p>{intro}</p>
                    <p>{status_line}</p>
                    <p><a href="{review_url}" class="button" style="color: #ffffff !important;">View in Review Page</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        text_body = f"{header_text}.\n\n{intro}\n{status_line}\n\nView in Review Page: {review_url}"
        if try_supabase_smtp(user_email, subject, html_body, text_body):
            return True
        return send_smtp_email(user_email, subject, html_body, text_body)
    except Exception as e:
        print(f"❌ Error sending batch completion email: {e}")
        return False


def try_supabase_smtp(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str
) -> bool:
    """
    Try to send email using Supabase SMTP configuration.
    Note: Supabase doesn't provide direct SMTP access in most cases.
    This is a placeholder for future Supabase email integration.
    
    Returns:
        True if sent via Supabase, False otherwise
    """
    # Check if Supabase email is configured
    supabase_email_enabled = os.environ.get("SUPABASE_EMAIL_ENABLED", "false").lower() == "true"
    
    if not supabase_email_enabled:
        return False
    
    # TODO: Implement Supabase email sending if/when available
    # Supabase typically doesn't expose SMTP directly
    # Would need to use Supabase Edge Functions or their email service
    
    return False


def send_smtp_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    attachments: Optional[list[dict[str, Any]]] = None,
) -> bool:
    """
    Send email using Gmail SMTP only. Requires EMAIL (Gmail or G Suite / Google Workspace address) and GMAIL_PASSWORD (app password).
    
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        gmail_password = (os.environ.get("GMAIL_PASSWORD") or "").strip().replace(" ", "")
        smtp_user = (os.environ.get("EMAIL") or "").strip()
        smtp_timeout = float((os.environ.get("SMTP_TIMEOUT_SECONDS") or "15").strip())
        if not gmail_password or not smtp_user:
            print("⚠️ Email not configured. Set EMAIL (Gmail or G Suite address) and GMAIL_PASSWORD (16-char app password).")
            return False
        smtp_host = "smtp.gmail.com"
        smtp_port = 587
        print(f"📧 Using Gmail SMTP: smtp.gmail.com port {smtp_port} (STARTTLS), sender={smtp_user}, timeout={smtp_timeout}s")
        
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_email
        body_part = MIMEMultipart("alternative")
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        body_part.attach(part1)
        body_part.attach(part2)
        msg.attach(body_part)
        for attachment in attachments or []:
            filename = str(attachment.get("filename") or "attachment.bin")
            content = attachment.get("content") or b""
            mime_part = MIMEApplication(content)
            mime_part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(mime_part)
        
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout)
        try:
            server.starttls()
            server.login(smtp_user, gmail_password)
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass
        
        print(f"✅ Email notification sent to {to_email}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending SMTP email: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_assignment_batch_email(
    *,
    to_email: str,
    school: str,
    grade: str,
    batch_number: int,
    total_batches: int,
    essay_count: int,
    portal_url: str,
) -> bool:
    """
    Send one assignment email with a portal link for batch access.
    """
    subject = f"IFI Essay Batch Assignment: {school} Grade {grade} Batch {batch_number}"
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #1d4ed8; color: white; padding: 20px; text-align: center; }}
            .content {{ background-color: #f8fafc; padding: 20px; }}
            .info {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid #1d4ed8; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header"><h2>Essay Batch Assignment</h2></div>
            <div class="content">
                <p>Hello,</p>
                <p>You have been assigned an IFI essay reading batch.</p>
                <div class="info">
                    <strong>School:</strong> {school}<br>
                    <strong>Grade:</strong> {grade}<br>
                    <strong>Batch:</strong> {batch_number} of {total_batches}<br>
                    <strong>Essays in this batch:</strong> {essay_count}
                </div>
                <p><a href="{portal_url}">Open your reader access page</a></p>
                <p>After opening the link, enter your email address to view your assigned essays, open each essay, and save rankings.</p>
                <div class="info">
                    <strong>Ranking instructions:</strong><br>
                    1 = best essay in your batch.<br>
                    {essay_count} = lowest-ranked essay in your batch.<br>
                    Save each essay's rank with its own Save button.<br>
                    Use Unrank if you want to remove a saved rank before finalizing your list.<br>
                    Only one essay can hold each rank number in your batch.
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    text_body = (
        "Essay Batch Assignment\n\n"
        f"School: {school}\n"
        f"Grade: {grade}\n"
        f"Batch: {batch_number} of {total_batches}\n"
        f"Essays in this batch: {essay_count}\n\n"
        f"Open your reader access page: {portal_url}\n\n"
        "After opening the link, enter your email address to view your assigned essays, open each essay, and save rankings.\n\n"
        "Ranking instructions:\n"
        f"- 1 = best essay in your batch\n"
        f"- {essay_count} = lowest-ranked essay in your batch\n"
        "- Save each essay with its own Save button\n"
        "- Use Unrank to move an essay back to unranked\n"
        "- Only one essay can use each rank number in the batch"
    )
    return send_smtp_email(to_email, subject, html_body, text_body)


def get_job_url(job_id: str) -> str:
    """
    Generate URL to view job details.
    
    Args:
        job_id: Job ID
        
    Returns:
        Full URL to job details page
    """
    base_url = os.environ.get("APP_URL", DEFAULT_APP_URL)
    return f"{base_url}/jobs/{job_id}"


def get_user_email_from_token(access_token: str) -> Optional[str]:
    """
    Extract user email from Supabase access token.
    
    Args:
        access_token: Supabase JWT access token
        
    Returns:
        User email if available, None otherwise
    """
    try:
        import jwt
        import json
        
        # Decode JWT without verification (Supabase tokens are already verified)
        # We just need to extract the email
        decoded = jwt.decode(access_token, options={"verify_signature": False})
        
        # Supabase JWT contains user email in different places depending on auth method
        email = decoded.get("email") or decoded.get("user_email")
        
        # If not directly in token, might be in user metadata
        if not email and "user_metadata" in decoded:
            email = decoded["user_metadata"].get("email")
        
        return email
        
    except Exception as e:
        print(f"⚠️ Could not extract email from token: {e}")
        return None
