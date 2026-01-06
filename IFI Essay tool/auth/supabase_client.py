"""
Supabase client initialization and authentication helpers.
"""

import os
from supabase import create_client, Client
from typing import Optional


def get_supabase_client(access_token: Optional[str] = None) -> Optional[Client]:
    """
    Initialize and return Supabase client from environment variables.
    If access_token is provided, initializes an authenticated client.
    
    Requires:
        - SUPABASE_URL: Your Supabase project URL
        - SUPABASE_ANON_KEY: Your Supabase anonymous key
    
    Args:
        access_token: Optional access token for authenticated requests
    
    Returns:
        Supabase client instance, or None if credentials are missing
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_key:
        return None
    
    try:
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # Set authenticated session if access token provided
        if access_token:
            try:
                supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=""  # Refresh token not needed for database operations
                )
            except Exception as e:
                print(f"Warning: Could not set session with access token: {e}")
                # Continue anyway - client still works, just not authenticated
        
        return supabase
    except Exception as e:
        print(f"Error initializing Supabase client: {e}")
        return None


def get_user_id(supabase_client: Client) -> Optional[str]:
    """
    Get the current user ID from Supabase session.
    
    Args:
        supabase_client: Initialized Supabase client
        
    Returns:
        User ID (UUID string) if authenticated, None otherwise
    """
    try:
        user = supabase_client.auth.get_user()
        if user and user.user:
            return user.user.id
        return None
    except Exception as e:
        # Not authenticated or session expired
        return None

