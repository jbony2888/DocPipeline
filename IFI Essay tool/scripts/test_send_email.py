#!/usr/bin/env python3
"""Send a test email to verify Gmail (EMAIL + GMAIL_PASSWORD) is configured correctly.

Usage:
  python scripts/test_send_email.py                    # send to EMAIL from .env
  python scripts/test_send_email.py your@example.com    # send to given address
"""
import os
import sys

# Load .env from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except ImportError:
    pass

from utils.email_notification import send_smtp_email

SUBJECT = "IFI Essay Gateway – test email"
HTML_BODY = """
<html><body>
<p>This is a test email from IFI Essay Gateway.</p>
<p>If you received this, Gmail (EMAIL + GMAIL_PASSWORD) is configured correctly.</p>
</body></html>
"""
TEXT_BODY = "This is a test email from IFI Essay Gateway. If you received this, Gmail is configured correctly."

if __name__ == "__main__":
    to_email = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or os.environ.get("EMAIL", "").strip()
    if not to_email:
        print("Usage: python scripts/test_send_email.py [to_email]")
        print("  Or set EMAIL in .env and run without arguments.")
        sys.exit(1)
    print(f"Sending test email to {to_email}...")
    ok = send_smtp_email(to_email, SUBJECT, HTML_BODY, TEXT_BODY)
    if ok:
        print(f"✅ Test email sent to {to_email}")
    else:
        print(f"❌ Failed. Check EMAIL and GMAIL_PASSWORD in .env (use a Gmail app password).")
        sys.exit(1)
