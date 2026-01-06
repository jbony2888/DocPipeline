"""
Supabase PostgreSQL database for storing submission records.
Replaces SQLite for production use.
"""

import os
from typing import Optional, List, Dict
from datetime import datetime
from pipeline.schema import SubmissionRecord
from auth.supabase_client import get_supabase_client


def init_database():
    """Verify Supabase connection and table exists."""
    # Table should already be created via SQL script
    # Just verify connection
    try:
        supabase = get_supabase_client()
        # Test query to verify connection
        result = supabase.table("submissions").select("submission_id").limit(1).execute()
        return True
    except Exception as e:
        print(f"⚠️ Warning: Could not connect to Supabase: {e}")
        return False


def save_record(record: SubmissionRecord, filename: str, owner_user_id: str, access_token: Optional[str] = None) -> bool:
    """Save a submission record to Supabase."""
    try:
        # Get Supabase client and set authenticated session if token provided
        supabase = get_supabase_client()
        
        # Set authenticated session if access token provided (required for RLS)
        if access_token:
            try:
                supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=""  # Refresh token not needed for database operations
                )
            except Exception as e:
                print(f"⚠️ Warning: Could not set session: {e}")
        
        # Convert Pydantic model to dict
        record_dict = record.model_dump() if hasattr(record, 'model_dump') else record.dict()
        
        # Add metadata
        record_dict["filename"] = filename
        record_dict["owner_user_id"] = owner_user_id
        record_dict["updated_at"] = datetime.now().isoformat()
        
        # Insert or update (upsert)
        result = supabase.table("submissions").upsert(
            record_dict,
            on_conflict="submission_id"
        ).execute()
        
        print(f"✅ Saved record {record.submission_id} to Supabase database")
        return True
    except Exception as e:
        print(f"❌ Error saving record to Supabase: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_records(
    needs_review: Optional[bool] = None,
    owner_user_id: Optional[str] = None,
    limit: Optional[int] = None,
    access_token: Optional[str] = None
) -> List[Dict]:
    """Get submission records from Supabase."""
    try:
        supabase = get_supabase_client()
        
        # Set authenticated session if access token provided (required for RLS)
        if access_token:
            try:
                supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=""
                )
            except Exception as e:
                print(f"⚠️ Warning: Could not set session: {e}")
        
        query = supabase.table("submissions").select("*")
        
        # Filter by owner
        if owner_user_id:
            query = query.eq("owner_user_id", owner_user_id)
        
        # Filter by needs_review
        if needs_review is not None:
            query = query.eq("needs_review", needs_review)
        
        # Order by created_at descending
        query = query.order("created_at", desc=True)
        
        # Apply limit
        if limit:
            query = query.limit(limit)
        
        result = query.execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"❌ Error getting records from Supabase: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_record_by_id(submission_id: str, owner_user_id: Optional[str] = None, access_token: Optional[str] = None) -> Optional[Dict]:
    """Get a single record by submission_id."""
    try:
        supabase = get_supabase_client()
        
        # Set authenticated session if access token provided (required for RLS)
        if access_token:
            try:
                supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=""
                )
            except Exception as e:
                print(f"⚠️ Warning: Could not set session: {e}")
        
        query = supabase.table("submissions").select("*").eq("submission_id", submission_id)
        
        if owner_user_id:
            query = query.eq("owner_user_id", owner_user_id)
        
        result = query.execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    except Exception as e:
        print(f"❌ Error getting record from Supabase: {e}")
        return None


def update_record(submission_id: str, updates: Dict, owner_user_id: Optional[str] = None, access_token: Optional[str] = None) -> bool:
    """Update a submission record."""
    try:
        supabase = get_supabase_client()
        
        # Set authenticated session if access token provided (required for RLS)
        if access_token:
            try:
                supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=""
                )
            except Exception as e:
                print(f"⚠️ Warning: Could not set session: {e}")
        
        # Add updated_at timestamp
        updates["updated_at"] = datetime.now().isoformat()
        
        query = supabase.table("submissions").update(updates).eq("submission_id", submission_id)
        
        if owner_user_id:
            query = query.eq("owner_user_id", owner_user_id)
        
        result = query.execute()
        return True
    except Exception as e:
        print(f"❌ Error updating record in Supabase: {e}")
        import traceback
        traceback.print_exc()
        return False


def delete_record(submission_id: str, owner_user_id: Optional[str] = None, access_token: Optional[str] = None) -> bool:
    """Delete a submission record."""
    try:
        supabase = get_supabase_client()
        
        # Set authenticated session if access token provided (required for RLS)
        if access_token:
            try:
                supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=""
                )
            except Exception as e:
                print(f"⚠️ Warning: Could not set session: {e}")
        
        query = supabase.table("submissions").delete().eq("submission_id", submission_id)
        
        if owner_user_id:
            query = query.eq("owner_user_id", owner_user_id)
        
        result = query.execute()
        return True
    except Exception as e:
        print(f"❌ Error deleting record from Supabase: {e}")
        return False


def get_stats(owner_user_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict:
    """Get statistics about submissions."""
    try:
        supabase = get_supabase_client()
        
        # Get all records for the user
        all_records = get_records(owner_user_id=owner_user_id, access_token=access_token)
        
        total_count = len(all_records)
        clean_count = sum(1 for r in all_records if not r.get("needs_review", False))
        needs_review_count = sum(1 for r in all_records if r.get("needs_review", False))
        
        return {
            "total_count": total_count,
            "clean_count": clean_count,
            "needs_review_count": needs_review_count
        }
    except Exception as e:
        print(f"❌ Error getting stats from Supabase: {e}")
        return {
            "total_count": 0,
            "clean_count": 0,
            "needs_review_count": 0
        }

