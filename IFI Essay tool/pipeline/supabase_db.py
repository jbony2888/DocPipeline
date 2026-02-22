"""
Supabase PostgreSQL database for storing submission records.
Replaces SQLite for production use.
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from pipeline.schema import SubmissionRecord
from auth.supabase_client import get_supabase_client, normalize_supabase_url


def _get_service_role_client():
    """Return a Supabase client using the service role key (bypasses RLS). Used for server-side ops scoped by owner_user_id."""
    from supabase import create_client as create_supabase_client
    supabase_url = normalize_supabase_url(os.environ.get("SUPABASE_URL"))
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        return None
    return create_supabase_client(supabase_url, service_key)


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


def check_duplicate_submission(submission_id: str, current_user_id: str, access_token: Optional[str] = None, refresh_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Check if a submission with this submission_id already exists.
    
    Returns:
        dict with:
            - is_duplicate: bool
            - existing_owner_user_id: str or None
            - is_own_duplicate: bool (True if same user uploaded it before)
            - existing_filename: str or None
    """
    try:
        supabase = get_supabase_client()
        
        if not supabase:
            return {"is_duplicate": False, "existing_owner_user_id": None, "is_own_duplicate": False, "existing_filename": None}
        
        # Set authenticated session for RLS
        if access_token:
            try:
                refresh = refresh_token if refresh_token else ""
                supabase.auth.set_session(access_token=access_token, refresh_token=refresh)
            except Exception as e:
                print(f"⚠️ Warning: Could not set session for check_duplicate: {e}")
        
        # Duplicate key compatibility:
        # - current pipeline duplicate key: base file hash (submission_id)
        # - legacy/single-chunk stored key: sha256(f"{base}:{0}")[:12]
        # Check both so duplicate detection works for existing records.
        import hashlib
        legacy_single_chunk_id = hashlib.sha256(f"{submission_id}:0".encode()).hexdigest()[:12]
        candidate_ids = [submission_id]
        if legacy_single_chunk_id != submission_id:
            candidate_ids.append(legacy_single_chunk_id)

        # Prefer service-role lookup so we can detect duplicates across all users.
        # If service-role is unavailable, fall back to user-scoped lookup so a user
        # still gets duplicate warnings for their own prior uploads.
        from supabase import create_client as create_supabase_client
        import os
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        supabase_url = normalize_supabase_url(os.environ.get("SUPABASE_URL"))
        
        if service_key and supabase_url:
            admin_client = create_supabase_client(supabase_url, service_key)
            result = (
                admin_client
                .table("submissions")
                .select("submission_id, owner_user_id, filename")
                .in_("submission_id", candidate_ids)
                .limit(1)
                .execute()
            )
            
            if result.data and len(result.data) > 0:
                existing_record = result.data[0]
                existing_owner = existing_record.get("owner_user_id")
                existing_filename = existing_record.get("filename")
                is_own_duplicate = (existing_owner == current_user_id)
                
                return {
                    "is_duplicate": True,
                    "existing_owner_user_id": existing_owner,
                    "is_own_duplicate": is_own_duplicate,
                    "existing_filename": existing_filename
                }
        else:
            # Fallback with authenticated client (RLS): detects current user's duplicates.
            # This keeps duplicate warning behavior working even without service role key.
            user_result = (
                supabase
                .table("submissions")
                .select("submission_id, owner_user_id, filename")
                .in_("submission_id", candidate_ids)
                .limit(1)
                .execute()
            )
            if user_result.data and len(user_result.data) > 0:
                existing_record = user_result.data[0]
                existing_owner = existing_record.get("owner_user_id") or current_user_id
                existing_filename = existing_record.get("filename")
                return {
                    "is_duplicate": True,
                    "existing_owner_user_id": existing_owner,
                    "is_own_duplicate": True,
                    "existing_filename": existing_filename
                }
        
        return {"is_duplicate": False, "existing_owner_user_id": None, "is_own_duplicate": False, "existing_filename": None}
    except Exception as e:
        print(f"⚠️ Warning: Error checking duplicate: {e}")
        return {"is_duplicate": False, "existing_owner_user_id": None, "is_own_duplicate": False, "existing_filename": None}


