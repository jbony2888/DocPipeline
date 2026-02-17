"""
Config-driven validation rules per DocClass.

All document types require essay, grade, school, and student_name for the IFI essay contest.
Missing any required field flags the record for human review.

Adding a new DocClass: extend VALIDATION_RULES with appropriate rule set.
Adding a new field rule: extend ValidationRules and update validate.py to honor it.
"""

from dataclasses import dataclass
from typing import Dict

from pipeline.schema import DocClass


@dataclass(frozen=True)
class ValidationRules:
    """Required-field rules for a document type."""

    require_student_name: bool = True
    require_school: bool = True
    require_grade: bool = True
    require_essay: bool = True  # word_count > 0 (and >= 50 for non-flag)


# All doc types use strict rules: essay, grade, school, student_name all required.
# Documents missing any required field are flagged for human review.
VALIDATION_RULES: Dict[DocClass, ValidationRules] = {
    DocClass.SINGLE_TYPED: ValidationRules(
        require_student_name=True,
        require_school=True,
        require_grade=True,
        require_essay=True,
    ),
    DocClass.SINGLE_SCANNED: ValidationRules(
        require_student_name=True,
        require_school=True,
        require_grade=True,
        require_essay=True,
    ),
    DocClass.MULTI_PAGE_SINGLE: ValidationRules(
        require_student_name=True,
        require_school=True,
        require_grade=True,
        require_essay=True,
    ),
    DocClass.BULK_SCANNED_BATCH: ValidationRules(
        require_student_name=True,
        require_school=True,
        require_grade=True,
        require_essay=True,
    ),
}


def get_validation_rules(doc_class: DocClass) -> ValidationRules:
    """Return validation rules for the given DocClass. Uses SINGLE_TYPED as fallback."""
    return VALIDATION_RULES.get(doc_class, VALIDATION_RULES[DocClass.SINGLE_TYPED])
