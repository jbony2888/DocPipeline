"""
Supabase client initialization and authentication helpers.
"""

import os
from supabase import create_client, Client
from yarl import URL
from typing import Optional


def normalize_supabase_url(url: Optional[str]) -> Optional[str]:
    """Ensure Supabase URL ends with a trailing slash to satisfy storage client."""
    if not url:
        return None
    normalized = url if url.endswith("/") else f"{url}/"
    os.environ["SUPABASE_URL"] = normalized
    return normalized


def get_supabase_client(access_token: Optional[str] = None) -> Optional[Client]:
    """
    Initialize and return Supabase client from environment variables.
    If access_token is provided, uses it as the Bearer token for authenticated
    PostgREST/Storage requests (RLS via auth.uid()) while keeping the anon key
    as the apiKey header.
    
    Requires:
        - SUPABASE_URL: Your Supabase project URL
        - SUPABASE_ANON_KEY: Your Supabase anonymous key (fallback if no access_token)
    
    Args:
        access_token: Optional access token (JWT) for authenticated requests.
                     When provided, this is used directly as the auth token.
    
    Returns:
        Supabase client instance, or None if credentials are missing
    """
    supabase_url = normalize_supabase_url(os.environ.get("SUPABASE_URL"))
    
    if not supabase_url:
        return None
    
    try:
        # Always create the client with the project's anon key.
        # When access_token is present, we set it as the Authorization Bearer token
        # (do NOT use it as the Supabase "key").
        supabase_key = os.environ.get("SUPABASE_ANON_KEY")
        if not supabase_key:
            return None
        supabase: Client = create_client(supabase_url, supabase_key)

        if access_token:
            bearer = f"Bearer {access_token}"
            try:
                supabase.options.headers["Authorization"] = bearer
            except Exception:
                pass
            try:
                supabase.postgrest.auth(access_token)
            except Exception:
                pass
            try:
                supabase.storage._client.headers["Authorization"] = bearer
            except Exception:
                pass

        # Ensure storage_url ends with a slash to avoid storage3 warnings.
        try:
            storage_url = str(supabase.storage_url)
            if not storage_url.endswith("/"):
                supabase.storage_url = URL(f"{storage_url}/")
        except Exception:
            pass

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
