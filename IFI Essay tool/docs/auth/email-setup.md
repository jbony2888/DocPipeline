# Email Notification Setup

## Overview

The application now sends email notifications when jobs complete or fail. This uses standard SMTP.

## Configuration

### Environment Variables

Add these to your `.env` file or Render environment variables:

```bash
# Required for email notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password  # See below for Gmail setup
SMTP_USE_TLS=true
FROM_EMAIL=your-email@gmail.com

# Required for job links in emails
APP_URL=https://your-app.onrender.com
```

### Gmail Setup (Recommended)

1. **Enable 2-Factor Authentication:**
   - Go to Google Account → Security
   - Enable 2-Step Verification

2. **Generate App Password:**
   - Google Account → Security → 2-Step Verification
   - Scroll to "App passwords"
   - Generate password for "Mail"
   - Use this as `SMTP_PASS` (NOT your regular password)

3. **Set Environment Variables:**
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASS=your-16-char-app-password
   SMTP_USE_TLS=true
   FROM_EMAIL=your-email@gmail.com
   ```

### Other SMTP Providers

**SendGrid:**
```
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASS=your-sendgrid-api-key
```

**Mailgun:**
```
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=your-mailgun-username
SMTP_PASS=your-mailgun-password
```

**Amazon SES:**
```
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=your-ses-smtp-username
SMTP_PASS=your-ses-smtp-password
```

## How It Works

1. **User uploads files** → Jobs enqueued to Redis
2. **Worker processes job** → Runs OCR and extraction
3. **Job completes** → Email sent automatically:
   - Success: "Processing Complete" with job details
   - Failure: "Processing Failed" with error message
4. **Email includes:**
   - Job ID
   - Filename
   - Status (completed/failed)
   - Timestamp
   - Link to job details page (`/jobs/<job_id>`)
   - Error message (if failed)

## Testing

### Test Email Locally

```python
from utils.email_notification import send_job_completion_email

# Test success email
send_job_completion_email(
    user_email="test@example.com",
    job_id="test-123",
    job_status="completed",
    filename="test.pdf",
    job_url="http://localhost:5000/jobs/test-123"
)

# Test failure email
send_job_completion_email(
    user_email="test@example.com",
    job_id="test-456",
    job_status="failed",
    filename="test.pdf",
    error_message="Test error message"
)
```

### Test in Production

1. Upload a test file
2. Wait for processing (check worker logs)
3. Check email inbox
4. Click job link in email to view details

## Email Format

### Success Email

**Subject:** Processing Complete: filename.pdf

**Content:**
- Green header: "Processing Complete"
- Job details (ID, filename, timestamp)
- Link to view job details
- Link to review page

### Failure Email

**Subject:** Processing Failed: filename.pdf

**Content:**
- Red header: "Processing Failed"
- Job details (ID, filename, timestamp)
- Error message
- Link to view job details

## Troubleshooting

### Emails Not Sending

1. **Check SMTP Configuration:**
   - All `SMTP_*` variables must be set
   - Check for typos in variable names

2. **Check Worker Logs:**
   ```
   docker-compose logs worker
   ```
   - Look for "✅ Email notification sent" or errors

3. **Test SMTP Connection:**
   - Try sending test email (see above)
   - Check for connection errors

### Gmail Issues

1. **"Invalid credentials":**
   - Must use App Password, not regular password
   - Enable 2FA first

2. **"Less secure app" error:**
   - Gmail requires App Passwords now
   - Generate App Password instead

3. **Connection timeout:**
   - Check firewall/VPN settings
   - Try port 465 with SSL instead of 587

### Email Content Issues

1. **Links not working:**
   - Check `APP_URL` is set correctly
   - Should be full URL (e.g., `https://app.onrender.com`)

2. **Missing job ID:**
   - Job ID is extracted from RQ context
   - If missing, email will still send but without job link

## Disabling Email (Optional)

If you don't want email notifications:

1. **Don't set SMTP variables** - System will skip email
2. **Or set `SMTP_HOST=""`** - Email function will return False

Emails are optional - jobs will still process correctly without them.



