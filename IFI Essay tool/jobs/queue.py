"""
Job queue interface using Redis/RQ.
Provides job queue functionality using Redis instead of PostgreSQL.
"""

from typing import List, Dict, Any, Optional
from jobs.redis_queue import (
    enqueue_submission as redis_enqueue_submission,
    get_job_status as redis_get_job_status,
    get_queue_status as redis_get_queue_status
)


def enqueue_submission(file_bytes: bytes, filename: str, owner_user_id: str, 
                      access_token: str, ocr_provider: str = "google", 
                      upload_batch_id: Optional[str] = None) -> str:
    """
    Enqueue a submission for background processing.
    
    Returns:
        Job ID (string)
        
    Raises:
        Exception if job cannot be enqueued
    """
    return redis_enqueue_submission(
        file_bytes=file_bytes,
        filename=filename,
        owner_user_id=owner_user_id,
        access_token=access_token,
        ocr_provider=ocr_provider,
        upload_batch_id=upload_batch_id
    )


def get_job_status(job_id: str, access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the status of a job.
    
    Returns:
        dict with status, result, error, etc.
    """
    return redis_get_job_status(job_id, access_token=access_token)


def get_queue_status(job_ids: List[str], access_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the aggregated status of a list of jobs.
    """
    return redis_get_queue_status(job_ids, access_token=access_token)

