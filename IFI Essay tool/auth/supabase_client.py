"""
Supabase client initialization and authentication helpers.
"""

import os
from supabase import create_client, Client
from typing import Optional


def get_supabase_client(access_token: Optional[str] = None) -> Optional[Client]:
    """
    Initialize and return Supabase client from environment variables.
    If access_token is provided, uses it directly as the auth token for RLS.
    
    Requires:
        - SUPABASE_URL: Your Supabase project URL
        - SUPABASE_ANON_KEY: Your Supabase anonymous key (fallback if no access_token)
    
    Args:
        access_token: Optional access token (JWT) for authenticated requests.
                     When provided, this is used directly as the auth token.
    
    Returns:
        Supabase client instance, or None if credentials are missing
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    
    if not supabase_url:
        return None
    
    try:
        # If access_token is provided, use it directly as the auth key
        # The access_token is a JWT that contains user info for RLS
        if access_token:
            supabase: Client = create_client(supabase_url, access_token)
        else:
            # Fallback to anon key for unauthenticated requests
            supabase_key = os.environ.get("SUPABASE_ANON_KEY")
            if not supabase_key:
                return None
            supabase: Client = create_client(supabase_url, supabase_key)
        
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

