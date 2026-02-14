"""
Background job for processing a single submission.
This runs in a worker process, separate from the Flask request handler.
"""

import os
import json
import logging
import tempfile
from pathlib import Path
from pipeline.runner import process_submission
from pipeline.supabase_storage import ingest_upload_supabase
from pipeline.supabase_db import save_record as save_db_record
from utils.email_notification import send_job_completion_email, get_job_url, get_user_email_from_token
from pipeline.document_analysis import analyze_document, make_chunk_submission_id
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


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
        logger.info(f"📄 Processing {filename} for user {owner_user_id}")

        # Use service role key for storage uploads in the worker.
        # The user's access_token (JWT) may have expired by the time
        # the worker picks up the job; the service role key bypasses RLS.
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        storage_token = service_role_key if service_role_key else access_token

        # Upload to Supabase Storage
        logger.info(f"⬆️ Uploading {filename} to Supabase Storage...")
        ingest_data = ingest_upload_supabase(
            uploaded_bytes=file_bytes,
            original_filename=filename,
            owner_user_id=owner_user_id,
            access_token=storage_token
        )
        logger.info(f"✅ Uploaded → submission_id={ingest_data['submission_id']}")
        # Create temporary file for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name

        # Analyze document for format/structure and chunking
        analysis = analyze_document(tmp_path, ocr_provider_name=ocr_provider)
        logger.info(f"🧭 Analysis: format={analysis.format}, structure={analysis.structure}, chunks={len(analysis.chunk_ranges)}")

        results = []
        doc = fitz.open(tmp_path)

        traceability_entries = []
        try:
            for idx, chunk in enumerate(analysis.chunk_ranges):
                # Extract chunk pages to a temp PDF
                chunk_doc = fitz.open()
                chunk_doc.insert_pdf(doc, from_page=chunk.start_page, to_page=chunk.end_page)
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as chunk_file:
                    chunk_doc.save(chunk_file.name)
                    chunk_path = chunk_file.name

                chunk_submission_id = make_chunk_submission_id(ingest_data["submission_id"], idx)
                run_id = ingest_data["submission_id"]
                chunk_artifact_dir = f"{owner_user_id}/{run_id}/artifacts/{run_id}/chunk_{idx}_{chunk_submission_id}"

                logger.info(f"🔍 Chunk {idx+1}/{len(analysis.chunk_ranges)} pages {chunk.start_page+1}-{chunk.end_page+1}")
                record, report = process_submission(
                    image_path=chunk_path,
                    submission_id=chunk_submission_id,
                    artifact_dir=chunk_artifact_dir,
                    ocr_provider_name=ocr_provider,
                    original_filename=filename,
                    chunk_metadata={
                        "parent_submission_id": ingest_data["submission_id"],
                        "chunk_index": idx,
                        "chunk_page_start": chunk.start_page + 1,
                        "chunk_page_end": chunk.end_page + 1,
                        "chunk_submission_id": chunk_submission_id,
                        "is_chunk": len(analysis.chunk_ranges) > 1,
                        "template_detected": analysis.structure == "template",
                        "template_blocked_low_confidence": analysis.low_confidence_for_template,
                    },
                    doc_format=analysis.format,
                )
                logger.info(f"✅ Chunk {idx+1}: student={record.student_name}, word_count={record.word_count}")

                record.artifact_dir = chunk_artifact_dir

                logger.info("💾 Saving chunk record to database...")
                save_result = save_db_record(
                    record,
                    filename=filename,
                    owner_user_id=owner_user_id,
                    access_token=storage_token,
                    upload_batch_id=upload_batch_id
                )

                if not save_result.get("success", False):
                    raise Exception(f"Failed to save record to database: {save_result.get('error', 'unknown')}")

                is_update = save_result.get("is_update", False)
                previous_owner = save_result.get("previous_owner_user_id")
                is_own_duplicate = (previous_owner == owner_user_id) if previous_owner else False

                record_dict = record.model_dump() if hasattr(record, 'model_dump') else record.dict()
                results.append({
                    "status": "success",
                    "filename": filename,
                    "submission_id": chunk_submission_id,
                    "record": record_dict,
                    "storage_url": ingest_data.get("storage_url"),
                    "is_duplicate": is_update,
                    "is_own_duplicate": is_own_duplicate,
                    "was_update": is_update,
                    "chunk_index": idx,
                    "chunk_pages": f"{chunk.start_page+1}-{chunk.end_page+1}",
                    "parent_submission_id": ingest_data["submission_id"],
                    "chunk_index": idx,
                })

                # Upload minimal per-chunk audit artifacts (no raw essay text)
                try:
                    from pipeline.supabase_storage import upload_file
                    base_prefix = f"{owner_user_id}/{ingest_data['submission_id']}/artifacts/{run_id}/chunk_{idx}_{chunk_submission_id}"
                    if report.get("ocr_summary"):
                        upload_file(
                            json.dumps(report["ocr_summary"]).encode("utf-8"),
                            f"{base_prefix}/ocr_summary.json",
                            content_type="application/json",
                            access_token=storage_token
                        )
                    extracted_fields = {
                        "student_name": record.student_name,
                        "school_name": record.school_name,
                        "grade": record.grade,
                        "word_count": record.word_count,
                        "needs_review": record.needs_review,
                    }
                    upload_file(
                        json.dumps(extracted_fields).encode("utf-8"),
                        f"{base_prefix}/extracted_fields.json",
                        content_type="application/json",
                        access_token=storage_token
                    )
                    if report.get("stages", {}).get("validation"):
                        upload_file(
                            json.dumps(report["stages"]["validation"]).encode("utf-8"),
                            f"{base_prefix}/validation.json",
                            content_type="application/json",
                            access_token=storage_token
                        )
                    traceability = {
                        "parent_submission_id": ingest_data["submission_id"],
                        "chunk_submission_id": chunk_submission_id,
                        "chunk_index": idx,
                        "chunk_page_start": chunk.start_page + 1,
                        "chunk_page_end": chunk.end_page + 1,
                        "artifact_prefix": base_prefix,
                        "analysis_classifier_version": analysis.classifier_version,
                    }
                    upload_file(
                        json.dumps(traceability).encode("utf-8"),
                        f"{base_prefix}/traceability.json",
                        content_type="application/json",
                        access_token=storage_token
                    )
                    traceability_entries.append({
                        "chunk_submission_id": chunk_submission_id,
                        "chunk_index": idx,
                        "artifact_prefix": base_prefix,
                        "traceability_path": f"{base_prefix}/traceability.json",
                    })
                except Exception as artifact_err:
                    logger.warning(f"⚠️ Failed to upload chunk artifacts: {artifact_err}")

                try:
                    os.unlink(chunk_path)
                except Exception:
                    pass
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        # Persist analysis JSON to storage for audit
        try:
            analysis_dict = json.loads(analysis.to_json())
            if traceability_entries:
                analysis_dict["traceability_artifacts"] = traceability_entries
            analysis_json = json.dumps(analysis_dict, indent=2)
            analysis_path = f"{owner_user_id}/{ingest_data['submission_id']}/artifacts/{ingest_data['submission_id']}/analysis.json"
            from pipeline.supabase_storage import upload_file
            upload_file(file_bytes=analysis_json.encode("utf-8"), file_path=analysis_path, content_type="application/json", access_token=storage_token)
        except Exception as e:
            logger.warning(f"⚠️ Failed to upload analysis artifact: {e}")

        # Send email once after processing all chunks
        try:
            user_email = get_user_email_from_token(access_token)
            if user_email:
                job_id = None
                try:
                    from rq import get_current_job
                    current_job = get_current_job()
                    if current_job:
                        job_id = current_job.id
                except Exception:
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
        except Exception as email_error:
            logger.warning(f"⚠️ Failed to send email notification: {email_error}")

        # Return first chunk result for compatibility
        return results[0] if results else {"status": "failed", "error": "No chunks processed"}
                
    except Exception as e:
        logger.error(f"❌ FAILED processing {filename}: {e}", exc_info=True)

        # Send email notification on failure
        try:
            user_email = get_user_email_from_token(access_token)
            if user_email:
                job_id = None
                try:
                    from rq import get_current_job
                    current_job = get_current_job()
                    if current_job:
                        job_id = current_job.id
                except Exception:
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
                    send_job_completion_email(
                        user_email=user_email,
                        job_id="unknown",
                        job_status="failed",
                        filename=filename,
                        error_message=str(e)
                    )
        except Exception as email_error:
            logger.warning(f"⚠️ Failed to send failure email: {email_error}")

        # Re-raise so RQ marks the job as failed (not silently "finished")
        raise
