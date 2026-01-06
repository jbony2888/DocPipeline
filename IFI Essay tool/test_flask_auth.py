#!/usr/bin/env python3
"""
Test script to verify Flask auth service is working.
"""

import requests
import sys

FLASK_URL = "http://localhost:5001"

def test_flask_running():
    """Test if Flask service is running."""
    try:
        response = requests.get(f"{FLASK_URL}/", timeout=2)
        if response.status_code == 200:
            print("✅ Flask service is running")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"❌ Flask returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Flask service is NOT running!")
        print("   Start it with: ./START_FLASK_AUTH.sh")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_session_endpoint():
    """Test Flask session endpoint."""
    try:
        response = requests.get(f"{FLASK_URL}/auth/session", timeout=2)
        if response.status_code in [200, 401]:
            print("✅ Session endpoint is accessible")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"❌ Session endpoint returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Testing Flask Auth Service...")
    print(f"   URL: {FLASK_URL}\n")
    
    flask_ok = test_flask_running()
    print()
    
    if flask_ok:
        test_session_endpoint()
        print()
        print("✅ Flask service is ready!")
        print("\n📝 Next steps:")
        print("   1. Make sure Supabase redirect URL is: http://localhost:5001/auth/callback")
        print("   2. Request a magic link from Streamlit")
        print("   3. Click the magic link in your email")
        print("   4. You should be redirected to Flask → then Streamlit → logged in!")
    else:
        print("\n❌ Flask service is not running!")
        print("   Start it in a separate terminal:")
        print("   ./START_FLASK_AUTH.sh")
        sys.exit(1)

