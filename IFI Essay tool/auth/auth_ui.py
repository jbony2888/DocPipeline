"""
Streamlit authentication UI components.
"""

import streamlit as st
import os
from auth.supabase_client import get_supabase_client, get_user_id
from typing import Optional, Tuple


def show_login_page() -> bool:
    """
    Display login page with magic link (email link) authentication.
    
    Returns:
        True if user successfully logged in, False otherwise
    """
    # Inject JavaScript to handle Supabase magic link callback
    # Use st.markdown with unsafe_allow_html for immediate execution
    st.markdown("""
    <script>
    (function() {
        'use strict';
        // Check if URL has hash fragment (Supabase magic link callback)
        if (window.location.hash && window.location.hash.includes('access_token')) {
            console.log('[Login Page] Magic link hash detected');
            const hash = window.location.hash.substring(1);
            const params = new URLSearchParams(hash);
            const accessToken = params.get('access_token');
            const refreshToken = params.get('refresh_token');
            const expiresAt = params.get('expires_at');
            const type = params.get('type');
            
            if (accessToken) {
                console.log('[Login Page] Redirecting with query params');
                const baseUrl = window.location.origin + window.location.pathname;
                const newUrl = baseUrl + '?access_token=' + encodeURIComponent(accessToken) + 
                              (refreshToken ? '&refresh_token=' + encodeURIComponent(refreshToken) : '') +
                              (expiresAt ? '&expires_at=' + encodeURIComponent(expiresAt) : '') +
                              '&type=' + (type || 'magiclink');
                window.location.replace(newUrl);
            }
        }
    })();
    </script>
    """, unsafe_allow_html=True)
    
    st.title("🔐 IFI Essay Gateway - Login")
    st.markdown("**Sign in with a secure link sent to your email**")
    st.info("💡 **No password needed!** Enter your email address below. We'll send you a secure login link. If this is your first time, we'll create your account automatically.")
    
    supabase = get_supabase_client()
    if not supabase:
        st.error("⚠️ Authentication is not configured. Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables.")
        st.stop()
        return False
    
    # Magic link form
    with st.form("magic_link_form"):
        email = st.text_input(
            "📧 Email Address", 
            placeholder="your.email@example.com",
            help="Enter your email address to receive a secure login link"
        )
        
        magic_link_button = st.form_submit_button(
            "📧 Send Login Link", 
            type="primary", 
            use_container_width=True
        )
    
    if magic_link_button:
        if not email:
            st.error("Please enter your email address.")
            return False
        
        # Validate email format
        if "@" not in email or "." not in email.split("@")[1]:
            st.error("Please enter a valid email address.")
            return False
        
        # Get the redirect URL for magic link callback
        # Use Flask callback service instead of direct Streamlit redirect
        # Flask handles the hash fragment properly
        flask_callback_url = os.environ.get("FLASK_AUTH_URL", "http://localhost:5001")
        redirect_url = f"{flask_callback_url}/auth/callback"  # Flask will handle callback and redirect to Streamlit
        
        try:
            # sign_in_with_otp works for both sign-up and sign-in
            # If user doesn't exist, Supabase will auto-create them (if sign-ups are enabled)
            # If user exists, it will send a login link
            supabase.auth.sign_in_with_otp({
                "email": email,
                "options": {
                    "email_redirect_to": redirect_url,
                    "should_create_user": True  # Auto-create user if they don't exist
                }
            })
            
            st.success(f"✅ **Login link sent!**")
            st.info(f"📬 Check your email at **{email}** and click the secure login link. The link will expire in 1 hour.")
            st.markdown("---")
            st.markdown("💡 **First time?**")
            st.markdown("- Your account will be created automatically when you click the link")
            st.markdown("- No separate registration needed!")
            st.markdown("---")
            st.markdown("💡 **Didn't receive the email?**")
            st.markdown("- Check your spam/junk folder")
            st.markdown("- Make sure you entered the correct email address")
            st.markdown("- Wait a few minutes and try again")
            return False
        except Exception as e:
            error_msg = str(e)
            # Handle different error cases
            if "signups disabled" in error_msg.lower() or "sign up is disabled" in error_msg.lower():
                st.error("❌ **Registration is currently disabled.**")
                st.info("Please contact your administrator to create an account, or enable sign-ups in Supabase Dashboard.")
            elif "email rate limit" in error_msg.lower() or "too many requests" in error_msg.lower():
                st.error("❌ **Too many requests.**")
                st.info("Please wait a few minutes before requesting another login link.")
            else:
                st.error(f"❌ **Error sending login link:** {str(e)}")
                st.info("💡 If this persists, please contact your administrator.")
            return False
    
    return False


