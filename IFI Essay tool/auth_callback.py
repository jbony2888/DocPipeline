"""
Flask callback service for handling Supabase magic link authentication.
This service handles the OAuth callback and redirects back to Streamlit with session.
"""

from flask import Flask, request, redirect, session
import os
from supabase import create_client, Client
from auth.supabase_client import normalize_supabase_url
import secrets
import hashlib
import time
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

# Configure session cookies for cross-origin requests
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Get Supabase credentials
SUPABASE_URL = normalize_supabase_url(os.environ.get("SUPABASE_URL"))
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
STREAMLIT_URL = os.environ.get("STREAMLIT_URL", "http://localhost:8501")

# In-memory token store (for passing tokens to Streamlit)
# In production, use Redis or database
_token_store = {}

def get_supabase_client() -> Client:
    """Initialize Supabase client."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


@app.route('/auth/callback')
def auth_callback():
    """
    Handle Supabase magic link callback.
    Extracts tokens from URL hash, sets session, and redirects to Streamlit.
    """
    # Supabase magic links use hash fragments (#access_token=...)
    # Flask can't read hash fragments server-side, so we use JavaScript
    access_token = request.args.get('access_token')
    refresh_token = request.args.get('refresh_token')
    expires_at = request.args.get('expires_at')
    
    # If no tokens in query params, extract from hash fragment using JavaScript
    if not access_token:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authenticating...</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            </style>
        </head>
        <body>
            <h2>🔐 Processing authentication...</h2>
            <div class="spinner"></div>
            <p>Please wait while we log you in...</p>
            <script>
                console.log('[Flask Callback] Extracting tokens from URL hash...');
                // Extract tokens from URL hash
                if (window.location.hash) {
                    const hash = window.location.hash.substring(1);
                    const params = new URLSearchParams(hash);
                    const accessToken = params.get('access_token');
                    const refreshToken = params.get('refresh_token');
                    const expiresAt = params.get('expires_at');
                    
                    console.log('[Flask Callback] Tokens found:', { hasAccessToken: !!accessToken, hasRefreshToken: !!refreshToken });
                    
                    if (accessToken) {
                        // Redirect to Flask callback with tokens as query params
                        const callbackUrl = '/auth/callback?access_token=' + encodeURIComponent(accessToken) +
                                          (refreshToken ? '&refresh_token=' + encodeURIComponent(refreshToken) : '') +
                                          (expiresAt ? '&expires_at=' + encodeURIComponent(expiresAt) : '');
                        console.log('[Flask Callback] Redirecting to:', callbackUrl.substring(0, 100) + '...');
                        window.location.replace(callbackUrl);
                    } else {
                        document.body.innerHTML = '<h2>❌ Error: No access token found</h2><p>The login link may be invalid or expired.</p>';
                    }
                } else {
                    document.body.innerHTML = '<h2>❌ Error: No authentication data found</h2><p>Please try requesting a new login link.</p>';
                }
            </script>
        </body>
        </html>
        """, 200
        
    # We have tokens in query params, process authentication
    try:
        supabase = get_supabase_client()
        
        # Set session in Supabase
        print(f"[Flask] Setting session with access_token: {access_token[:20]}...")
        session_response = supabase.auth.set_session({
            "access_token": access_token,
            "refresh_token": refresh_token or ""
        })
        
        # Get user info to verify
        user_response = supabase.auth.get_user()
        
        if user_response and user_response.user:
            print(f"[Flask] User authenticated: {user_response.user.email}")
            
            # Store user info in Flask session (for Flask endpoints)
            session['user_id'] = user_response.user.id
            session['user_email'] = user_response.user.email
            session['authenticated'] = True
            session['supabase_access_token'] = access_token
            if refresh_token:
                session['supabase_refresh_token'] = refresh_token
            
            # Create a short-lived token to pass tokens to Streamlit securely
            # Streamlit can't access Flask session cookies, so we use a token exchange
            import uuid
            exchange_token = str(uuid.uuid4())
            _token_store[exchange_token] = {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user_id': user_response.user.id,
                'user_email': user_response.user.email,
                'expires_at': time.time() + 60  # Token expires in 60 seconds
            }
            
            # Redirect to Streamlit with exchange token
            redirect_url = f"{STREAMLIT_URL}?auth_token={exchange_token}"
            print(f"[Flask] Redirecting to Streamlit with exchange token")
            return redirect(redirect_url)
        else:
            return "❌ Authentication failed: Could not retrieve user information. Please try again.", 400
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[Flask] Authentication error: {error_msg}")
        print(traceback.format_exc())
        return f"❌ Authentication error: {error_msg}<br><br>Please try requesting a new login link.", 500


@app.route('/auth/exchange')
def exchange_token():
    """Exchange a short-lived token for Supabase tokens."""
    from flask import jsonify
    exchange_token = request.args.get('token')
    
    if not exchange_token:
        return jsonify({'error': 'No token provided'}), 400
    
    # Check token store
    if exchange_token in _token_store:
        token_data = _token_store[exchange_token]
        
        # Check if token expired
        if time.time() > token_data['expires_at']:
            del _token_store[exchange_token]
            return jsonify({'error': 'Token expired'}), 401
        
        # Return tokens and delete token (one-time use)
        tokens = {
            'access_token': token_data['access_token'],
            'refresh_token': token_data['refresh_token'],
            'user_id': token_data['user_id'],
            'user_email': token_data['user_email']
        }
        del _token_store[exchange_token]
        return jsonify(tokens)
    
    return jsonify({'error': 'Invalid token'}), 401


@app.route('/auth/session')
def get_session():
    """API endpoint for Streamlit to check authentication status."""
    from flask import jsonify
    if session.get('authenticated'):
        return jsonify({
            'authenticated': True,
            'user_id': session.get('user_id'),
            'user_email': session.get('user_email'),
            'access_token': session.get('supabase_access_token'),
            'refresh_token': session.get('supabase_refresh_token')
        })
    return jsonify({'authenticated': False}), 401


@app.route('/')
def index():
    """Health check endpoint."""
    return {'status': 'ok', 'service': 'Flask Auth Callback'}, 200


@app.route('/auth/logout')
def logout():
    """Logout endpoint."""
    session.clear()
    return redirect(f"{STREAMLIT_URL}")


if __name__ == '__main__':
    port = int(os.environ.get('FLASK_PORT', 5001))  # Use 5001 to avoid conflicts
    print(f"🚀 Flask auth callback service starting on http://0.0.0.0:{port}")
    print(f"📧 Magic links should redirect to: http://localhost:{port}/auth/callback")
    app.run(host='0.0.0.0', port=port, debug=True)
