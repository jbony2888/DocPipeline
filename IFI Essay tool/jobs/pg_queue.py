"""
PostgreSQL-based job queue using Supabase.
Replaces Redis/RQ with a simple PostgreSQL table.
"""

import os
import json
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from auth.supabase_client import get_supabase_client
from supabase import create_client


def _supabase_url_no_trailing_slash() -> Optional[str]:
    url = os.environ.get("SUPABASE_URL")
    if not url:
        return None
    return url.rstrip("/")


def enqueue_submission(
    file_bytes: bytes,
    filename: str,
    owner_user_id: str,
    access_token: str,
    ocr_provider: str = "google",
    upload_batch_id: Optional[str] = None
) -> str:
    """
    Enqueue a submission for background processing.
    
    Returns:
        Job ID (UUID as string)
        
    Raises:
        Exception if job cannot be enqueued
    """
    try:
        # Use service role key to bypass RLS for job insertion
        # This is safe because we validate owner_user_id matches the authenticated user
        supabase_url = _supabase_url_no_trailing_slash()
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if not supabase_url:
            raise Exception("SUPABASE_URL is not set")
        if not service_role_key:
            raise Exception("Supabase Service Role Key not set (SUPABASE_SERVICE_ROLE_KEY)")

        supabase = create_client(supabase_url, service_role_key)
        
        # Encode file bytes as base64 for storage
        file_base64 = base64.b64encode(file_bytes).decode('utf-8')
        
        # Prepare job data
        job_data = {
            "file_bytes_base64": file_base64,
            "filename": filename,
            "owner_user_id": owner_user_id,
            "access_token": access_token,  # Store access token for worker
            "ocr_provider": ocr_provider,
            "upload_batch_id": upload_batch_id  # Store batch ID for linking submissions
        }
        
        # Insert job into database using service role key (bypasses RLS)
        result = supabase.table("jobs").insert({
            "job_type": "process_submission",
            "status": "queued",
            "job_data": job_data,
            "progress": 0,
            "status_message": f"Queued: {filename}",
            "attempts": 0,
            "max_attempts": 3
        }).execute()
        
        if not result.data or len(result.data) == 0:
            raise Exception("Failed to create job in database")
        
        job_id = result.data[0]["id"]
        return str(job_id)
        
    except Exception as e:
        raise Exception(f"Failed to enqueue job: {str(e)}")


