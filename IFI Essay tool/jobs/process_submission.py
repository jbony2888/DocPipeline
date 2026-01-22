"""
Background job for processing a single submission.
This runs in a worker process, separate from the Flask request handler.
"""

import os
import tempfile
import logging
from pathlib import Path
from pipeline.runner import process_submission
from pipeline.supabase_storage import ingest_upload_supabase
from pipeline.supabase_db import save_record as save_db_record
from utils.email_notification import send_job_completion_email, get_job_url, get_user_email_from_token
from pipeline.pdf_splitter import analyze_pdf_structure, should_split_pdf, split_pdf_into_groups

logger = logging.getLogger(__name__)


def process_submission_job(
    file_bytes: bytes,
    filename: str,
    owner_user_id: str,
    access_token: str,
    ocr_provider: str = "google",
    upload_batch_id: str = None,
    parent_submission_id: str = None,
    split_group_index: int = None
):
    """
    Process a single submission in the background.
    
    Args:
        file_bytes: File content as bytes
        filename: Original filename
        owner_user_id: User ID who uploaded the file
        access_token: Supabase access token for authenticated operations
        ocr_provider: OCR provider to use
        upload_batch_id: Batch ID for grouping uploads
        parent_submission_id: If this is a split entry, the parent submission ID
        split_group_index: If this is a split entry, the group index (0-based)
        
    Returns:
        dict with status and result/error
    """
    try:
        # Create temporary file for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name
        
        try:
            # Check if this is a PDF that might contain multiple entries
            is_pdf = Path(filename).suffix.lower() == '.pdf'
            should_check_split = is_pdf and parent_submission_id is None  # Only check original uploads, not already-split entries
            
            if should_check_split:
                logger.info(f"Analyzing PDF for multi-entry detection: {filename}")
                analysis = analyze_pdf_structure(tmp_path)
                
                if should_split_pdf(analysis):
                    # Multi-entry PDF detected - split and process each entry
                    logger.info(f"Multi-entry PDF detected: {filename} ({len(analysis.detected_groups)} entries, confidence={analysis.confidence:.2f})")
                    
                    # Upload parent record to Supabase Storage (original file)
                    parent_ingest_data = ingest_upload_supabase(
                        uploaded_bytes=file_bytes,
                        original_filename=filename,
                        owner_user_id=owner_user_id,
                        access_token=access_token
                    )
                    
                    parent_submission_id = parent_ingest_data["submission_id"]
                    
                    # Create temp directory for split PDFs
                    split_dir = tempfile.mkdtemp(prefix="pdf_split_")
                    base_filename = Path(filename).stem
                    
                    # Split PDF into separate files
                    split_artifacts = split_pdf_into_groups(
                        pdf_path=tmp_path,
                        groups=analysis.detected_groups,
                        output_dir=split_dir,
                        base_filename=base_filename
                    )
                    
                    # Enqueue jobs for each split entry
                    results = []
                    for artifact in split_artifacts:
                        with open(artifact.output_pdf_path, 'rb') as f:
                            split_file_bytes = f.read()
                        
                        split_filename = Path(artifact.output_pdf_path).name
                        
                        # Process this split entry (recursive call, but with parent_submission_id set)
                        try:
                            split_result = process_submission_job(
                                file_bytes=split_file_bytes,
                                filename=split_filename,
                                owner_user_id=owner_user_id,
                                access_token=access_token,
                                ocr_provider=ocr_provider,
                                upload_batch_id=upload_batch_id,
                                parent_submission_id=parent_submission_id,
                                split_group_index=artifact.group_index
                            )
                            results.append(split_result)
                        except Exception as split_error:
                            logger.error(f"Error processing split entry {artifact.group_index}: {split_error}")
                            results.append({
                                "status": "error",
                                "filename": split_filename,
                                "error": str(split_error),
                                "split_group_index": artifact.group_index
                            })
                    
                    # Clean up split files
                    import shutil
                    try:
                        shutil.rmtree(split_dir)
                    except:
                        pass
                    
                    # Return summary of all split entries
                    return {
                        "status": "success",
                        "filename": filename,
                        "submission_id": parent_submission_id,
                        "is_multi_entry": True,
                        "split_count": len(results),
                        "split_results": results,
                        "analysis": {
                            "page_count": analysis.page_count,
                            "confidence": analysis.confidence,
                            "groups": analysis.detected_groups
                        }
                    }
            
            # Single-entry processing (original flow)
            # Upload to Supabase Storage
            ingest_data = ingest_upload_supabase(
                uploaded_bytes=file_bytes,
                original_filename=filename,
                owner_user_id=owner_user_id,
                access_token=access_token
            )
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
            
            # Add multi-entry metadata if this is a split entry
            record_dict = record.model_dump() if hasattr(record, 'model_dump') else record.dict()
            if parent_submission_id:
                record_dict["parent_submission_id"] = parent_submission_id
                record_dict["split_group_index"] = split_group_index
                record_dict["multi_entry_source"] = True
            
            # Save to Supabase database
            save_result = save_db_record(
                record, 
                filename=filename, 
                owner_user_id=owner_user_id, 
                access_token=access_token,
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

