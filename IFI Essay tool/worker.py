#!/usr/bin/env python3
"""
PostgreSQL-based Worker for processing submissions in the background.
Replaces Redis/RQ worker with PostgreSQL polling.

Usage:
    python worker.py
"""

import os
import sys
import time
import base64
import logging
from jobs.pg_queue import get_next_job, update_job_status
from jobs.process_submission import process_submission_job

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Get Supabase service role key from environment
# This bypasses RLS so the worker can process any job
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SERVICE_ROLE_KEY:
    logger.error("❌ SUPABASE_SERVICE_ROLE_KEY environment variable is required for the worker")
    logger.error("   Get it from: Supabase Dashboard > Settings > API > service_role key")
    sys.exit(1)

# Worker ID (unique identifier for this worker instance)
WORKER_ID = os.environ.get("WORKER_ID", f"worker-{os.getpid()}")

logger.info(f"🚀 Worker {WORKER_ID} started")
logger.info("📊 Using PostgreSQL-based job queue (Supabase)")
logger.info("⏳ Polling for jobs every 2 seconds...")
logger.info("Press Ctrl+C to stop.")

def process_job(job):
    """Process a single job."""
    job_id = job["id"]
    job_data = job.get("job_data", {})
    
    try:
        # Update job status to "started"
        update_job_status(
            job_id=job_id,
            status="started",
            progress=0,
            status_message=f"Started processing {job_data.get('filename', 'file')}",
            service_role_key=SERVICE_ROLE_KEY
        )
        
        # Decode file bytes from base64
        file_bytes_base64 = job_data.get("file_bytes_base64")
        if not file_bytes_base64:
            raise ValueError("file_bytes_base64 not found in job data")
        
        file_bytes = base64.b64decode(file_bytes_base64)
        
        # Extract job parameters
        filename = job_data.get("filename")
        owner_user_id = job_data.get("owner_user_id")
        access_token = job_data.get("access_token")
        ocr_provider = job_data.get("ocr_provider", "google")
        upload_batch_id = job_data.get("upload_batch_id")  # Optional batch ID
        
        if not all([filename, owner_user_id, access_token]):
            raise ValueError("Missing required job parameters")
        
        # Update progress: uploading
        update_job_status(
            job_id=job_id,
            status="started",
            progress=10,
            status_message=f"Uploading {filename}...",
            service_role_key=SERVICE_ROLE_KEY
        )
        
        # Process the submission
        result = process_submission_job(
            file_bytes=file_bytes,
            filename=filename,
            owner_user_id=owner_user_id,
            access_token=access_token,
            ocr_provider=ocr_provider,
            upload_batch_id=upload_batch_id
        )
        
        # Check if processing succeeded
        if result.get("status") == "error":
            error_msg = result.get("error", "Unknown error")
            update_job_status(
                job_id=job_id,
                status="failed",
                progress=100,
                status_message=f"Failed: {error_msg}",
                error_message=error_msg,
                service_role_key=SERVICE_ROLE_KEY
            )
            logger.error(f"❌ Job {job_id} failed: {error_msg}")
            return False
        
        # Update progress: saving
        update_job_status(
            job_id=job_id,
            status="started",
            progress=90,
            status_message=f"Saving results for {filename}...",
            service_role_key=SERVICE_ROLE_KEY
        )
        
        # Mark job as finished
        update_job_status(
            job_id=job_id,
            status="finished",
            progress=100,
            status_message=f"Finished processing {filename}",
            result=result,
            service_role_key=SERVICE_ROLE_KEY
        )
        
        logger.info(f"✅ Job {job_id} completed: {filename}")
        return True
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        
        update_job_status(
            job_id=job_id,
            status="failed",
            progress=100,
            status_message=f"Error: {str(e)}",
            error_message=str(e),
            error_traceback=error_traceback,
            service_role_key=SERVICE_ROLE_KEY
        )
        
        logger.error(f"❌ Job {job_id} failed with exception: {e}")
        logger.debug(error_traceback)
        return False


def main():
    """Main worker loop."""
    poll_interval = 2  # seconds
    
    try:
        while True:
            try:
                # Get next queued job
                job = get_next_job(service_role_key=SERVICE_ROLE_KEY)
                
                if job:
                    logger.info(f"📥 Processing job {job['id']}: {job.get('job_data', {}).get('filename', 'unknown')}")
                    process_job(job)
                else:
                    # No jobs available, wait before polling again
                    time.sleep(poll_interval)
                    
            except KeyboardInterrupt:
                logger.info("\n🛑 Worker stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Error in worker loop: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                time.sleep(poll_interval)  # Wait before retrying
                
    except KeyboardInterrupt:
        logger.info("\n🛑 Worker stopped")


if __name__ == '__main__':
    main()
