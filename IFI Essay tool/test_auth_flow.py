#!/usr/bin/env python3
"""
Test script to verify the authentication flow.
Run this to debug authentication issues.
"""

import os
import sys
import requests
from supabase import create_client

# Load environment variables from .env file if it exists
from dotenv import load_dotenv
load_dotenv()

# Environment variables must be set in .env file or exported
# Required: SUPABASE_URL, SUPABASE_ANON_KEY

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
FLASK_URL = "http://localhost:5001"
STREAMLIT_URL = "http://localhost:8501"

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    print("❌ Error: SUPABASE_URL and SUPABASE_ANON_KEY must be set")
    print("   Create a .env file or export these environment variables")
    print("   See .env.example for reference")
    sys.exit(1)

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
    if SUPABASE_URL:
        # Extract project ID from URL if possible
        project_id = SUPABASE_URL.split("//")[1].split(".")[0] if "supabase.co" in SUPABASE_URL else "your-project-id"
        print(f"   📧 Go to: https://supabase.com/dashboard/project/{project_id}/auth/url-configuration")
    else:
        print(f"   📧 Go to: Supabase Dashboard → Authentication → URL Configuration")

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

