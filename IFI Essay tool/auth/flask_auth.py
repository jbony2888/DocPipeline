"""
Flask-based authentication helper for Streamlit.
Checks Flask session service for authentication status.
"""

import requests
import os
from typing import Optional, Tuple

FLASK_AUTH_URL = os.environ.get("FLASK_AUTH_URL", "http://localhost:5001")


def check_flask_session() -> Tuple[bool, Optional[str]]:
    """
    Check authentication status from Flask callback service.
    
    Returns:
        Tuple of (is_authenticated: bool, user_id: Optional[str])
    """
    try:
        response = requests.get(f"{FLASK_AUTH_URL}/auth/session", timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data.get('authenticated'):
                return True, data.get('user_id')
    except Exception:
        # Flask service not available or error
        pass
    return False, None


def get_flask_session_tokens() -> Optional[dict]:
    """Get Supabase tokens from Flask session."""
    try:
        response = requests.get(f"{FLASK_AUTH_URL}/auth/session", timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data.get('authenticated'):
                return {
                    'access_token': data.get('access_token'),
                    'refresh_token': data.get('refresh_token')
                }
    except Exception:
        pass
    return None

