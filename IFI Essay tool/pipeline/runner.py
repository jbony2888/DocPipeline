"""
Pipeline runner: orchestrates the full processing pipeline.
Runs OCR → segmentation → extraction → validation and writes artifacts.
"""

import json
import re
from pathlib import Path
from typing import Tuple

from pipeline.schema import SubmissionRecord
from pipeline.ocr import get_ocr_provider, ocr_pdf_pages, get_ocr_result_from_pdf_text_layer, extract_pdf_text_layer
from pipeline.segment import split_contact_vs_essay
from pipeline.extract import extract_fields_rules, compute_essay_metrics
from pipeline.validate import validate_record, _is_effectively_missing_student_name, _is_effectively_missing_school_name
from pipeline.normalize import normalize_grade, normalize_school_name, sanitize_grade
from pipeline.doc_type_routing import detect_pdf_has_acroform_fields, route_doc_type
import logging

logger = logging.getLogger(__name__)


def _extract_typed_form_acroform_fields(form_field_values: dict | None) -> dict:
    """
    Extract student/school/grade from AcroForm fields only.
    """
    values = form_field_values or {}
    out = {"student_name": None, "school_name": None, "grade": None}
    for key, raw in values.items():
        if raw is None:
            continue
        value = str(raw).strip()
        if not value:
            continue
        k = str(key).strip().lower()
        if ("student" in k or "estudiante" in k) and "dad" not in k and "father" not in k:
            out["student_name"] = value
        elif "school" in k or "escuela" in k:
            out["school_name"] = value
        elif k in ("grade", "grado") or "grade" in k or "grado" in k:
            out["grade"] = value
    return out


def _extract_header_fields_from_text(text: str) -> dict:
    """Extract student/school/grade from header-like OCR text."""
    txt = text or ""
    patterns = {
        "student_name": [
            r"(?im)\b(?:student(?:'s)?\s*name|nombre(?:\s+del)?\s+estudiante)\s*[:\-]?\s*([^\n\r]{2,80})",
        ],
        "school_name": [
            r"(?im)\b(?:school(?:\s+name)?|escuela|campus)\s*[:\-]?\s*([^\n\r]{2,120})",
        ],
        "grade": [
            r"(?im)\b(?:grade\s*/\s*grado|grado\s*/\s*grade|grade|grado)\s*[:\-]?\s*(pre[\s\-]?k|k|[0-9]{1,2})\b",
            r"(?im)\b(?:grade|grado)\s*[:\-]?\s*(pre[\s\-]?k|k|[0-9]{1,2})\b",
        ],
    }

    extracted = {"student_name": None, "school_name": None, "grade": None}
    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, txt)
            if not match:
                continue
            value = re.sub(r"\s+", " ", (match.group(1) or "")).strip(" .,:;-\t")
            extracted[field] = value or None
            if extracted[field]:
                break
    return extracted


def _get_best_essay_text(essay_block: str, llm_essay_text: str = None, raw_text: str = None) -> tuple[str, str]:
    """
    Get the best available essay text from multiple sources.
    
    Priority order:
    1. LLM-extracted essay_text (if segmentation failed and LLM found substantial text)
    2. Segmented essay_block (if it has substantial content)
    3. Raw text fallback (last resort)
    
    Args:
        essay_block: Text from segmentation
        llm_essay_text: Essay text extracted by LLM (from _ifi_metadata)
        raw_text: Full OCR text (fallback only)
        
    Returns:
        Tuple of (best_essay_text, source_name)
    """
    # Count words in each source
    essay_block_words = len(essay_block.split()) if essay_block else 0
    llm_words = len(llm_essay_text.split()) if llm_essay_text else 0
    
    # If segmentation found substantial text (> 50 words), use it
    if essay_block_words > 50:
        return essay_block, "segmentation"
    
    # If LLM extracted substantial essay text (> 50 words), use it as fallback
    if llm_essay_text and llm_words > 50:
        logger.info(f"Using LLM-extracted essay_text as fallback (segmentation found only {essay_block_words} words, LLM found {llm_words})")
        return llm_essay_text, "llm_extraction"
    
    # If segmentation found some text (even if < 50 words), use it
    if essay_block_words > 0:
        return essay_block, "segmentation"
    
    # If LLM found some text, use it
    if llm_essay_text and llm_words > 0:
        logger.info(f"Using LLM-extracted essay_text (segmentation found 0 words, LLM found {llm_words})")
        return llm_essay_text, "llm_extraction"
    
    # Last resort: return segmented block (will be empty, but preserves original behavior)
    return essay_block, "segmentation"