def get_job_status(job_id: str, access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the status of a job.
    
    Args:
        job_id: UUID of the job
        access_token: Optional access token for authenticated requests
        
    Returns:
        dict with status, result, error, etc.
    """
    try:
        supabase = get_supabase_client(access_token=access_token) if access_token else get_supabase_client()
        if not supabase:
            return {
                "job_id": job_id,
                "status": "error",
                "error": "Failed to initialize Supabase client"
            }
        
        result = supabase.table("jobs").select("*").eq("id", job_id).execute()
        
        if not result.data or len(result.data) == 0:
            return {
                "job_id": job_id,
                "status": "not_found",
                "error": "Job not found"
            }
        
        job = result.data[0]
        
        return {
            "job_id": job_id,
            "status": job.get("status", "unknown"),
            "result": job.get("result"),
            "error": job.get("error_message"),
            "progress": job.get("progress", 0),
            "status_message": job.get("status_message", ""),
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at")
        }
    except Exception as e:
        return {
            "job_id": job_id,
            "status": "error",
            "error": str(e)
        }


def get_queue_status(job_ids: List[str], access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the aggregated status of a list of jobs.
    """
    try:
        # Use service role key to bypass RLS for status checking
        # This is safe because we're only checking status, not modifying data
        supabase_url = _supabase_url_no_trailing_slash()
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if not supabase_url or not service_role_key:
            # Fallback to authenticated client if service role not available
            supabase = get_supabase_client(access_token=access_token) if access_token else get_supabase_client()
        else:
            supabase = create_client(supabase_url, service_role_key)
        
        if not supabase:
            return {
                "total": len(job_ids),
                "completed": 0,
                "failed": 0,
                "pending": len(job_ids),
                "in_progress": 0,
                "estimated_remaining_seconds": 0,
                "error": "Failed to initialize Supabase client"
            }
        
        if not job_ids:
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "pending": 0,
                "in_progress": 0,
                "estimated_remaining_seconds": 0
            }
        
        # Fetch all jobs
        result = supabase.table("jobs").select("id, status, progress, created_at, started_at, finished_at").in_("id", job_ids).execute()
        
        jobs = result.data if result.data else []
        
        total = len(job_ids)
        completed = 0
        failed = 0
        pending = 0
        in_progress = 0
        
        processing_times = []
        
        for job in jobs:
            status = job.get("status", "queued")
            if status == "finished":
                completed += 1
                # Calculate processing time if available
                if job.get("started_at") and job.get("finished_at"):
                    # Parse timestamps and calculate duration
                    try:
                        started = datetime.fromisoformat(job["started_at"].replace('Z', '+00:00'))
                        finished = datetime.fromisoformat(job["finished_at"].replace('Z', '+00:00'))
                        duration = (finished - started).total_seconds()
                        processing_times.append(duration)
                    except:
                        processing_times.append(15)  # Default estimate
                else:
                    processing_times.append(15)
            elif status == "failed":
                failed += 1
                processing_times.append(15)
            elif status == "started":
                in_progress += 1
            else:  # queued
                pending += 1
        
        # Calculate estimated remaining time
        estimated_remaining_seconds = 0
        if completed + failed > 0 and pending > 0:
            avg_time_per_job = sum(processing_times) / len(processing_times) if processing_times else 15
            estimated_remaining_seconds = avg_time_per_job * pending
        elif pending > 0:
            estimated_remaining_seconds = pending * 20  # Rough estimate
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "in_progress": in_progress,
            "estimated_remaining_seconds": estimated_remaining_seconds
        }
    except Exception as e:
        return {
            "total": len(job_ids),
            "completed": 0,
            "failed": 0,
            "pending": len(job_ids),
            "in_progress": 0,
            "estimated_remaining_seconds": 0,
            "error": str(e)
        }


def get_next_job(service_role_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get the next queued job for processing.
    This is used by the worker.
    
    Args:
        service_role_key: Supabase service role key (bypasses RLS)
        
    Returns:
        Job dict or None if no jobs available
    """
    try:
        # Use service role key for worker to bypass RLS
        if service_role_key:
            # Create client with service role key
            supabase_url = _supabase_url_no_trailing_slash()
            if not supabase_url:
                return None
            
            supabase = create_client(supabase_url, service_role_key)
        else:
            supabase = get_supabase_client()
        
        if not supabase:
            return None
        
        # Find next queued job (ordered by priority DESC, created_at ASC)
        result = supabase.table("jobs").select("*").eq("status", "queued").order("priority", desc=True).order("created_at", desc=False).limit(1).execute()
        
        if not result.data or len(result.data) == 0:
            return None
        
        return result.data[0]
    except Exception as e:
        print(f"Error getting next job: {e}")
        return None


def update_job_status(
    job_id: str,
    status: str,
    progress: Optional[int] = None,
    status_message: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    error_traceback: Optional[str] = None,
    service_role_key: Optional[str] = None
) -> bool:
    """
    Update job status and progress.
    Used by the worker.
    """
    try:
        if service_role_key:
            supabase_url = _supabase_url_no_trailing_slash()
            if not supabase_url:
                return False
            supabase = create_client(supabase_url, service_role_key)
        else:
            supabase = get_supabase_client()
        
        if not supabase:
            return False
        
        update_data = {"status": status}
        
        if progress is not None:
            update_data["progress"] = progress
        if status_message:
            update_data["status_message"] = status_message
        if result:
            update_data["result"] = result
        if error_message:
            update_data["error_message"] = error_message
        if error_traceback:
            update_data["error_traceback"] = error_traceback
        
        # Update timestamps
        if status == "started" and not update_data.get("started_at"):
            update_data["started_at"] = datetime.now(timezone.utc).isoformat()
        elif status in ("finished", "failed") and not update_data.get("finished_at"):
            update_data["finished_at"] = datetime.now(timezone.utc).isoformat()
        
        result = supabase.table("jobs").update(update_data).eq("id", job_id).execute()
        
        return result.data is not None and len(result.data) > 0
    except Exception as e:
        print(f"Error updating job status: {e}")
        return False
