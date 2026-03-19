"""
Background job for processing a single submission.
This runs in a worker process, separate from the Flask request handler.
"""

import os
import json
import logging
import tempfile
import time
import gc
from datetime import datetime, timezone
from pathlib import Path
from pipeline.runner import process_submission
from pipeline.supabase_storage import ingest_upload_supabase
from pipeline.supabase_db import save_record as save_db_record
from pipeline.supabase_metrics import save_processing_metric
from utils.email_notification import send_batch_completion_email, get_review_url, get_user_email_from_token
from pipeline.document_analysis import analyze_document, make_chunk_submission_id, get_batch_iter_ranges
from pipeline.schema import DocClass
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# Image extensions we convert to single-page PDF so the rest of the pipeline always sees a PDF (#5).
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _image_to_pdf(image_path: str) -> str | None:
    """
    Convert a single image (PNG, JPEG) to a one-page PDF using PyMuPDF.
    Returns path to the temp PDF, or None on failure.
    Ensures PNG/image submissions are processed like PDFs (fixes Angel Sagado #5).
    """
    try:
        # Try to open as image to get dimensions (works in many PyMuPDF versions)
        try:
            img_doc = fitz.open(image_path)
            if len(img_doc) > 0:
                page_rect = img_doc[0].rect
                img_doc.close()
                out_doc = fitz.open()
                page = out_doc.new_page(width=page_rect.width, height=page_rect.height)
                page.insert_image(page.rect, filename=image_path)
            else:
                img_doc.close()
                raise ValueError("Empty image document")
        except Exception:
            # Fallback: create default page and insert image (image may scale)
            out_doc = fitz.open()
            page = out_doc.new_page()
            page.insert_image(page.rect, filename=image_path)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            out_doc.save(tmp.name)
            path = tmp.name
        out_doc.close()
        return path
    except Exception as e:
        logger.warning("Image-to-PDF conversion failed for %s: %s", image_path, e)
        return None


def _write_batch_verification_summary(upload_batch_id: str) -> None:
    """Write batch results to verification_summary.json in project root for feedback verification."""
    if not upload_batch_id:
        return
    try:
        from pipeline.supabase_db import _get_service_role_client
        from collections import defaultdict
        client = _get_service_role_client()
        if not client:
            return
        result = (
            client.table("submissions")
            .select("submission_id, filename, doc_class, student_name, school_name, grade, word_count, needs_review, review_reason_codes")
            .eq("upload_batch_id", upload_batch_id)
            .order("created_at", desc=False)
            .execute()
        )
        submissions = result.data or []
        if not submissions:
            return
        by_filename = defaultdict(list)
        for s in submissions:
            fn = s.get("filename") or "unknown"
            by_filename[fn].append({
                "submission_id": s.get("submission_id"),
                "doc_class": s.get("doc_class"),
                "student_name": s.get("student_name"),
                "school_name": s.get("school_name"),
                "grade": s.get("grade"),
                "word_count": s.get("word_count"),
                "needs_review": s.get("needs_review"),
                "review_reason_codes": s.get("review_reason_codes") or "",
            })
        files = []
        for filename, records in sorted(by_filename.items()):
            files.append({"filename": filename, "chunk_count": len(records), "records": records})
        summary = {
            "batch_id": upload_batch_id,
            "total_files": len(by_filename),
            "total_records": len(submissions),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "app_production",
        }
        payload = {"summary": summary, "files": files}
        repo_root = Path(__file__).resolve().parent.parent
        out_path = repo_root / "verification_summary.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"📄 Wrote verification summary to {out_path}")
    except Exception as e:
        logger.warning(f"Failed to write verification summary: {e}")


def _maybe_send_batch_completion(
    batch_run_id: str,
    access_token: str,
    upload_batch_id: str,
) -> None:
    """If this job is the last in the batch, send one batch completion email."""
    if not batch_run_id:
        return
    try:
        from jobs.redis_queue import get_redis_client
        redis = get_redis_client()
        key = f"batch_run:{batch_run_id}"
        completed = redis.incr(f"{key}:completed")
        raw = redis.get(key)
        if not raw:
            return
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        total = data.get("total", 0)
        logger.info(f"📬 Batch progress: {completed}/{total} jobs completed (batch_run_id={batch_run_id[:8]}...)")
        if completed < total:
            return
        user_email = get_user_email_from_token(access_token)
        if not user_email:
            logger.warning("Batch complete but no user email from token; skipping batch completion email")
            return
        review_url = get_review_url(upload_batch_id or None)
        logger.info(f"📧 Sending batch completion email to {user_email} (total={total})")
        send_batch_completion_email(user_email, total, review_url)
        redis.delete(key)
        redis.delete(f"{key}:completed")
        logger.info("✅ Batch completion email sent")
        _write_batch_verification_summary(upload_batch_id)
    except Exception as e:
        logger.warning(f"Failed to send batch completion email: {e}")