def save_record(record: SubmissionRecord, filename: str, owner_user_id: str, access_token: Optional[str] = None, upload_batch_id: Optional[str] = None) -> Dict[str, Any]:
    """Save a submission record to Supabase."""
    try:
        # Prefer an authenticated client when possible (RLS relies on auth.uid()).
        supabase = get_supabase_client(access_token=access_token) if access_token else get_supabase_client()
        if not supabase:
            raise Exception("Could not initialize Supabase client")
        
        # Convert Pydantic model to dict (includes review_reason_codes from validation - do not overwrite)
        record_dict = record.model_dump() if hasattr(record, 'model_dump') else record.dict()
        
        # Add metadata
        record_dict["filename"] = filename
        record_dict["owner_user_id"] = owner_user_id
        record_dict["updated_at"] = datetime.now().isoformat()
        
        # Add batch tracking
        if upload_batch_id:
            record_dict["upload_batch_id"] = upload_batch_id

        # NOT NULL columns (migration 005): provide defaults so upsert never fails
        # Records with missing name/school/grade are saved and flagged (needs_review), not rejected
        if "school_source" not in record_dict:
            record_dict["school_source"] = "extracted"
        if "grade_source" not in record_dict:
            record_dict["grade_source"] = "extracted"
        if "teacher_source" not in record_dict:
            record_dict["teacher_source"] = "extracted"
        
        # Check if this is an update (duplicate) or new record
        # We'll check this before upsert to return info about duplicates
        from supabase import create_client as create_supabase_client
        import os
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        supabase_url = normalize_supabase_url(os.environ.get("SUPABASE_URL"))
        
        is_update = False
        previous_owner = None
        if service_key and supabase_url:
            admin_client = create_supabase_client(supabase_url, service_key)
            existing = admin_client.table("submissions").select("owner_user_id").eq("submission_id", record.submission_id).limit(1).execute()
            if existing.data and len(existing.data) > 0:
                is_update = True
                previous_owner = existing.data[0].get("owner_user_id")
        
        # Insert or update (upsert). If schema lacks source columns (005 not run), retry without them.
        try:
            result = supabase.table("submissions").upsert(
                record_dict,
                on_conflict="submission_id"
            ).execute()
        except Exception as upsert_err:
            err_str = str(upsert_err).lower()
            # Schema lacks source columns (migration not applied): retry without them.
            # PostgREST returns PGRST204 "Could not find the 'grade_source' column... in the schema cache"
            missing_column = (
                ("column" in err_str and ("does not exist" in err_str or "undefined_column" in err_str))
                or ("grade_source" in err_str and "schema" in err_str)
                or "pgrst204" in err_str
            )
            if ("school_source" in record_dict or "grade_source" in record_dict or "teacher_source" in record_dict) and missing_column:
                for k in ("school_source", "grade_source", "teacher_source"):
                    record_dict.pop(k, None)
                result = supabase.table("submissions").upsert(
                    record_dict,
                    on_conflict="submission_id"
                ).execute()
            else:
                raise

        if is_update:
            print(f"🔄 Updated existing record {record.submission_id} in Supabase database")
        else:
            print(f"✅ Saved new record {record.submission_id} to Supabase database")
        
        return {
            "success": True,
            "is_update": is_update,
            "previous_owner_user_id": previous_owner if is_update else None
        }
    except Exception as e:
        err_msg = str(e)
        print(f"❌ Error saving record to Supabase: {err_msg}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": err_msg, "is_update": False, "previous_owner_user_id": None}


