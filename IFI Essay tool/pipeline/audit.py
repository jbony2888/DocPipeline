"""
DBF-compliant audit trail builder.
Constructs structured traces: Input → Signal → Rule → Outcome
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


def build_decision_trace(
    submission_id: str,
    filename: str,
    owner_user_id: Optional[str],
    ocr_result: Optional[Dict[str, Any]] = None,
    extracted_fields: Optional[Dict[str, Any]] = None,
    validation_result: Optional[Dict[str, Any]] = None,
    llm_result: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
    doc_type_final: Optional[str] = None,
    doc_type_signal: Optional[str] = None,
    rules_applied: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Build a structured decision trace following DBF Input → Signal → Rule → Outcome pattern.
    
    Args:
        submission_id: Unique submission identifier
        filename: Original filename
        owner_user_id: User who uploaded
        ocr_result: OCR output with confidence
        extracted_fields: Extracted structured fields
        validation_result: Validation report
        llm_result: LLM extraction result (if used)
        errors: List of errors encountered
        doc_type_final: Final deterministic doc_type
        doc_type_signal: LLM-suggested doc_type (before verification)
        rules_applied: List of rules evaluated
        
    Returns:
        Dictionary with input, signals, rules_applied, outcome, errors
    """
    # Build input section
    input_section = {
        "submission_id": submission_id,
        "filename": filename,
        "owner_user_id": owner_user_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Build signals section
    signals_section = {}
    
    if ocr_result:
        signals_section["ocr"] = {
            "confidence_avg": ocr_result.get("confidence_avg"),
            "text_length": len(ocr_result.get("text", "")),
            "line_count": len(ocr_result.get("lines", []))
        }
    
    if llm_result:
        signals_section["llm"] = {
            "doc_type_signal": doc_type_signal,
            "model": llm_result.get("model"),
            "extraction_method": llm_result.get("extraction_method"),
            "fields_extracted_count": sum(1 for k, v in extracted_fields.items() if v is not None and not k.startswith("_")) if extracted_fields else 0
        }
    
    if extracted_fields:
        signals_section["extracted_fields"] = {
            "student_name": extracted_fields.get("student_name") is not None,
            "school_name": extracted_fields.get("school_name") is not None,
            "grade": extracted_fields.get("grade") is not None,
            "father_figure_name": extracted_fields.get("father_figure_name") is not None,
            "phone": extracted_fields.get("phone") is not None,
            "email": extracted_fields.get("email") is not None
        }
    
    # Build rules_applied section
    if rules_applied is None:
        rules_applied = []
    
    # Add default rules if validation_result provided
    if validation_result:
        # OCR confidence rule
        ocr_conf = signals_section.get("ocr", {}).get("confidence_avg")
        if ocr_conf is not None:
            rules_applied.append({
                "rule_id": "ocr_confidence_threshold",
                "description": "OCR confidence must be >= 0.5",
                "params": {"threshold": 0.5},
                "evaluated": ocr_conf,
                "result": ocr_conf >= 0.5,
                "triggered": ocr_conf < 0.5
            })
        
        # Required fields rules
        if not extracted_fields or not extracted_fields.get("student_name"):
            rules_applied.append({
                "rule_id": "required_student_name",
                "description": "student_name is required",
                "params": {},
                "evaluated": extracted_fields.get("student_name") if extracted_fields else None,
                "result": False,
                "triggered": True
            })
        
        if not extracted_fields or not extracted_fields.get("school_name"):
            rules_applied.append({
                "rule_id": "required_school_name",
                "description": "school_name is required",
                "params": {},
                "evaluated": extracted_fields.get("school_name") if extracted_fields else None,
                "result": False,
                "triggered": True
            })
        
        if not extracted_fields or not extracted_fields.get("grade"):
            rules_applied.append({
                "rule_id": "required_grade",
                "description": "grade is required",
                "params": {},
                "evaluated": extracted_fields.get("grade") if extracted_fields else None,
                "result": False,
                "triggered": True
            })
        
        # Essay word count rule
        word_count = validation_result.get("word_count", 0) if isinstance(validation_result, dict) else 0
        if word_count == 0:
            rules_applied.append({
                "rule_id": "essay_not_empty",
                "description": "Essay must have word_count > 0",
                "params": {},
                "evaluated": word_count,
                "result": False,
                "triggered": True
            })
        elif word_count < 50:
            rules_applied.append({
                "rule_id": "essay_minimum_length",
                "description": "Essay must have >= 50 words",
                "params": {"minimum": 50},
                "evaluated": word_count,
                "result": False,
                "triggered": True
            })
    
    # Build outcome section
    outcome_section = {
        "needs_review": validation_result.get("needs_review", True) if validation_result else True,
        "review_reason_codes": validation_result.get("review_reason_codes", "PENDING_REVIEW") if validation_result else "PENDING_REVIEW",
        "doc_type_final": doc_type_final,
        "status": "PENDING_REVIEW"  # Default status
    }
    
    if validation_result:
        if isinstance(validation_result, dict):
            outcome_section.update({
                "needs_review": validation_result.get("needs_review", True),
                "review_reason_codes": validation_result.get("review_reason_codes", "PENDING_REVIEW")
            })
    
    # Determine status
    if errors and len(errors) > 0:
        outcome_section["status"] = "FAILED"
    elif outcome_section["needs_review"]:
        outcome_section["status"] = "PENDING_REVIEW"
    else:
        outcome_section["status"] = "PROCESSED"
    
    # Build errors section
    errors_section = errors or []
    
    return {
        "trace_version": "dbf-audit-v1",
        "input": input_section,
        "signals": signals_section,
        "rules_applied": rules_applied,
        "outcome": outcome_section,
        "errors": errors_section
    }


def write_artifact_json(trace_dict: Dict[str, Any], artifact_path: str) -> None:
    """
    Write decision_log.json to artifact directory (for debugging).
    Supabase is the source of truth; this is just for local inspection.
    
    Args:
        trace_dict: Decision trace dictionary
        artifact_path: Path to artifact directory
    """
    import json
    from pathlib import Path
    
    try:
        artifact_dir = Path(artifact_path)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        log_path = artifact_dir / "decision_log.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(trace_dict, f, indent=2)
    except Exception as e:
        # Don't fail on artifact write - Supabase is source of truth
        print(f"⚠️ Warning: Could not write decision_log.json: {e}")
