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
    ocr_provider_name: str = "stub"
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
    
    # Stage 3: Extraction
    contact_fields = extract_fields_rules(contact_block)
    essay_metrics = compute_essay_metrics(essay_block)
    
    structured_data = {
        **contact_fields,
        **essay_metrics
    }
    
    # Write extraction artifacts
    with open(artifact_path / "structured.json", "w", encoding="utf-8") as f:
        json.dump(structured_data, f, indent=2)
    
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

