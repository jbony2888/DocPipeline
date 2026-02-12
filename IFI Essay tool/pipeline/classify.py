"""
Deterministic document classification for IFI submissions.
Removes LLM authority for classification decisions per DBF.
"""

import re
from typing import Dict, Any, Tuple, Optional


def extract_classification_features(ocr_text: str) -> Dict[str, Any]:
    """
    Extract deterministic features from OCR text for classification.
    
    Args:
        ocr_text: Full OCR text
        
    Returns:
        Dictionary of features
    """
    ocr_lower = ocr_text.lower()
    
    # Check for form labels (English and Spanish)
    form_labels_en = [
        "student's name", "student name", "school", "grade", "grade level",
        "father", "father-figure", "father figure", "essay", "reaction"
    ]
    form_labels_es = [
        "nombre del estudiante", "estudiante", "escuela", "grado",
        "padre", "figura paterna", "ensayo", "reaccion"
    ]
    
    has_form_labels = any(label in ocr_lower for label in form_labels_en + form_labels_es)
    
    # Check for essay prompt markers
    essay_prompt_markers = [
        "what my father", "means to me", "father or", "father-figure",
        "que significa", "mi padre", "figura paterna"
    ]
    has_essay_prompt = any(marker in ocr_lower for marker in essay_prompt_markers)
    
    # Word and line counts
    words = ocr_text.split()
    word_count = len(words)
    lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
    line_count = len(lines)
    
    # Check for blank template indicators
    # Blank templates have form structure but minimal content
    template_blank_score = 0.0
    if has_form_labels:
        # If we have labels but very little content, likely blank
        if word_count < 50:
            template_blank_score = 1.0
        elif word_count < 100:
            template_blank_score = 0.7
        elif word_count < 200:
            template_blank_score = 0.3
    
    # Check for multi-entry indicators
    # Multiple names, multiple "essay" sections, page breaks
    name_patterns = re.findall(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+', ocr_text)
    unique_names = len(set(name_patterns))
    is_multi_entry = unique_names > 3  # More than 3 unique name patterns suggests multiple entries
    
    # Check for header metadata format (name/school/grade on first few lines without labels)
    first_lines = lines[:5] if len(lines) >= 5 else lines
    has_unlabeled_header = False
    if len(first_lines) >= 3:
        # Check if first lines look like name/school/grade without labels
        first_line_has_name = bool(re.search(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+', first_lines[0]))
        has_school_keyword = any(keyword in ' '.join(first_lines[:3]).lower() for keyword in ['school', 'elementary', 'middle', 'high', 'escuela'])
        has_grade_keyword = any(keyword in ' '.join(first_lines[:3]).lower() for keyword in ['grade', 'grado', r'\b\d{1,2}\b'])
        
        if first_line_has_name and (has_school_keyword or has_grade_keyword):
            has_unlabeled_header = True
    
    return {
        "has_form_labels": has_form_labels,
        "has_essay_prompt": has_essay_prompt,
        "word_count": word_count,
        "line_count": line_count,
        "template_blank_score": template_blank_score,
        "is_multi_entry": is_multi_entry,
        "has_unlabeled_header": has_unlabeled_header,
        "unique_name_count": unique_names
    }


def verify_doc_type_signal(
    signal_doc_type: Optional[str],
    features: Dict[str, Any],
    ocr_text: str
) -> Tuple[str, bool, str]:
    """
    Verify LLM-suggested doc_type against deterministic features.
    
    Args:
        signal_doc_type: LLM-suggested doc_type
        features: Extracted features from extract_classification_features
        ocr_text: Full OCR text
        
    Returns:
        Tuple of (doc_type_final, verified: bool, reason: str)
    """
    # If no signal, classify deterministically
    if not signal_doc_type:
        return classify_document_type_deterministic(features, ocr_text), False, "No LLM signal provided"
    
    # Deterministic classification
    deterministic_type = classify_document_type_deterministic(features, ocr_text)
    
    # Verify signal matches deterministic classification
    if signal_doc_type == deterministic_type:
        return deterministic_type, True, "Signal matches deterministic classification"
    
    # Check if signal is plausible given features
    is_plausible = False
    reason = ""
    
    if signal_doc_type == "IFI_OFFICIAL_FORM_FILLED":
        is_plausible = features["has_form_labels"] and features["has_essay_prompt"] and features["word_count"] > 100
        reason = "Signal suggests form but features indicate otherwise" if not is_plausible else "Signal plausible but differs from deterministic"
    
    elif signal_doc_type == "IFI_OFFICIAL_TEMPLATE_BLANK":
        is_plausible = features["has_form_labels"] and features["template_blank_score"] > 0.5
        reason = "Signal suggests blank template but features indicate otherwise" if not is_plausible else "Signal plausible but differs from deterministic"
    
    elif signal_doc_type == "ESSAY_WITH_HEADER_METADATA":
        is_plausible = features["has_unlabeled_header"] and not features["has_form_labels"]
        reason = "Signal suggests header format but features indicate otherwise" if not is_plausible else "Signal plausible but differs from deterministic"
    
    elif signal_doc_type == "ESSAY_ONLY":
        is_plausible = not features["has_form_labels"] and features["word_count"] > 50
        reason = "Signal suggests essay-only but features indicate otherwise" if not is_plausible else "Signal plausible but differs from deterministic"
    
    elif signal_doc_type == "MULTI_ENTRY":
        is_plausible = features["is_multi_entry"]
        reason = "Signal suggests multi-entry but features indicate otherwise" if not is_plausible else "Signal plausible but differs from deterministic"
    
    # If plausible but differs, use deterministic (more conservative)
    if is_plausible:
        return deterministic_type, False, f"Signal plausible but using deterministic: {reason}"
    else:
        # Signal not plausible - use deterministic and flag for review
        return deterministic_type, False, f"Signal not plausible: {reason}"


def classify_document_type_deterministic(features: Dict[str, Any], ocr_text: str) -> str:
    """
    Deterministically classify document type based on features.
    
    Args:
        features: Extracted features
        ocr_text: Full OCR text
        
    Returns:
        Document type string
    """
    # Multi-entry check (highest priority)
    if features["is_multi_entry"]:
        return "MULTI_ENTRY"
    
    # Blank template check
    if features["has_form_labels"] and features["template_blank_score"] > 0.7:
        return "IFI_OFFICIAL_TEMPLATE_BLANK"
    
    # Official form filled
    if features["has_form_labels"] and features["has_essay_prompt"] and features["word_count"] > 100:
        return "IFI_OFFICIAL_FORM_FILLED"
    
    # Essay with header metadata
    if features["has_unlabeled_header"] and not features["has_form_labels"]:
        return "ESSAY_WITH_HEADER_METADATA"
    
    # Essay only
    if not features["has_form_labels"] and features["word_count"] > 50:
        return "ESSAY_ONLY"
    
    # Default: unknown (defer to review)
    return "UNKNOWN"
