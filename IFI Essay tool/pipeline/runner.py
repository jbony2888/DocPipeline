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
    artifact_path = Path(artifact_dir)
    processing_report = {"stages": {}}
    
    # Stage 1: OCR
    ocr_provider = get_ocr_provider(ocr_provider_name)
    ocr_result = ocr_provider.process_image(image_path)
    
    # Write OCR artifacts
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
    
    # Write segmentation artifacts
    with open(artifact_path / "contact_block.txt", "w", encoding="utf-8") as f:
        f.write(contact_block)
    
    with open(artifact_path / "essay_block.txt", "w", encoding="utf-8") as f:
        f.write(essay_block)
    
    processing_report["stages"]["segmentation"] = {
        "contact_lines": len(contact_block.split('\n')),
        "essay_lines": len(essay_block.split('\n'))
    }
    
    # Stage 3: Extraction (IFI-specific two-phase extraction)
    from pipeline.extract_ifi import extract_fields_ifi
    import os
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
    essay_metrics = compute_essay_metrics(essay_block)
    
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
    
    return record, processing_report