def process_submission(
    image_path: str,
    submission_id: str,
    artifact_dir: str,
    ocr_provider_name: str = "stub",
    original_filename: str = None,
    chunk_metadata: dict | None = None,
    doc_format: str | None = None,
) -> Tuple[SubmissionRecord, dict]:
    """
    Runs the complete processing pipeline for a single submission.
    
    Pipeline stages:
        1. OCR: Extract text from image
        2. Segmentation: Split contact vs essay
        3. Extraction: Parse structured fields and compute metrics
        4. Validation: Check required fields and flag issues
    
    Writes artifacts at each stage:
        - ocr.json: Raw OCR output
        - raw_text.txt: Full OCR text
        - contact_block.txt: Extracted contact section
        - essay_block.txt: Extracted essay content
        - structured.json: Extracted fields and metrics
        - validation.json: Validation report
    
    Args:
        image_path: Path to uploaded image
        submission_id: Unique submission identifier
        artifact_dir: Directory to write artifacts
        ocr_provider_name: OCR provider to use
        
    Returns:
        Tuple of (SubmissionRecord, processing_report dict)
    """
    # Create temporary local directory for processing artifacts
    # artifact_dir is now a Supabase Storage path, so we use a temp dir for processing
    import tempfile
    import os
    temp_artifact_dir = tempfile.mkdtemp(prefix=f"essay_{submission_id}_")
    artifact_path = Path(temp_artifact_dir)
    
    processing_report = {"stages": {}}
    
    try:
        # Stage 1: OCR (or text-layer extraction for typed PDFs)
        ocr_provider = get_ocr_provider(ocr_provider_name)
        if str(image_path).lower().endswith(".pdf"):
            ocr_result = get_ocr_result_from_pdf_text_layer(image_path)
            if ocr_result is not None:
                logger.info(f"Using PDF text layer for {submission_id} (no OCR)")
        else:
            ocr_result = None
        if ocr_result is None:
            ocr_result = ocr_provider.process_image(image_path)
        
        # Write OCR artifacts to temp directory
        with open(artifact_path / "ocr.json", "w", encoding="utf-8") as f:
            json.dump(ocr_result.model_dump(), f, indent=2)
        
        with open(artifact_path / "raw_text.txt", "w", encoding="utf-8") as f:
            f.write(ocr_result.text)
        
        processing_report["stages"]["ocr"] = {
            "confidence_avg": ocr_result.confidence_avg,
            "confidence_min": ocr_result.confidence_min,
            "confidence_p10": ocr_result.confidence_p10,
            "low_conf_page_count": ocr_result.low_conf_page_count,
            "line_count": len(ocr_result.lines)
        }
        processing_report["ocr_summary"] = {
            "confidence_avg": ocr_result.confidence_avg,
            "confidence_min": ocr_result.confidence_min,
            "confidence_p10": ocr_result.confidence_p10,
            "low_conf_page_count": ocr_result.low_conf_page_count,
            "char_count": len(ocr_result.text or ""),
        }
        
        # Stage 2: Segmentation
        contact_block, essay_block = split_contact_vs_essay(ocr_result.text)
        
        # Write segmentation artifacts (initial segmentation)
        with open(artifact_path / "contact_block.txt", "w", encoding="utf-8") as f:
            f.write(contact_block)
        
        # Stage 3: Extraction (IFI-specific two-phase extraction)
        from pipeline.extract_ifi import extract_fields_ifi
        form_field_values = getattr(ocr_result, "form_field_values", None)
        contact_fields = extract_fields_ifi(
            contact_block, ocr_result.text, original_filename,
            form_field_values=form_field_values,
            doc_format=doc_format,
        )

        chunk_meta = chunk_metadata or {}
        field_attribution = {
            "chunk_scoped_enforced": False,
            "chunk_start_page": chunk_meta.get("chunk_page_start"),
            "field_source_pages": {"student_name": None, "school_name": None, "grade": None},
            "attribution_risk_fields": [],
        }

        ifi_meta = contact_fields.get("_ifi_metadata", {})
        analysis_for_routing = {
            "format": doc_format,
            "structure": chunk_meta.get("analysis_structure"),
            "form_layout": chunk_meta.get("analysis_form_layout"),
            "header_signature_score": chunk_meta.get("analysis_header_signature_score_max"),
        }
        has_acroform = bool(str(image_path).lower().endswith(".pdf")) and detect_pdf_has_acroform_fields(str(image_path))
        routed_doc_type = route_doc_type(
            analysis_for_routing,
            ocr_result.text,
            has_acroform=has_acroform,
        )
        if routed_doc_type == "ifi_typed_form_submission" and has_acroform:
            acroform_fields = _extract_typed_form_acroform_fields(form_field_values)
            # Typed forms must source metadata from form fields only.
            contact_fields["student_name"] = acroform_fields.get("student_name")
            contact_fields["school_name"] = acroform_fields.get("school_name")
            contact_fields["grade"] = acroform_fields.get("grade")

        is_typed_form = ifi_meta.get("extraction_method") == "typed_form_rule_based"
        # 0-based: end=1, start=0 means 2 pages; end-start>=1 = multi-page
        chunk_start = chunk_meta.get("chunk_page_start")
        chunk_end = chunk_meta.get("chunk_page_end")
        chunk_span = (chunk_end if chunk_end is not None else 0) - (chunk_start if chunk_start is not None else 0)
        multi_page_typed = is_typed_form and chunk_span >= 1 and str(image_path).lower().endswith(".pdf")

        # For multi-page typed forms (e.g. 26-IFI: page 1 = essay details, page 2 = contest),
        # re-run header extraction on page-1 text only so grade/name/school come from essay page.
        if multi_page_typed and not (routed_doc_type == "ifi_typed_form_submission" and has_acroform):
            try:
                per_page_stats, _ = extract_pdf_text_layer(
                    image_path, pages=None, mode="full", include_text=True
                )
                if per_page_stats:
                    per_page_sorted = sorted(per_page_stats, key=lambda r: int(r.get("page_index", 0)))
                    page0_text = (per_page_sorted[0].get("text") or "").strip()
                    if page0_text:
                        absolute_start = chunk_meta.get("chunk_page_start")
                        if absolute_start is None:
                            absolute_start = 0
                        p0_contact, _ = split_contact_vs_essay(page0_text)
                        page0_fields = extract_fields_ifi(
                            p0_contact, page0_text, original_filename,
                            form_field_values=getattr(ocr_result, "form_field_values", None),
                            doc_format=doc_format,
                        )
                        for key in ("student_name", "school_name", "grade"):
                            if page0_fields.get(key) is not None:
                                contact_fields[key] = page0_fields[key]
                                field_attribution["field_source_pages"][key] = absolute_start
                        # Fallback: if grade/name/school still missing, use header regex on page-0 text
                        start_fields = _extract_header_fields_from_text(page0_text)
                        for key in ("student_name", "school_name", "grade"):
                            if start_fields.get(key) is not None and contact_fields.get(key) is None:
                                contact_fields[key] = start_fields[key]
                                field_attribution["field_source_pages"][key] = absolute_start
                        field_attribution["chunk_scoped_enforced"] = True
            except Exception as exc:
                logger.warning(f"Multi-page typed page-1 extraction failed for {submission_id}: {exc}")

        # Guardrail: for chunked PDFs (non-typed), source student/school/grade from the chunk start page only.
        # Typed multi-page is handled above with page-1-only extraction.
        if chunk_meta.get("is_chunk") and str(image_path).lower().endswith(".pdf") and not is_typed_form:
            try:
                # Prefer text layer for typed PDFs (no OCR)
                per_page_stats, _ = extract_pdf_text_layer(
                    image_path, pages=None, mode="full", include_text=True
                )
                if not per_page_stats or not (per_page_stats[0].get("text") or "").strip():
                    per_page_stats, _ = ocr_pdf_pages(
                        image_path,
                        pages=None,
                        mode="full",
                        provider_name=ocr_provider_name,
                        provider=ocr_provider,
                        include_text=True,
                    )
                per_page_stats_sorted = sorted(per_page_stats, key=lambda r: int(r.get("page_index", 0)))
                start_page_text = (per_page_stats_sorted[0].get("text") or "") if per_page_stats_sorted else ""
                start_fields = _extract_header_fields_from_text(start_page_text)
                absolute_start_page = chunk_meta.get("chunk_page_start")
                if absolute_start_page is None:
                    absolute_start_page = 0

                found_on_non_start = {"student_name": False, "school_name": False, "grade": False}
                for page in per_page_stats_sorted[1:]:
                    page_fields = _extract_header_fields_from_text(page.get("text") or "")
                    for key in ("student_name", "school_name", "grade"):
                        if page_fields.get(key):
                            found_on_non_start[key] = True

                for key in ("student_name", "school_name", "grade"):
                    if start_fields.get(key):
                        contact_fields[key] = start_fields[key]
                        field_attribution["field_source_pages"][key] = absolute_start_page
                    else:
                        if not multi_page_typed:
                            contact_fields[key] = None
                        if found_on_non_start[key]:
                            field_attribution["attribution_risk_fields"].append(key)

                field_attribution["chunk_scoped_enforced"] = True
            except Exception as exc:
                logger.warning(f"Chunk attribution guardrail failed for {submission_id}: {exc}")

        # Deterministic normalization
        grade_raw = contact_fields.get("grade")
        grade_norm, grade_norm_reason = normalize_grade(grade_raw)
        school_raw = contact_fields.get("school_name")
        school_norm, school_key = normalize_school_name(school_raw)
        contact_fields["grade_raw"] = grade_raw
        contact_fields["grade_normalized"] = grade_norm
        contact_fields["grade_norm_reason"] = grade_norm_reason
        contact_fields["school_raw"] = school_raw
        contact_fields["school_normalized"] = school_norm
        contact_fields["school_canonical_key"] = school_key
        # Use cleaned school in structured output; null when confidence too low (< 3 chars)
        contact_fields["school_name"] = school_norm
        
        # Determine which model was used (Groq for normalization; OpenAI not used)
        if os.environ.get("GROQ_API_KEY"):
            model_used = "llama-3.3-70b-versatile (Groq)"
        else:
            model_used = "none (no API key)"
        
        # Create debug info (include IFI classification if available)
        ifi_metadata = contact_fields.get("_ifi_metadata", {})
        
        extraction_debug = {
            "extraction_method": ifi_metadata.get("extraction_method", "llm"),
            "model": ifi_metadata.get("model", model_used),
            "fields_extracted": sum(1 for k, v in contact_fields.items() if v is not None and k != "_ifi_metadata"),
            "required_fields_found": {
                "student_name": contact_fields.get("student_name") is not None,
                "school_name": contact_fields.get("school_name") is not None,
                "grade": contact_fields.get("grade") is not None
            },
            "result": {k: v for k, v in contact_fields.items() if k != "_ifi_metadata"},
            "normalization": {
                "grade_raw": grade_raw,
                "grade_normalized": grade_norm,
                "grade_norm_reason": grade_norm_reason,
                "school_raw": school_raw,
                "school_normalized": school_norm,
                "school_canonical_key": school_key,
            }
        }
        
        # Add IFI-specific classification info if available
        if ifi_metadata:
            extraction_debug["ifi_classification"] = {
                "doc_type": ifi_metadata.get("doc_type"),
                "is_blank_template": ifi_metadata.get("is_blank_template"),
                "language": ifi_metadata.get("language"),
                "topic": ifi_metadata.get("topic"),
                "is_off_prompt": ifi_metadata.get("is_off_prompt"),
                "notes": ifi_metadata.get("notes", [])
            }
        # Doc class (for review / improving the system)
        dc = chunk_meta.get("doc_class") if chunk_meta else None
        extraction_debug["doc_class"] = dc.value if dc and hasattr(dc, "value") else (str(dc) if dc else None)

        # Priority 1 Fix: Use best available essay text source
        # If segmentation failed (essay_block too short), try LLM-extracted essay_text as fallback
        final_essay_text, essay_source = _get_best_essay_text(
            essay_block, 
            ifi_metadata.get("essay_text") if ifi_metadata else None,
            ocr_result.text
        )
        
        # Write final essay_block.txt (may be improved from LLM extraction)
        with open(artifact_path / "essay_block.txt", "w", encoding="utf-8") as f:
            f.write(final_essay_text)
        
        processing_report["stages"]["segmentation"] = {
            "contact_lines": len(contact_block.split('\n')),
            "essay_lines": len(final_essay_text.split('\n')),
            "essay_source": essay_source,
            "initial_essay_words": len(essay_block.split()),
            "final_essay_words": len(final_essay_text.split())
        }
        
        essay_metrics = compute_essay_metrics(final_essay_text)
        essay_metrics["essay_source"] = essay_source  # Track which source was used for debugging
        # Canonical validation text is the full OCR/text-layer aggregation.
        canonical_validation_text = ocr_result.text or final_essay_text or ""
        canonical_validation_word_count = compute_essay_metrics(canonical_validation_text)["word_count"]
        canonical_validation_char_count = len(canonical_validation_text)

        structured_data = {
            **contact_fields,
            **essay_metrics
        }
        
        # Write extraction artifacts
        with open(artifact_path / "structured.json", "w", encoding="utf-8") as f:
            json.dump(structured_data, f, indent=2)
        
        # Write extraction debug report
        with open(artifact_path / "extraction_debug.json", "w", encoding="utf-8") as f:
            json.dump(extraction_debug, f, indent=2)
        
        processing_report["stages"]["extraction"] = {
            "fields_extracted": sum(1 for v in contact_fields.values() if v is not None),
            "word_count": essay_metrics["word_count"]
        }
        processing_report["extraction_debug"] = extraction_debug  # For review: doc_class, extraction method, normalization
        processing_report["doc_type"] = routed_doc_type
        processing_report["normalization"] = {
            "grade_raw": grade_raw,
            "grade_normalized": grade_norm,
            "grade_norm_reason": grade_norm_reason,
            "school_raw": school_raw,
            "school_normalized": school_norm,
            "school_canonical_key": school_key,
        }
        
        # Stage 4: Validation
        # Choose grade to store (prefer normalized). Reject out-of-range (e.g. 40, 0, 13).
        grade_for_record = grade_norm if grade_norm is not None else sanitize_grade(grade_raw)
        school_for_record = school_norm  # cleaned only; null when sanitize rejected (e.g. < 3 chars)
        # Never pass label/sentinel strings into the record (pipeline stays clean)
        if school_for_record and _is_effectively_missing_school_name(school_for_record):
            school_for_record = None

        if contact_fields.get("student_name") and _is_effectively_missing_student_name(contact_fields["student_name"]):
            contact_fields = {**contact_fields, "student_name": None}
        if contact_fields.get("school_name") and _is_effectively_missing_school_name(contact_fields["school_name"]):
            contact_fields = {**contact_fields, "school_name": None}

        partial_record = {
            "submission_id": submission_id,
            "artifact_dir": artifact_dir,
            **contact_fields,
            "grade": grade_for_record,
            "school_name": school_for_record,
            "word_count": canonical_validation_word_count,
            "final_text_char_count": canonical_validation_char_count,
            "ocr_confidence_avg": ocr_result.confidence_avg,
            "ocr_confidence_min": ocr_result.confidence_min,
            "ocr_confidence_p10": ocr_result.confidence_p10,
            "ocr_low_conf_page_count": ocr_result.low_conf_page_count,
            "ocr_provider": ocr_provider_name,
            "format": doc_format,
            "parent_submission_id": chunk_meta.get("parent_submission_id"),
            "chunk_index": chunk_meta.get("chunk_index"),
            "chunk_page_start": chunk_meta.get("chunk_page_start"),
            "chunk_page_end": chunk_meta.get("chunk_page_end"),
            "is_chunk": chunk_meta.get("is_chunk", False),
            "template_detected": chunk_meta.get("template_detected", False),
            "template_blocked_low_confidence": chunk_meta.get("template_blocked_low_confidence", False),
            "field_attribution_risk": bool(field_attribution["attribution_risk_fields"]),
            "doc_class": chunk_meta.get("doc_class"),
            "doc_type": routed_doc_type,
            "is_container_parent": bool(chunk_meta.get("is_container_parent", False)),
            "extraction_method": ifi_metadata.get("extraction_method"),
            "parse_model": ifi_metadata.get("model"),
        }

        record, validation_report = validate_record(
            partial_record,
            {
                "extraction_debug": extraction_debug,
                "ocr_summary": processing_report.get("ocr_summary"),
            },
        )
        
        # Write validation artifacts
        with open(artifact_path / "validation.json", "w", encoding="utf-8") as f:
            json.dump(validation_report, f, indent=2)
    
        processing_report["stages"]["validation"] = validation_report
        processing_report["needs_review"] = record.needs_review
        processing_report["chunk_metadata"] = chunk_meta
        processing_report["field_attribution"] = field_attribution
        processing_report["extracted_fields"] = {
            "student_name": record.student_name,
            "school_name": record.school_name,
            "grade": record.grade,
        }
    
    finally:
        # Clean up temporary directory (artifacts are stored in Supabase Storage, not needed locally)
        try:
            import shutil
            shutil.rmtree(temp_artifact_dir)
        except Exception as e:
            logger.warning(f"Could not clean up temp directory {temp_artifact_dir}: {e}")
    
    return record, processing_report