def process_submission_job(
    file_bytes: bytes,
    filename: str,
    owner_user_id: str,
    access_token: str,
    ocr_provider: str = "google",
    upload_batch_id: str = None,
    batch_run_id: str = None,
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
    job_id = None
    job_started_at = datetime.now(timezone.utc)
    job_timer_start = time.perf_counter()
    ingest_data = None
    analysis = None
    chunk_context = None
    queue_wait_ms = None
    converted_pdf_path = None
    try:
        try:
            from rq import get_current_job
            current_job = get_current_job()
            if current_job:
                job_id = current_job.id
                if current_job.enqueued_at and current_job.started_at:
                    queue_wait_ms = round(
                        (current_job.started_at - current_job.enqueued_at).total_seconds() * 1000,
                        2,
                    )
        except Exception:
            pass
        logger.info(f"📄 Job started: job_id={job_id or 'sync'} filename={filename} batch_run_id={batch_run_id[:8] if batch_run_id else 'none'}...")
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

        # Convert Word or image (PNG/JPEG) to PDF before analysis so pipeline always sees a PDF (#5)
        ext = Path(filename).suffix.lower()
        if ext in (".doc", ".docx"):
            from pipeline.word_converter import convert_word_to_pdf
            converted_pdf_path = convert_word_to_pdf(tmp_path)
            if not converted_pdf_path:
                raise ValueError(
                    f"Could not convert Word document to PDF. "
                    f"For .doc files, LibreOffice must be installed. "
                    f"For .docx, python-docx and reportlab are required."
                )
            processing_path = converted_pdf_path
        elif ext in IMAGE_EXTENSIONS:
            converted_pdf_path = _image_to_pdf(tmp_path)
            if not converted_pdf_path:
                raise ValueError(
                    f"Could not convert image ({ext}) to PDF. The file may be corrupted or in an unsupported format."
                )
            processing_path = converted_pdf_path
            logger.info(f"📷 Converted image to single-page PDF for processing")
        else:
            processing_path = tmp_path

        # Analyze document for format/structure and chunking
        analysis = analyze_document(processing_path, ocr_provider_name=ocr_provider)
        logger.info(f"🧭 Analysis: format={analysis.format}, structure={analysis.structure}, chunks={len(analysis.chunk_ranges)}")

        # BULK_SCANNED_BATCH: paired metadata+essay when alternating; else one submission per page
        iter_ranges = (
            get_batch_iter_ranges(analysis)
            if analysis.doc_class == DocClass.BULK_SCANNED_BATCH
            else analysis.chunk_ranges
        )
        if analysis.doc_class == DocClass.BULK_SCANNED_BATCH:
            logger.info(f"📑 BULK_SCANNED_BATCH: splitting into {len(iter_ranges)} submission(s)")

        first_result = None
        processed_count = 0
        doc = fitz.open(processing_path)

        traceability_entries = []
        try:
            for idx, chunk in enumerate(iter_ranges):
                chunk_timer_start = time.perf_counter()
                # Extract chunk pages to a temp PDF (widgets=0 avoids PyMuPDF crash on form-filled PDFs)
                chunk_doc = fitz.open()
                chunk_path = None
                try:
                    chunk_doc.insert_pdf(doc, from_page=chunk.start_page, to_page=chunk.end_page, widgets=0)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as chunk_file:
                        chunk_doc.save(chunk_file.name)
                        chunk_path = chunk_file.name
                finally:
                    # Ensure native resources are released every chunk to avoid
                    # memory growth in constrained production workers.
                    try:
                        chunk_doc.close()
                    except Exception:
                        pass

                # For single-chunk docs (e.g. typed form), use the original PDF so AcroForm widgets
                # (Student's Name, School, Grade) are present; the chunk PDF strips widgets and yields N/A.
                image_path = processing_path if len(iter_ranges) == 1 else chunk_path

                chunk_submission_id = make_chunk_submission_id(ingest_data["submission_id"], idx)
                run_id = ingest_data["submission_id"]
                chunk_artifact_dir = f"{owner_user_id}/{run_id}/artifacts/{run_id}/chunk_{idx}_{chunk_submission_id}"
                child_doc_class = DocClass.SINGLE_SCANNED if analysis.doc_class == DocClass.BULK_SCANNED_BATCH else analysis.doc_class
                chunk_context = {
                    "submission_id": chunk_submission_id,
                    "parent_submission_id": ingest_data["submission_id"],
                    "chunk_index": idx,
                    "chunk_page_start": chunk.start_page + 1,
                    "chunk_page_end": chunk.end_page + 1,
                    "doc_class": child_doc_class.value if hasattr(child_doc_class, "value") else str(child_doc_class),
                }

                logger.info(f"🔍 Chunk {idx+1}/{len(iter_ranges)} pages {chunk.start_page+1}-{chunk.end_page+1}")
                # Each batch page is a single-page submission (SINGLE_SCANNED); no shared fields across pages
                record, report = process_submission(
                    image_path=image_path,
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
                        "is_chunk": len(iter_ranges) > 1,
                        "template_detected": analysis.structure == "template",
                        "template_blocked_low_confidence": analysis.low_confidence_for_template,
                        "doc_class": child_doc_class,
                        "analysis_structure": (
                            "single" if analysis.doc_class == DocClass.BULK_SCANNED_BATCH else analysis.structure
                        ),
                        "analysis_form_layout": analysis.form_layout,
                        "analysis_header_signature_score_max": max(
                            (p.header_signature_score for p in analysis.pages),
                            default=0.0,
                        ),
                    },
                    doc_format=analysis.format,
                )
                logger.info(f"✅ Chunk {idx+1}: student={record.student_name}, word_count={record.word_count}")

                record.artifact_dir = chunk_artifact_dir

                # Save record even when needs_review is True (missing name/school/grade): process and flag, don't fail
                logger.info("💾 Saving chunk record to database...")
                save_result = save_db_record(
                    record,
                    filename=filename,
                    owner_user_id=owner_user_id,
                    access_token=storage_token,
                    upload_batch_id=upload_batch_id,
                    essay_text=report.get("essay_text"),
                )

                if not save_result.get("success", False):
                    raise Exception(f"Failed to save record to database: {save_result.get('error', 'unknown')}")

                is_update = save_result.get("is_update", False)
                previous_owner = save_result.get("previous_owner_user_id")
                is_own_duplicate = (previous_owner == owner_user_id) if previous_owner else False
                timing_ms = report.get("timing_ms", {})
                total_processing_ms = round((time.perf_counter() - chunk_timer_start) * 1000, 2)
                save_processing_metric(
                    {
                        "submission_id": chunk_submission_id,
                        "parent_submission_id": ingest_data["submission_id"],
                        "owner_user_id": owner_user_id,
                        "job_id": job_id,
                        "filename": filename,
                        "doc_class": child_doc_class.value if hasattr(child_doc_class, "value") else str(child_doc_class),
                        "ocr_provider": ocr_provider,
                        "status": "success",
                        "upload_batch_id": upload_batch_id,
                        "batch_run_id": batch_run_id,
                        "chunk_index": idx,
                        "chunk_page_start": chunk.start_page + 1,
                        "chunk_page_end": chunk.end_page + 1,
                        "queue_wait_ms": queue_wait_ms,
                        "processing_time_ms": total_processing_ms,
                        "ocr_time_ms": timing_ms.get("ocr"),
                        "segmentation_time_ms": timing_ms.get("segmentation"),
                        "extraction_time_ms": timing_ms.get("extraction"),
                        "validation_time_ms": timing_ms.get("validation"),
                        "pipeline_time_ms": timing_ms.get("total"),
                        "word_count": record.word_count,
                        "ocr_confidence_avg": record.ocr_confidence_avg,
                        "needs_review": record.needs_review,
                        "is_duplicate": bool(is_update),
                        "error_message": None,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

                chunk_result = {
                    "status": "success",
                    "filename": filename,
                    "submission_id": chunk_submission_id,
                    "record": None,
                    "storage_url": ingest_data.get("storage_url"),
                    "is_duplicate": is_update,
                    "is_own_duplicate": is_own_duplicate,
                    "was_update": is_update,
                    "chunk_index": idx,
                    "chunk_pages": f"{chunk.start_page+1}-{chunk.end_page+1}",
                    "parent_submission_id": ingest_data["submission_id"],
                }
                if first_result is None:
                    # Keep only first payload for API compatibility; avoid
                    # retaining all per-chunk record dicts in memory.
                    chunk_result["record"] = (
                        record.model_dump() if hasattr(record, "model_dump") else record.dict()
                    )
                    first_result = chunk_result
                processed_count += 1

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
                    # Pipeline log for review: doc_class, extraction method, normalization, validation (improve system later)
                    if report.get("extraction_debug") or report.get("stages") or report.get("normalization"):
                        pipeline_log = {
                            "doc_class": report.get("extraction_debug", {}).get("doc_class"),
                            "extraction_debug": report.get("extraction_debug"),
                            "normalization": report.get("normalization"),
                            "validation": report.get("stages", {}).get("validation"),
                            "chunk_metadata": report.get("chunk_metadata"),
                        }
                        upload_file(
                            json.dumps(pipeline_log, indent=2).encode("utf-8"),
                            f"{base_prefix}/pipeline_log.json",
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
                    if chunk_path:
                        os.unlink(chunk_path)
                except Exception:
                    pass
                # Drop large refs per chunk to reduce peak memory on long jobs.
                try:
                    del report
                except Exception:
                    pass
                try:
                    del record
                except Exception:
                    pass
                try:
                    del timing_ms
                except Exception:
                    pass
                try:
                    del chunk_result
                except Exception:
                    pass
                # Opportunistic cleanup during long runs helps prevent OOM kills.
                if (idx + 1) % 3 == 0:
                    gc.collect()
        finally:
            try:
                doc.close()
            except Exception:
                pass
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            if converted_pdf_path:
                try:
                    os.unlink(converted_pdf_path)
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

        logger.info(f"✅ Job finished: job_id={job_id or 'sync'} filename={filename}")
        # Send one batch completion email when all jobs in this batch are done
        _maybe_send_batch_completion(batch_run_id, access_token, upload_batch_id)

        # Return first result for compatibility; include batch summary when BULK_SCANNED_BATCH
        out = first_result if first_result else {"status": "failed", "error": "No chunks processed"}
        if first_result and analysis.doc_class == DocClass.BULK_SCANNED_BATCH:
            out = {
                **out,
                "batch_page_count": processed_count,
                "batch_parent_id": ingest_data["submission_id"],
            }
        return out
                
    except Exception as e:
        logger.error(f"❌ FAILED processing {filename}: {e}", exc_info=True)
        save_processing_metric(
            {
                "submission_id": chunk_context.get("submission_id") if chunk_context else None,
                "parent_submission_id": (
                    chunk_context.get("parent_submission_id")
                    if chunk_context
                    else (ingest_data.get("submission_id") if isinstance(ingest_data, dict) else None)
                ),
                "owner_user_id": owner_user_id,
                "job_id": job_id,
                "filename": filename,
                "doc_class": chunk_context.get("doc_class") if chunk_context else (analysis.doc_class.value if analysis else None),
                "ocr_provider": ocr_provider,
                "status": "failed",
                "upload_batch_id": upload_batch_id,
                "batch_run_id": batch_run_id,
                "chunk_index": chunk_context.get("chunk_index") if chunk_context else None,
                "chunk_page_start": chunk_context.get("chunk_page_start") if chunk_context else None,
                "chunk_page_end": chunk_context.get("chunk_page_end") if chunk_context else None,
                "queue_wait_ms": queue_wait_ms,
                "processing_time_ms": round((time.perf_counter() - job_timer_start) * 1000, 2),
                "ocr_time_ms": None,
                "segmentation_time_ms": None,
                "extraction_time_ms": None,
                "validation_time_ms": None,
                "pipeline_time_ms": None,
                "word_count": None,
                "ocr_confidence_avg": None,
                "needs_review": None,
                "is_duplicate": False,
                "error_message": str(e),
                "created_at": job_started_at.isoformat(),
            }
        )

        # Still count this job in batch; send one batch completion email when all are done
        _maybe_send_batch_completion(batch_run_id, access_token, upload_batch_id)

        # Re-raise so RQ marks the job as failed (not silently "finished")
        raise
