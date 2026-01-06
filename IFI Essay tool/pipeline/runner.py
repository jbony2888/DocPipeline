"""
Pipeline runner: orchestrates the full processing pipeline.
Runs OCR → segmentation → extraction → validation and writes artifacts.
"""

import json
from pathlib import Path
from typing import Tuple

from pipeline.schema import SubmissionRecord
from pipeline.ocr import get_ocr_provider
from pipeline.segment import split_contact_vs_essay
from pipeline.extract import extract_fields_rules, compute_essay_metrics
from pipeline.validate import validate_record
import logging

logger = logging.getLogger(__name__)


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
    original_filename: str = None
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
        # Stage 1: OCR
        ocr_provider = get_ocr_provider(ocr_provider_name)
        ocr_result = ocr_provider.process_image(image_path)
        
        # Write OCR artifacts to temp directory
        with open(artifact_path / "ocr.json", "w", encoding="utf-8") as f:
            json.dump(ocr_result.model_dump(), f, indent=2)
        
        with open(artifact_path / "raw_text.txt", "w", encoding="utf-8") as f:
            f.write(ocr_result.text)
        
        processing_report["stages"]["ocr"] = {
            "confidence_avg": ocr_result.confidence_avg,
            "line_count": len(ocr_result.lines)
        }
        
        # Stage 2: Segmentation
        contact_block, essay_block = split_contact_vs_essay(ocr_result.text)
        
        # Write segmentation artifacts (initial segmentation)
        with open(artifact_path / "contact_block.txt", "w", encoding="utf-8") as f:
            f.write(contact_block)
        
        # Stage 3: Extraction (IFI-specific two-phase extraction)
        from pipeline.extract_ifi import extract_fields_ifi
        contact_fields = extract_fields_ifi(contact_block, ocr_result.text, original_filename)
        
        # Determine which model was used
        if os.environ.get("OPENAI_API_KEY"):
            model_used = "gpt-4o-mini (OpenAI)"
        elif os.environ.get("GROQ_API_KEY"):
            model_used = "mixtral-8x7b-32768 (Groq)"
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
            "result": {k: v for k, v in contact_fields.items() if k != "_ifi_metadata"}
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
        
        # Stage 4: Validation
        partial_record = {
            "submission_id": submission_id,
            "artifact_dir": artifact_dir,
            **contact_fields,
            "word_count": essay_metrics["word_count"],
            "ocr_confidence_avg": ocr_result.confidence_avg
        }
        
        record, validation_report = validate_record(partial_record)
        
        # Write validation artifacts
        with open(artifact_path / "validation.json", "w", encoding="utf-8") as f:
            json.dump(validation_report, f, indent=2)
    
        processing_report["stages"]["validation"] = validation_report
        processing_report["needs_review"] = record.needs_review
        
    finally:
        # Clean up temporary directory (artifacts are stored in Supabase Storage, not needed locally)
        try:
            import shutil
            shutil.rmtree(temp_artifact_dir)
        except Exception as e:
            logger.warning(f"Could not clean up temp directory {temp_artifact_dir}: {e}")
    
    return record, processing_report

