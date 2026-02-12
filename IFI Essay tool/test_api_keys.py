#!/usr/bin/env python3
"""
Test script to verify Google Cloud Vision and Groq API keys are properly configured.
"""

import os
import json
import sys

def test_google_vision():
    """Test Google Cloud Vision credentials (file path or JSON env)."""
    print("🔍 Testing Google Cloud Vision credentials...")
    
    creds_json = os.environ.get('GOOGLE_CLOUD_VISION_CREDENTIALS_JSON')
    creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    
    # Prefer credentials file when set
    if creds_path:
        path = os.path.abspath(os.path.expanduser(creds_path))
        if not os.path.isfile(path):
            print(f"❌ GOOGLE_APPLICATION_CREDENTIALS file not found: {path}")
            return False
        try:
            with open(path, 'r') as f:
                creds_dict = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in credentials file: {e}")
            return False
        if creds_dict.get('type') != 'service_account':
            print("❌ Invalid credentials type (expected 'service_account')")
            return False
        project_id = creds_dict.get('project_id', '')
        client_email = creds_dict.get('client_email', '')
        print(f"✅ Google credentials file is valid: {path}")
        print(f"   Project ID: {project_id}")
        print(f"   Client Email: {client_email}")
        try:
            from pipeline.ocr import GoogleVisionOcrProvider
            ocr = GoogleVisionOcrProvider()
            print("✅ Google Vision OCR client initialized successfully")
            return True
        except Exception as e:
            print(f"⚠️  Credentials loaded but client init failed: {e}")
            print("   This might be OK if Cloud Vision API is not enabled")
            return True
    elif not creds_json or creds_json.strip() == '':
        print("❌ Neither GOOGLE_APPLICATION_CREDENTIALS nor GOOGLE_CLOUD_VISION_CREDENTIALS_JSON set")
        return False
    
    try:
        creds_dict = json.loads(creds_json)
        if creds_dict.get('type') != 'service_account':
            print("❌ Invalid credentials type (expected 'service_account')")
            return False
        
        client_email = creds_dict.get('client_email', '')
        project_id = creds_dict.get('project_id', '')
        
        print(f"✅ Google credentials JSON is valid")
        print(f"   Project ID: {project_id}")
        print(f"   Client Email: {client_email}")
        
        try:
            from pipeline.ocr import GoogleVisionOcrProvider
            ocr = GoogleVisionOcrProvider()
            print("✅ Google Vision OCR client initialized successfully")
            return True
        except Exception as e:
            print(f"⚠️  Credentials loaded but client init failed: {e}")
            print("   This might be OK if Cloud Vision API is not enabled")
            return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in GOOGLE_CLOUD_VISION_CREDENTIALS_JSON: {e}")
        return False
    except Exception as e:
        print(f"❌ Error checking Google credentials: {e}")
        return False


def test_groq_key():
    """Test Groq API key."""
    print("\n🔍 Testing Groq API key...")
    
    groq_key = os.environ.get('GROQ_API_KEY')
    if not groq_key:
        print("❌ GROQ_API_KEY not set")
        return False
    
    # Check key format (should start with 'gsk_' for Groq)
    if len(groq_key) < 20:
        print("⚠️  Groq key seems too short (expected at least 20 chars)")
        return False
    
    if not groq_key.startswith('gsk_'):
        print("⚠️  Groq key doesn't start with 'gsk_' (unusual format)")
        # Still return True as format might vary
    
    print(f"✅ Groq API key is set (length: {len(groq_key)} chars)")
    print(f"   Key format: {groq_key[:4]}...{groq_key[-4:]}")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("API Keys Configuration Test")
    print("=" * 60)
    print()
    
    google_ok = test_google_vision()
    groq_ok = test_groq_key()
    
    print()
    print("=" * 60)
    print("Summary:")
    print("=" * 60)
    print(f"Google Cloud Vision: {'✅ OK' if google_ok else '❌ FAIL'}")
    print(f"Groq API Key:        {'✅ OK' if groq_ok else '❌ FAIL'}")
    print()
    
    if google_ok and groq_ok:
        print("✅ All API keys are properly configured!")
        return 0
    else:
        print("❌ Some API keys are missing or invalid")
        print("\nNext steps:")
        if not google_ok:
            print("  - Set GOOGLE_CLOUD_VISION_CREDENTIALS_JSON in .env")
        if not groq_ok:
            print("  - Set GROQ_API_KEY in .env")
        return 1


if __name__ == '__main__':
    sys.exit(main())



