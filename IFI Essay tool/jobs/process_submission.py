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


def process_submission_job(
    file_bytes: bytes,
    filename: str,
    owner_user_id: str,
    access_token: str,
    ocr_provider: str = "google"
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
            
            # Save to Supabase database
            save_success = save_db_record(
                record, 
                filename=filename, 
                owner_user_id=owner_user_id, 
                access_token=access_token
            )
            
            if not save_success:
                raise Exception("Failed to save record to database")
            
            # Convert Pydantic model to dict
            record_dict = record.model_dump() if hasattr(record, 'model_dump') else record.dict()
            
            return {
                "status": "success",
                "filename": filename,
                "submission_id": ingest_data["submission_id"],
                "record": record_dict,
                "storage_url": ingest_data.get("storage_url")
            }
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
                
    except Exception as e:
        return {
            "status": "error",
            "filename": filename,
            "error": str(e)
        }

