"""
Background job for processing a single submission.
This runs in a worker process, separate from the Flask request handler.
"""

import os
import tempfile
import traceback
from pathlib import Path
from pipeline.runner import process_submission
from pipeline.supabase_storage import ingest_upload_supabase
from pipeline.supabase_db import save_record as save_db_record
from pipeline.pdf_splitter import detect_multi_entry, split_pdf
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
        # Upload to Supabase Storage
        ingest_data = ingest_upload_supabase(
            uploaded_bytes=file_bytes,
            original_filename=filename,
            owner_user_id=owner_user_id,
            access_token=access_token
        )
        
        # Create temporary file for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name
        
        try:
            # Detect if PDF has multiple entries
            import logging
            logging.info(f"🔍 Starting multi-entry detection for {filename}...")
            detection = detect_multi_entry(tmp_path)
            logging.info(f"📄 Multi-entry detection: {detection.total_entries} entries found (confidence: {detection.confidence:.2f})")
            logging.info(f"📄 Is multi-entry: {detection.is_multi_entry}, Pattern: {detection.pattern}")
            logging.info(f"🔍 Checking condition: is_multi_entry={detection.is_multi_entry}, total_entries={detection.total_entries} > 1")
            
            if detection.is_multi_entry and detection.total_entries > 1:
                logging.info(f"✅ ENTERING multi-entry processing block!")
                # Multi-entry PDF - split and process each
                logging.info(f"🔀 Splitting PDF into {detection.total_entries} individual entries...")
                
                # Create temp directory for split PDFs
                split_dir = tempfile.mkdtemp(prefix="split_pdfs_")
                logging.info(f"📁 Created temp directory: {split_dir}")
                split_paths = split_pdf(tmp_path, detection.entry_boundaries, split_dir)
                logging.info(f"📄 Split complete! Created {len(split_paths)} PDFs")
                
                results = []
                for idx, split_path in enumerate(split_paths, start=1):
                    try:
                        logging.info(f"🔄 Processing entry {idx}/{len(split_paths)}: {Path(split_path).name}")
                        
                        # Create new storage entry for this split
                        with open(split_path, 'rb') as f:
                            split_bytes = f.read()
                        
                        split_filename = f"{Path(filename).stem}_entry_{idx}{Path(filename).suffix}"
                        logging.info(f"📤 Uploading {split_filename} to storage...")
                        split_ingest = ingest_upload_supabase(
                            uploaded_bytes=split_bytes,
                            original_filename=split_filename,
                            owner_user_id=owner_user_id,
                            access_token=access_token
                        )
                        
                        logging.info(f"🔍 Running OCR and extraction for entry {idx}...")
                        # Process this entry
                        record, report = process_submission(
                            image_path=split_path,
                            submission_id=split_ingest["submission_id"],
                            artifact_dir=split_ingest["artifact_dir"],
                            ocr_provider_name=ocr_provider,
                            original_filename=split_filename
                        )
                        
                        logging.info(f"💾 Saving entry {idx} to database...")
                        # Save to database
                        save_db_record(
                            record=record,
                            filename=split_filename,
                            owner_user_id=owner_user_id,
                            access_token=access_token,
                            upload_batch_id=upload_batch_id
                        )
                        
                        results.append({
                            "entry_number": idx,
                            "filename": split_filename,
                            "submission_id": split_ingest["submission_id"],
                            "student_name": record.student_name if hasattr(record, 'student_name') else None,
                            "status": "success"
                        })
                        
                        logging.info(f"✅ Entry {idx}/{len(split_paths)} completed successfully!")
                        
                    except Exception as e:
                        logging.error(f"❌ Error processing entry {idx}: {str(e)}")
                        logging.error(f"Traceback: {traceback.format_exc()}")
                        results.append({
                            "entry_number": idx,
                            "filename": f"{Path(filename).stem}_entry_{idx}{Path(filename).suffix}",
                            "submission_id": None,
                            "student_name": None,
                            "status": "error",
                            "error": str(e)
                        })
                        continue  # Continue with next entry
                    
                    # Clean up split PDF
                    try:
                        os.unlink(split_path)
                    except:
                        pass
                
                # Clean up split directory
                try:
                    os.rmdir(split_dir)
                except:
                    pass
                
                # Clean up original temp file
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                
                print(f"✅ Successfully processed {len(results)} entries from multi-entry PDF")
                
                # Send email notification
                try:
                    user_email = get_user_email_from_token(access_token)
                    print(f"📧 Retrieved user_email: {user_email}")
                    if user_email:
                        from rq import get_current_job
                        current_job = get_current_job()
                        job_id = current_job.id if current_job else None
                        
                        if job_id:
                            job_url = get_job_url(job_id)
                            print(f"📧 Sending completion email to {user_email} for {filename}")
                            result_email = send_job_completion_email(
                                user_email=user_email,
                                job_id=job_id,
                                job_status="completed",
                                filename=f"{filename} ({len(results)} entries)",
                                job_url=job_url
                            )
                            print(f"📧 Email sent: {result_email}")
                except Exception as e:
                    print(f"⚠️ Failed to send email notification: {str(e)}")
                
                # IMPORTANT: Return early for multi-entry PDFs
                return {
                    "status": "success",
                    "multi_entry": True,
                    "total_entries": len(results),
                    "results": results,
                    "message": f"Successfully processed {len(results)} entries"
                }
            
            # Single-entry PDF continues below...
            
            else:
                # Single-entry PDF - process normally
                print(f"📄 Processing as single-entry PDF")
            record, report = process_submission(
                image_path=tmp_path,
                submission_id=ingest_data["submission_id"],
                artifact_dir=ingest_data["artifact_dir"],
                ocr_provider_name=ocr_provider,
                original_filename=filename
            )
            
            # Update artifact_dir to use Supabase Storage path
            record.artifact_dir = ingest_data["artifact_dir"]
            
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
                print(f"📧 Retrieved user_email: {user_email}")
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
                        print(f"📧 Sending completion email to {user_email} for {filename}")
                        result = send_job_completion_email(
                            user_email=user_email,
                            job_id=job_id,
                            job_status="completed",
                            filename=filename,
                            job_url=job_url
                        )
                        print(f"📧 Email sent: {result}")
                    else:
                        # Fallback: send email without job URL (use submission_id)
                        print(f"📧 Sending completion email (no job URL) to {user_email} for {filename}")
                        result = send_job_completion_email(
                            user_email=user_email,
                            job_id=result.get("submission_id", "unknown"),
                            job_status="completed",
                            filename=filename
                        )
                        print(f"📧 Email sent: {result}")
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