def check_auth() -> Tuple[bool, Optional[str]]:
    """
    Check if user is authenticated.
    Also handles magic link callback from email via Flask service.
    
    Returns:
        Tuple of (is_authenticated: bool, user_id: Optional[str])
    """
    supabase = get_supabase_client()
    if not supabase:
        return False, None
    
    # Check if we're coming from Flask callback (auth_token query param)
    query_params = st.query_params
    if "auth_token" in query_params:
        exchange_token = query_params.get("auth_token")
        if exchange_token:
            # Exchange token for Supabase tokens
            try:
                import requests
                flask_auth_url = os.environ.get("FLASK_AUTH_URL", "http://localhost:5001")
                response = requests.get(f"{flask_auth_url}/auth/exchange", params={'token': exchange_token}, timeout=3)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('access_token'):
                        # Set Supabase session using tokens from Flask
                        supabase.auth.set_session({
                            "access_token": data['access_token'],
                            "refresh_token": data.get('refresh_token', '')
                        })
                        
                        # Verify user
                        user_response = supabase.auth.get_user()
                        if user_response and user_response.user:
                            # Store in Streamlit session state
                            st.session_state.user = user_response.user
                            st.session_state.user_id = user_response.user.id
                            st.session_state.user_email = user_response.user.email
                            st.session_state.supabase = supabase
                            
                            # Clear query params
                            st.query_params.clear()
                            
                            # Show success and redirect
                            st.success("✅ **Login successful!**")
                            st.balloons()
                            st.rerun()
                            return True, user_response.user.id
                        else:
                            st.error("❌ Failed to verify user session.")
                    else:
                        st.error("❌ Invalid token response.")
                elif response.status_code == 401:
                    st.error("❌ Token expired or invalid. Please request a new login link.")
                    st.query_params.clear()
                else:
                    st.warning(f"⚠️ Flask service error: {response.status_code}")
            except requests.exceptions.ConnectionError:
                st.warning("⚠️ **Flask auth service not running!**")
                st.info("💡 Please start the Flask service in a separate terminal:\n```bash\n./START_FLASK_AUTH.sh\n```")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
                st.query_params.clear()
    
    # Check for direct token callback (fallback - if Flask isn't used)
    if "access_token" in query_params:
        try:
            # Get tokens from query params
            access_token = query_params.get("access_token")
            refresh_token = query_params.get("refresh_token", "")
            expires_at = query_params.get("expires_at")
            
            if access_token:
                # Show loading state
                st.info("🔐 **Processing login...**")
                
                try:
                    # Set session in Supabase client using the tokens
                    # The set_session method expects a dict with access_token and refresh_token
                    session_response = supabase.auth.set_session({
                        "access_token": access_token,
                        "refresh_token": refresh_token
                    })
                    
                    # Get user info to verify session was set correctly
                    user_response = supabase.auth.get_user()
                    
                    if user_response and user_response.user:
                        # Store session in Streamlit session state
                        st.session_state.user = user_response.user
                        st.session_state.user_id = user_response.user.id
                        st.session_state.user_email = user_response.user.email
                        st.session_state.supabase = supabase
                        
                        # Clear query params after successful auth
                        st.query_params.clear()
                        
                        # Show success message
                        st.success("✅ **Login successful!**")
                        st.balloons()
                        
                        # Force immediate rerun to show dashboard
                        st.rerun()
                        return True, user_response.user.id
                    else:
                        st.error("❌ Failed to authenticate. Could not retrieve user information.")
                        st.query_params.clear()
                        return False, None
                        
                except Exception as session_error:
                    import traceback
                    error_details = str(session_error)
                    st.error(f"❌ **Authentication error:** {error_details}")
                    st.code(traceback.format_exc())
                    st.info("💡 Please try requesting a new login link.")
                    st.query_params.clear()
                    return False, None
                        
        except Exception as e:
            # Token might be invalid or expired
            st.error(f"❌ Authentication error: {str(e)}")
            st.info("💡 The login link may have expired. Please request a new one.")
            import traceback
            st.code(traceback.format_exc())
            st.query_params.clear()
            return False, None
    
    # Check session state for existing authentication
    if "user_id" in st.session_state and st.session_state.user_id:
        supabase_session = st.session_state.get("supabase")
        if supabase_session:
            # Verify session is still valid
            try:
                user_id = get_user_id(supabase_session)
                if user_id:
                    return True, user_id
            except Exception:
                # Session expired, clear it
                if "user_id" in st.session_state:
                    del st.session_state.user_id
                if "user_email" in st.session_state:
                    del st.session_state.user_email
                if "supabase" in st.session_state:
                    del st.session_state.supabase
    
    return False, None


def require_auth():
    """
    Require authentication - redirects to login if not authenticated.
    Call this at the start of your app to gate access.
    """
    is_authenticated, user_id = check_auth()
    
    if not is_authenticated:
        show_login_page()
        st.stop()
    
    return user_id


def show_logout_button():
    """Display logout button in sidebar or header."""
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        # Clear session state
        if "user" in st.session_state:
            del st.session_state.user
        if "user_id" in st.session_state:
            del st.session_state.user_id
        if "user_email" in st.session_state:
            del st.session_state.user_email
        if "supabase" in st.session_state:
            del st.session_state.supabase
        
        # Clear all other session state
        for key in list(st.session_state.keys()):
            if key not in ["file_uploader_key"]:  # Keep some non-auth state
                del st.session_state[key]
        
        st.success("✅ Logged out successfully!")
        st.rerun()

