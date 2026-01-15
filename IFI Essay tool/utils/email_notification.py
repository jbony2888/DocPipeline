"""
Email notification system for job completion.
Supports Supabase SMTP and standard SMTP.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from datetime import datetime


def send_job_completion_email(
    user_email: str,
    job_id: str,
    job_status: str,
    filename: str,
    job_url: Optional[str] = None,
    error_message: Optional[str] = None
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
                    
                    {f'<p><a href="{job_url}" class="button">View Job Details</a></p>' if job_url else ''}
                    
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
        
        {f'View job details: {job_url}' if job_url else ''}
        
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
    text_body: str
) -> bool:
    """
    Send email using standard SMTP.
    
    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        # Get SMTP configuration
        smtp_host = os.environ.get("SMTP_HOST")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER")
        smtp_password = os.environ.get("SMTP_PASS")
        from_email = os.environ.get("FROM_EMAIL", smtp_user)
        
        # Check if SMTP is configured
        if not all([smtp_host, smtp_user, smtp_password]):
            print("⚠️ SMTP not configured. Skipping email notification.")
            print("   Set SMTP_HOST, SMTP_USER, SMTP_PASS, and optionally SMTP_PORT, FROM_EMAIL")
            return False
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        
        # Attach both plain text and HTML versions
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
        
        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        else:
            # Use SSL/TLS on connection (port 465)
            if smtp_port == 465:
                import ssl
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, context=context)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port)
        
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Email notification sent to {to_email}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending SMTP email: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_job_url(job_id: str) -> str:
    """
    Generate URL to view job details.
    
    Args:
        job_id: Job ID
        
    Returns:
        Full URL to job details page
    """
    base_url = os.environ.get("APP_URL", "http://localhost:5000")
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

