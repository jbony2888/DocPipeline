#!/usr/bin/env python3
"""
Test IONOS SMTP connection
Run: python test_smtp.py
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# IONOS SMTP Settings
SMTP_HOST = "smtp.ionos.com"
SMTP_USER = "essays@4dads.org"
SMTP_PASS = "rgXjWgJ9TrhiE4h"
TEST_TO_EMAIL = "jerrybony5@gmail.com"

def test_smtp_587_starttls():
    """Test port 587 with STARTTLS"""
    print("\n" + "="*60)
    print("Testing Port 587 with STARTTLS")
    print("="*60)
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = TEST_TO_EMAIL
        msg['Subject'] = "Test Email - Port 587 STARTTLS"
        msg.attach(MIMEText("This is a test email from IONOS SMTP using port 587 with STARTTLS.", 'plain'))
        
        # Connect to SMTP server
        print(f"Connecting to {SMTP_HOST}:587...")
        server = smtplib.SMTP(SMTP_HOST, 587, timeout=10)
        server.set_debuglevel(1)  # Show debug output
        
        print("Starting TLS...")
        server.starttls()
        
        print("Logging in...")
        server.login(SMTP_USER, SMTP_PASS)
        
        print("Sending email...")
        server.send_message(msg)
        
        print("Closing connection...")
        server.quit()
        
        print("\n✅ SUCCESS! Email sent via port 587 with STARTTLS")
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED! Error: {type(e).__name__}: {str(e)}")
        return False


def test_smtp_465_ssl():
    """Test port 465 with SSL/TLS"""
    print("\n" + "="*60)
    print("Testing Port 465 with SSL/TLS")
    print("="*60)
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = TEST_TO_EMAIL
        msg['Subject'] = "Test Email - Port 465 SSL/TLS"
        msg.attach(MIMEText("This is a test email from IONOS SMTP using port 465 with SSL/TLS.", 'plain'))
        
        # Connect to SMTP server with SSL
        print(f"Connecting to {SMTP_HOST}:465 with SSL...")
        context = ssl.create_default_context()
        server = smtplib.SMTP_SSL(SMTP_HOST, 465, timeout=10, context=context)
        server.set_debuglevel(1)  # Show debug output
        
        print("Logging in...")
        server.login(SMTP_USER, SMTP_PASS)
        
        print("Sending email...")
        server.send_message(msg)
        
        print("Closing connection...")
        server.quit()
        
        print("\n✅ SUCCESS! Email sent via port 465 with SSL/TLS")
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED! Error: {type(e).__name__}: {str(e)}")
        return False


if __name__ == "__main__":
    print("\n🔧 IONOS SMTP Connection Test")
    print(f"Host: {SMTP_HOST}")
    print(f"User: {SMTP_USER}")
    print(f"Testing email will be sent to: {TEST_TO_EMAIL}")
    
    # Test both configurations
    result_587 = test_smtp_587_starttls()
    result_465 = test_smtp_465_ssl()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Port 587 (STARTTLS): {'✅ WORKS' if result_587 else '❌ FAILED'}")
    print(f"Port 465 (SSL/TLS):  {'✅ WORKS' if result_465 else '❌ FAILED'}")
    print("="*60)
    
    if result_587 or result_465:
        print("\n✅ At least one configuration works!")
        if result_587:
            print("   → Use Port 587 with STARTTLS in Supabase")
        if result_465:
            print("   → Use Port 465 with SSL in Supabase")
    else:
        print("\n❌ Both configurations failed. Check:")
        print("   1. IONOS email credentials are correct")
        print("   2. SMTP access is enabled in IONOS")
        print("   3. Account is active and not blocked")
