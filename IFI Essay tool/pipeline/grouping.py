"""
Grouping module: Organizes submission records into School → Grade buckets.
"""

import re
from typing import Dict, List, Any, Optional


def normalize_key(text: Optional[str]) -> str:
    """
    Normalize a key for grouping: trim whitespace, collapse spaces, casefold.
    
    Args:
        text: Original text value
        
    Returns:
        Normalized key for grouping
    """
    if not text:
        return ""
    
    # Convert to string and strip whitespace
    text = str(text).strip()
    
    # Collapse multiple spaces into single space
    text = re.sub(r'\s+', ' ', text)
    
    # Casefold for case-insensitive grouping
    text = text.casefold()
    
    return text


def get_display_value(record: Dict, field: str) -> str:
    """
    Get the original display value from a record.
    
    Args:
        record: Record dictionary
        field: Field name to extract
        
    Returns:
        Original value for display (or empty string)
    """
    value = record.get(field)
    if value is None:
        return ""
    return str(value).strip()


def group_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Group records into:
    - needs_review: List of records that need review
    - schools: Dict of {school_name: {grade: [records]}}
    
    Rules:
    - Records with both school_name and grade AND needs_review == False go into School→Grade buckets
    - Records missing school/grade OR needs_review == True stay in Needs Review
    
    Args:
        records: List of record dictionaries
        
    Returns:
        Dict with structure:
        {
            "needs_review": [...],
            "schools": {
                "School A": {
                    "4": [...],
                    "5": [...]
                },
                "School B": {
                    "6": [...]
                }
            }
        }
    """
    needs_review = []
    schools: Dict[str, Dict[str, List[Dict]]] = {}
    
    for record in records:
        # Check if record belongs in needs_review
        school_name = record.get("school_name")
        grade = record.get("grade")
        needs_review_flag = record.get("needs_review", False)
        
        # Determine if record should be in needs_review
        should_review = (
            needs_review_flag or
            not school_name or
            not grade or
            str(school_name).strip() == "" or
            str(grade).strip() == ""
        )
        
        if should_review:
            needs_review.append(record)
        else:
            # Normalize keys for grouping
            school_key = normalize_key(school_name)
            grade_key = normalize_key(str(grade))
            
            if not school_key or not grade_key:
                # If normalization results in empty, put in needs_review
                needs_review.append(record)
                continue
            
            # Get display values (original)
            display_school = get_display_value(record, "school_name")
            display_grade = get_display_value(record, "grade")
            
            # Initialize school dict if needed
            if display_school not in schools:
                schools[display_school] = {}
            
            # Initialize grade list if needed
            if display_grade not in schools[display_school]:
                schools[display_school][display_grade] = []
            
            # Add record to appropriate bucket
            schools[display_school][display_grade].append(record)
    
    return {
        "needs_review": needs_review,
        "schools": schools
    }


def get_school_grade_records(grouped: Dict[str, Any], school_name: str, grade: str) -> List[Dict]:
    """
    Get records for a specific school and grade from grouped data.
    
    Args:
        grouped: Result from group_records()
        school_name: School name (display value)
        grade: Grade (display value)
        
    Returns:
        List of records for that school/grade combination
    """
    schools = grouped.get("schools", {})
    if school_name not in schools:
        return []
    
    grades = schools[school_name]
    if grade not in grades:
        return []
    
    return grades[grade]


def get_all_school_names(grouped: Dict[str, Any]) -> List[str]:
    """
    Get all school names from grouped data, sorted.
    
    Args:
        grouped: Result from group_records()
        
    Returns:
        Sorted list of school names
    """
    schools = grouped.get("schools", {})
    return sorted(schools.keys())


def get_grades_for_school(grouped: Dict[str, Any], school_name: str) -> List[str]:
    """
    Get all grades for a specific school, sorted.
    
    Args:
        grouped: Result from group_records()
        school_name: School name (display value)
        
    Returns:
        Sorted list of grades for that school
    """
    schools = grouped.get("schools", {})
    if school_name not in schools:
        return []
    
    grades = schools[school_name]
    # Sort grades: numeric first, then text
    def sort_key(g):
        try:
            return (0, int(g))  # Numeric grades
        except (ValueError, TypeError):
            return (1, g.lower())  # Text grades
    
    return sorted(grades.keys(), key=sort_key)