def get_records(
    needs_review: Optional[bool] = None,
    owner_user_id: Optional[str] = None,
    limit: Optional[int] = None,
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
    select_fields: Optional[List[str]] = None
) -> List[Dict]:
    """Get submission records from Supabase."""
    try:
        # Prefer an authenticated client when possible (RLS relies on auth.uid()).
        supabase = get_supabase_client(access_token=access_token) if access_token else get_supabase_client()
        
        if not supabase:
            print("❌ Error: Could not initialize Supabase client")
            return []
        
        select_expr = "*"
        if select_fields:
            select_expr = ", ".join(select_fields)
        query = supabase.table("submissions").select(select_expr)
        
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
        
        try:
            result = query.execute()
            return result.data if result.data else []
        except Exception as query_error:
            print(f"❌ Error executing query in get_records: {query_error}")
            # If query fails due to RLS/auth, return empty list instead of crashing
            import traceback
            traceback.print_exc()
            return []
    except Exception as e:
        print(f"❌ Error getting records from Supabase: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_record_by_id(submission_id: str, owner_user_id: Optional[str] = None, access_token: Optional[str] = None, refresh_token: Optional[str] = None) -> Optional[Dict]:
    """Get a single record by submission_id. Uses service role when owner_user_id is set so fetch works even if user JWT is expired."""
    try:
        if owner_user_id:
            supabase = _get_service_role_client()
        else:
            supabase = get_supabase_client(access_token=access_token) if access_token else get_supabase_client()

        if not supabase:
            print("❌ Error: Could not initialize Supabase client")
            return None

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


def update_record(submission_id: str, updates: Dict, owner_user_id: Optional[str] = None, access_token: Optional[str] = None, refresh_token: Optional[str] = None) -> bool:
    """Update a submission record."""
    try:
        # Prefer an authenticated client when possible (RLS relies on auth.uid()).
        supabase = get_supabase_client(access_token=access_token) if access_token else get_supabase_client()
        
        if not supabase:
            print("❌ Error: Could not initialize Supabase client")
            return False
        
        # Add updated_at timestamp
        updates["updated_at"] = datetime.now().isoformat()
        
        query = supabase.table("submissions").update(updates).eq("submission_id", submission_id)
        
        if owner_user_id:
            query = query.eq("owner_user_id", owner_user_id)
        
        result = query.execute()
        
        if result.data:
            print(f"✅ Updated record {submission_id} in Supabase")
            return True
        else:
            print(f"⚠️ Warning: Update query returned no data for {submission_id}")
            return False
    except Exception as e:
        print(f"❌ Error updating record in Supabase: {e}")
        import traceback
        traceback.print_exc()
        return False


def delete_record(submission_id: str, owner_user_id: Optional[str] = None, access_token: Optional[str] = None, refresh_token: Optional[str] = None) -> bool:
    """Delete a submission record. Uses service role when owner_user_id is set so delete works even if user JWT is expired."""
    try:
        if owner_user_id:
            supabase = _get_service_role_client()
        else:
            supabase = get_supabase_client(access_token=access_token) if access_token else get_supabase_client()

        if not supabase:
            print("❌ Error: Could not initialize Supabase client")
            return False

        query = supabase.table("submissions").delete().eq("submission_id", submission_id)

        if owner_user_id:
            query = query.eq("owner_user_id", owner_user_id)

        result = query.execute()
        return True
    except Exception as e:
        print(f"❌ Error deleting record from Supabase: {e}")
        return False


def get_stats(owner_user_id: Optional[str] = None, access_token: Optional[str] = None, refresh_token: Optional[str] = None) -> Dict:
    """Get statistics about submissions. Uses service role when owner_user_id is set so stats work even if user JWT is expired."""
    try:
        # When we have owner_user_id, use service role so stats don't depend on user JWT (avoids 401 when token expired).
        if owner_user_id:
            supabase = _get_service_role_client()
        else:
            supabase = get_supabase_client(access_token=access_token) if access_token else get_supabase_client()

        if not supabase:
            print("❌ Error: Could not initialize Supabase client")
            return {"total_count": 0, "clean_count": 0, "needs_review_count": 0}

        def _count_for(needs_review_value: Optional[bool] = None) -> int:
            query = supabase.table("submissions").select("submission_id", count="exact", head=True)
            if owner_user_id:
                query = query.eq("owner_user_id", owner_user_id)
            if needs_review_value is not None:
                query = query.eq("needs_review", needs_review_value)
            result = query.execute()
            if hasattr(result, "count") and result.count is not None:
                return int(result.count)
            return len(result.data) if result.data else 0

        total_count = _count_for(None)
        needs_review_count = _count_for(True)
        clean_count = _count_for(False)

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
