"""
Service functions for batch defaults functionality.
Handles applying default values to submissions in a batch while protecting manual edits.
"""

from typing import Optional, Dict, List
from auth.supabase_client import get_supabase_client


def apply_batch_defaults(
    upload_batch_id: str,
    default_school_name: Optional[str],
    default_grade: Optional[str],
    default_teacher_name: Optional[str],
    owner_user_id: str,
    access_token: Optional[str] = None
) -> Dict[str, any]:
    """
    Apply batch defaults to all submissions in a batch.
    
    Rules:
    - Only updates fields that are NULL/empty AND source != 'manual'
    - Sets source to 'batch_default' for fields that are updated
    - Never overwrites fields with source='manual'
    - Updates the upload_batches table with the defaults (for future reference)
    
    Args:
        upload_batch_id: UUID of the upload batch
        default_school_name: Default school name (can be None)
        default_grade: Default grade (can be None)
        default_teacher_name: Default teacher name (can be None)
        owner_user_id: User ID (for RLS)
        access_token: Supabase access token (for RLS)
        
    Returns:
        dict with:
            - success: bool
            - updated_count: int (number of submissions updated)
            - error: str (if failed)
    """
    try:
        supabase = get_supabase_client(access_token=access_token)
        if not supabase:
            return {"success": False, "error": "Failed to initialize Supabase client"}
        
        # Set authenticated session if access token provided
        if access_token:
            try:
                supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=""
                )
            except Exception as e:
                print(f"⚠️ Warning: Could not set session: {e}")
        
        # Step 1: Update upload_batches table with defaults (for reference)
        batch_updates = {}
        if default_school_name is not None:
            batch_updates["default_school_name"] = default_school_name
        if default_grade is not None:
            batch_updates["default_grade"] = default_grade
        if default_teacher_name is not None:
            batch_updates["default_teacher_name"] = default_teacher_name
        
        if batch_updates:
            try:
                supabase.table("upload_batches").update(batch_updates).eq("id", upload_batch_id).eq("owner_user_id", owner_user_id).execute()
            except Exception as e:
                print(f"⚠️ Warning: Could not update batch defaults: {e}")
        
        # Step 2: Apply defaults to submissions
        # Query all submissions in the batch first, then filter and update in Python
        # This approach is safer and handles NULL/empty checks correctly
        all_submissions = supabase.table("submissions").select(
            "submission_id, school_name, grade, teacher_name, school_source, grade_source, teacher_source"
        ).eq("upload_batch_id", upload_batch_id).eq("owner_user_id", owner_user_id).execute()
        
        if not all_submissions.data:
            return {"success": True, "updated_count": 0, "total_submissions": 0, "message": "No submissions found in batch"}
        
        # Filter submissions that need updates
        submissions_to_update = []
        for sub in all_submissions.data:
            updates = {}
            
            # Check school_name
            if default_school_name and default_school_name.strip():
                current_school = sub.get("school_name")
                if (not current_school or current_school.strip() == "") and sub.get("school_source") != "manual":
                    updates["school_name"] = default_school_name.strip()
                    updates["school_source"] = "batch_default"
            
            # Check grade
            if default_grade and str(default_grade).strip():
                current_grade = sub.get("grade")
                if (current_grade is None or str(current_grade).strip() == "") and sub.get("grade_source") != "manual":
                    updates["grade"] = default_grade.strip()
                    updates["grade_source"] = "batch_default"
            
            # Check teacher_name
            if default_teacher_name and default_teacher_name.strip():
                current_teacher = sub.get("teacher_name")
                if (not current_teacher or current_teacher.strip() == "") and sub.get("teacher_source") != "manual":
                    updates["teacher_name"] = default_teacher_name.strip()
                    updates["teacher_source"] = "batch_default"
            
            if updates:
                submissions_to_update.append((sub["submission_id"], updates))
        
        # Update each submission
        for submission_id, updates in submissions_to_update:
            supabase.table("submissions").update(updates).eq("submission_id", submission_id).eq("owner_user_id", owner_user_id).execute()
        
        updated_count = len(submissions_to_update)
        
        return {
            "success": True,
            "updated_count": updated_count,
            "total_submissions": len(all_submissions.data)
        }
        
    except Exception as e:
        print(f"❌ Error applying batch defaults: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def get_batch_with_submissions(
    upload_batch_id: str,
    owner_user_id: str,
    access_token: Optional[str] = None
) -> Optional[Dict]:
    """
    Get an upload batch with its submissions.
    
    Returns:
        dict with batch info and submissions list, or None if not found
    """
    try:
        supabase = get_supabase_client(access_token=access_token)
        if not supabase:
            return None
        
        # Set authenticated session if access token provided
        if access_token:
            try:
                supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=""
                )
            except Exception as e:
                print(f"⚠️ Warning: Could not set session: {e}")
        
        # Get batch
        batch_result = supabase.table("upload_batches").select("*").eq("id", upload_batch_id).eq("owner_user_id", owner_user_id).execute()
        
        if not batch_result.data or len(batch_result.data) == 0:
            return None
        
        batch = batch_result.data[0]
        
        # Get submissions for this batch
        submissions_result = supabase.table("submissions").select("*").eq("upload_batch_id", upload_batch_id).eq("owner_user_id", owner_user_id).order("created_at", desc=True).execute()
        
        batch["submissions"] = submissions_result.data if submissions_result.data else []
        
        return batch
        
    except Exception as e:
        print(f"❌ Error getting batch: {e}")
        return None


def create_upload_batch(
    owner_user_id: str,
    access_token: Optional[str] = None
) -> Optional[str]:
    """
    Create a new upload batch.
    
    Returns:
        Batch ID (UUID as string) or None if failed
    """
    try:
        supabase = get_supabase_client(access_token=access_token)
        if not supabase:
            return None
        
        # Set authenticated session if access token provided
        if access_token:
            try:
                supabase.auth.set_session(
                    access_token=access_token,
                    refresh_token=""
                )
            except Exception as e:
                print(f"⚠️ Warning: Could not set session: {e}")
        
        result = supabase.table("upload_batches").insert({
            "owner_user_id": owner_user_id
        }).execute()
        
        if result.data and len(result.data) > 0:
            return str(result.data[0]["id"])
        return None
        
    except Exception as e:
        print(f"❌ Error creating upload batch: {e}")
        return None

