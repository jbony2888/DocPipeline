"""
Background job for processing a single submission.
This runs in a worker process, separate from the Flask request handler.
"""

import os
import tempfile
from pathlib import Path
from pipeline.runner import process_submission
from pipeline.supabase_storage import ingest_upload_supabase
from pipeline.supabase_db import save_record as save_db_record
from utils.email_notification import send_job_completion_email, get_job_url, get_user_email_from_token


def process_submission_job(
    file_bytes: bytes,
    filename: str,
    owner_user_id: str,
    access_token: str,
    ocr_provider: str = "google",
    upload_batch_id: str = None
):
    """
    Process a single submission in the background.
    
    Args:
        file_bytes: File content as bytes
        filename: Original filename
        owner_user_id: User ID who uploaded the file
        access_token: Supabase access token for authenticated operations
        ocr_provider: OCR provider to use
        
    Returns:
        dict with status and result/error
    """
    try:
        # Use service role key for storage uploads in the worker.
        # The user's access_token (JWT) may have expired by the time
        # the worker picks up the job; the service role key bypasses RLS.
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        storage_token = service_role_key if service_role_key else access_token

        # Upload to Supabase Storage
        ingest_data = ingest_upload_supabase(
            uploaded_bytes=file_bytes,
            original_filename=filename,
            owner_user_id=owner_user_id,
            access_token=storage_token
        )
        
        # Create temporary file for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name
        
        try:
            # Process the submission
            record, report = process_submission(
                image_path=tmp_path,
                submission_id=ingest_data["submission_id"],
                artifact_dir=ingest_data["artifact_dir"],
                ocr_provider_name=ocr_provider,
                original_filename=filename
            )
            
            # Update artifact_dir to use Supabase Storage path
            record.artifact_dir = ingest_data["artifact_dir"]
            
            # Save to Supabase database (use service role key to bypass RLS)
            save_result = save_db_record(
                record,
                filename=filename,
                owner_user_id=owner_user_id,
                access_token=storage_token,
                upload_batch_id=upload_batch_id
            )
            
            if not save_result.get("success", False):
                raise Exception("Failed to save record to database")
            
            # Get duplicate info from save_result (already checked in save_record)
            is_update = save_result.get("is_update", False)
            previous_owner = save_result.get("previous_owner_user_id")
            is_own_duplicate = (previous_owner == owner_user_id) if previous_owner else False
            
            # Convert Pydantic model to dict
            record_dict = record.model_dump() if hasattr(record, 'model_dump') else record.dict()
            
            result = {
                "status": "success",
                "filename": filename,
                "submission_id": ingest_data["submission_id"],
                "record": record_dict,
                "storage_url": ingest_data.get("storage_url"),
                "is_duplicate": is_update,
                "is_own_duplicate": is_own_duplicate,
                "was_update": is_update
            }
            
            # Send email notification on success
            try:
                user_email = get_user_email_from_token(access_token)
                if user_email:
                    # Get job_id from RQ context if available
                    job_id = None
                    try:
                        from rq import get_current_job
                        current_job = get_current_job()
                        if current_job:
                            job_id = current_job.id
                    except ImportError:
                        # RQ not available (running in different context)
                        pass
                    except Exception:
                        # Job not in RQ context
                        pass
                    
                    if job_id:
                        job_url = get_job_url(job_id)
                        send_job_completion_email(
                            user_email=user_email,
                            job_id=job_id,
                            job_status="completed",
                            filename=filename,
                            job_url=job_url
                        )
                    else:
                        # Fallback: send email without job URL (use submission_id)
                        send_job_completion_email(
                            user_email=user_email,
                            job_id=result.get("submission_id", "unknown"),
                            job_status="completed",
                            filename=filename
                        )
            except Exception as email_error:
                # Don't fail job if email fails
                print(f"⚠️ Failed to send email notification: {email_error}")
                import traceback
                traceback.print_exc()
            
            return result
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
                
    except Exception as e:
        error_result = {
            "status": "error",
            "filename": filename,
            "error": str(e)
        }
        
        # Send email notification on failure
        try:
            user_email = get_user_email_from_token(access_token)
            if user_email:
                # Get job_id from RQ context if available
                job_id = None
                try:
                    from rq import get_current_job
                    current_job = get_current_job()
                    if current_job:
                        job_id = current_job.id
                except ImportError:
                    # RQ not available (running in different context)
                    pass
                except Exception:
                    # Job not in RQ context
                    pass
                
                if job_id:
                    job_url = get_job_url(job_id)
                    send_job_completion_email(
                        user_email=user_email,
                        job_id=job_id,
                        job_status="failed",
                        filename=filename,
                        job_url=job_url,
                        error_message=str(e)
                    )
                else:
                    # Fallback: send email without job URL
                    send_job_completion_email(
                        user_email=user_email,
                        job_id="unknown",
                        job_status="failed",
                        filename=filename,
                        error_message=str(e)
                    )
        except Exception as email_error:
            # Don't fail job if email fails
            print(f"⚠️ Failed to send email notification: {email_error}")
            import traceback
            traceback.print_exc()
        
        return error_result

