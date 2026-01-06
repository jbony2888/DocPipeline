#!/usr/bin/env python3
"""
Test script to verify the authentication flow.
Run this to debug authentication issues.
"""

import os
import sys
import requests
from supabase import create_client

# Set environment variables
os.environ.setdefault("SUPABASE_URL", "https://escbcdjlafzjxzqiephc.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVzY2JjZGpsYWZ6anh6cWllcGhjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc2NzgzNTcsImV4cCI6MjA4MzI1NDM1N30.kxxKhBcp1iZuwSrucZhBx31f59AlW3EO0pu279lIhJI")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
FLASK_URL = "http://localhost:5001"
STREAMLIT_URL = "http://localhost:8501"

def test_flask_health():
    """Test if Flask service is running."""
    print("\n1️⃣ Testing Flask health...")
    try:
        response = requests.get(f"{FLASK_URL}/", timeout=2)
        print(f"   ✅ Flask is running: {response.status_code}")
        print(f"   Response: {response.json()}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Flask is NOT running on {FLASK_URL}")
        print(f"   💡 Start it with: ./START_FLASK_AUTH.sh")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_flask_session():
    """Test Flask session endpoint."""
    print("\n2️⃣ Testing Flask session endpoint...")
    try:
        response = requests.get(f"{FLASK_URL}/auth/session", timeout=2)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_supabase_client():
    """Test Supabase client initialization."""
    print("\n3️⃣ Testing Supabase client...")
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        print(f"   ✅ Supabase client initialized")
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def test_magic_link_config():
    """Check if magic link redirect URL is configured correctly."""
    print("\n4️⃣ Magic Link Configuration Check...")
    print(f"   Flask callback URL: {FLASK_URL}/auth/callback")
    print(f"   Streamlit URL: {STREAMLIT_URL}")
    print(f"   ⚠️  Make sure Supabase redirect URL is set to: {FLASK_URL}/auth/callback")
    print(f"   📧 Go to: https://supabase.com/dashboard/project/escbcdjlafzjxzqiephc/auth/url-configuration")

def main():
    print("=" * 60)
    print("🔐 Authentication Flow Test")
    print("=" * 60)
    
    flask_ok = test_flask_health()
    if flask_ok:
        test_flask_session()
    
    test_supabase_client()
    test_magic_link_config()
    
    print("\n" + "=" * 60)
    print("📋 Next Steps:")
    print("=" * 60)
    print("1. Make sure Flask is running: ./START_FLASK_AUTH.sh")
    print("2. Update Supabase redirect URL to: http://localhost:5001/auth/callback")
    print("3. Request a magic link from Streamlit")
    print("4. Click the link in your email")
    print("5. You should be redirected to Flask → Streamlit → Logged in")
    print("=" * 60)

if __name__ == "__main__":
    main()

