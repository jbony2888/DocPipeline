#!/usr/bin/env python3
"""
Helper script to prepare environment variables for Render deployment.

This script helps format your Google Cloud credentials JSON correctly
for pasting into Render's environment variable dashboard.
"""

import json
import sys
import os
from pathlib import Path

def format_google_credentials_for_render(credentials_file: str) -> str:
    """
    Convert Google Cloud credentials JSON file to single-line string
    suitable for Render's GOOGLE_CLOUD_VISION_CREDENTIALS_JSON environment variable.
    """
    try:
        # Read the JSON file
        with open(credentials_file, 'r') as f:
            credentials = json.load(f)
        
        # Convert to compact JSON (single line, no spaces)
        single_line = json.dumps(credentials, separators=(',', ':'))
        
        return single_line
    
    except FileNotFoundError:
        print(f"❌ Error: File not found: {credentials_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def print_render_instructions():
    """Print instructions for setting up Render environment variables."""
    print("\n" + "="*70)
    print("RENDER ENVIRONMENT VARIABLES SETUP")
    print("="*70)
    print("\n📋 Step-by-step instructions:\n")
    print("1. Go to: https://dashboard.render.com")
    print("2. Select your service: 'ifi-essay-gateway'")
    print("3. Click: 'Environment' tab")
    print("4. Click: 'Add Environment Variable' for each variable below\n")
    print("-" * 70)
    print("\n✅ REQUIRED VARIABLES:\n")
    print("Variable 1:")
    print("  Key:   GOOGLE_CLOUD_VISION_CREDENTIALS_JSON")
    print("  Value: [See formatted JSON below - copy the entire string]")
    print("\nVariable 2:")
    print("  Key:   GROQ_API_KEY")
    print("  Value: gsk_your_groq_key_here")
    print("\n" + "-" * 70)


def main():
    if len(sys.argv) < 2:
        print("Usage: python prepare_render_env.py <google-credentials.json>")
        print("\nExample:")
        print("  python prepare_render_env.py ~/Downloads/your-credentials.json")
        sys.exit(1)
    
    credentials_file = sys.argv[1]
    
    print("\n🔧 Preparing Google Cloud Vision credentials for Render...\n")
    
    # Format credentials
    formatted_json = format_google_credentials_for_render(credentials_file)
    
    # Print instructions
    print_render_instructions()
    
    # Print formatted JSON (for copy/paste)
    print("\n📋 COPY THIS VALUE FOR 'GOOGLE_CLOUD_VISION_CREDENTIALS_JSON':\n")
    print("-" * 70)
    print(formatted_json)
    print("-" * 70)
    
    # Also save to file for easy access
    output_file = Path("render_google_creds.txt")
    with open(output_file, 'w') as f:
        f.write(formatted_json)
    
    print(f"\n✅ Formatted JSON saved to: {output_file}")
    print("   (This file is gitignored - safe to keep locally)")
    print("\n⚠️  SECURITY: Never commit this file to Git!")
    print("   It's already in .gitignore for safety.\n")
    
    # Verify JSON is valid
    try:
        json.loads(formatted_json)
        print("✅ JSON format validated successfully!")
    except:
        print("❌ Warning: JSON validation failed")


if __name__ == "__main__":
    main()

