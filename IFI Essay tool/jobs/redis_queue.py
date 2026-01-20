"""
Redis-based job queue using RQ (Redis Queue).
Provides job queue functionality using Redis instead of PostgreSQL.
"""

import os
import base64
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from redis import Redis
from rq import Queue
from rq.job import Job
from rq.exceptions import NoSuchJobError


def get_redis_client() -> Redis:
    """Get Redis client connection."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    
    # Parse Redis URL
    if redis_url.startswith("redis://"):
        # Extract connection details from URL
        # Format: redis://[:password@]host[:port][/db]
        import urllib.parse
        parsed = urllib.parse.urlparse(redis_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        db = int(parsed.path.lstrip('/')) if parsed.path else 0
        password = parsed.password
        
        if password:
            return Redis(host=host, port=port, db=db, password=password, decode_responses=False)
        else:
            return Redis(host=host, port=port, db=db, decode_responses=False)
    else:
        # Fallback to default
        return Redis(host="localhost", port=6379, db=0, decode_responses=False)


def get_queue() -> Queue:
    """Get RQ queue instance."""
    redis_client = get_redis_client()
    return Queue("submissions", connection=redis_client)


def enqueue_submission(
    file_bytes: bytes,
    filename: str,
    owner_user_id: str,
    access_token: str,
    ocr_provider: str = "google",
    upload_batch_id: Optional[str] = None
) -> str:
    """
    Enqueue a submission for background processing using Redis/RQ.
    
    Returns:
        Job ID (string)
        
    Raises:
        Exception if job cannot be enqueued
    """
    try:
        from jobs.process_submission import process_submission_job
        
        # Prepare job data
        job_data = {
            "file_bytes_base64": base64.b64encode(file_bytes).decode('utf-8'),
            "filename": filename,
            "owner_user_id": owner_user_id,
            "access_token": access_token,
            "ocr_provider": ocr_provider,
            "upload_batch_id": upload_batch_id
        }
        
        # Enqueue job to Redis
        queue = get_queue()
        job = queue.enqueue(
            process_submission_job,
            file_bytes=file_bytes,
            filename=filename,
            owner_user_id=owner_user_id,
            access_token=access_token,
            ocr_provider=ocr_provider,
            upload_batch_id=upload_batch_id,
            job_timeout=600,  # 10 minutes timeout
            result_ttl=3600,  # Keep result for 1 hour
            failure_ttl=86400  # Keep failed jobs for 24 hours
        )
        
        return job.id
        
    except Exception as e:
        raise Exception(f"Failed to enqueue job: {str(e)}")


def get_job_status(job_id: str, access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the status of a job.
    
    Returns:
        dict with status, result, error, etc.
    """
    try:
        redis_client = get_redis_client()
        job = Job.fetch(job_id, connection=redis_client)
        
        # Map RQ job status to our status format
        rq_status = job.get_status()
        status_map = {
            "queued": "queued",
            "started": "started",
            "finished": "finished",
            "failed": "failed",
            "deferred": "queued",
            "scheduled": "queued"
        }
        status = status_map.get(rq_status, "unknown")
        
        result = {
            "job_id": job_id,
            "status": status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.ended_at.isoformat() if job.ended_at else None,
            "progress": 50 if status == "started" else (100 if status == "finished" else 0),
            "status_message": job.description or f"Job {status}",
        }
        
        if status == "finished" and job.result:
            result["result"] = job.result
        elif status == "failed":
            result["error"] = str(job.exc_info) if job.exc_info else "Unknown error"
            
        return result
        
    except NoSuchJobError:
        return {
            "job_id": job_id,
            "status": "not_found",
            "error": "Job not found"
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
        redis_client = get_redis_client()
        
        if not job_ids:
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "pending": 0,
                "in_progress": 0,
                "estimated_remaining_seconds": 0
            }
        
        total = len(job_ids)
        completed = 0
        failed = 0
        pending = 0
        in_progress = 0
        processing_times = []
        
        for job_id in job_ids:
            try:
                job = Job.fetch(job_id, connection=redis_client)
                rq_status = job.get_status()
                
                if rq_status == "finished":
                    completed += 1
                    if job.started_at and job.ended_at:
                        duration = (job.ended_at - job.started_at).total_seconds()
                        processing_times.append(duration)
                elif rq_status == "failed":
                    failed += 1
                    processing_times.append(20)  # Default estimate for failed jobs
                elif rq_status == "started":
                    in_progress += 1
                else:  # queued, deferred, scheduled
                    pending += 1
                    
            except NoSuchJobError:
                # Job not found, count as failed
                failed += 1
            except Exception:
                # Error fetching job, count as pending (might be processing)
                pending += 1
        
        # Calculate estimated remaining time
        estimated_remaining_seconds = 0
        if completed + failed > 0 and pending > 0:
            avg_time_per_job = sum(processing_times) / len(processing_times) if processing_times else 20
            estimated_remaining_seconds = avg_time_per_job * (pending + in_progress)
        elif pending > 0 or in_progress > 0:
            estimated_remaining_seconds = (pending + in_progress) * 20  # Rough estimate
        
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



