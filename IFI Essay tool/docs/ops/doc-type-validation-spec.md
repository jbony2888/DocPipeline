# Doc-type validation spec

## Objective

Ensure all IFI essay contest submissions have the essential data. Every document type requires essay, grade, school, and student name. Missing any required field flags the document for human review. Use a config-driven validation matrix so rules can be extended without core rewrites.

## Technical scope

### Validation matrix (all fields required for all doc types)

| Doc Class         | Essay | Grade | School | Student Name |
|-------------------|-------|-------|--------|--------------|
| SINGLE_TYPED      | ✅    | ✅    | ✅     | ✅           |
| SINGLE_SCANNED    | ✅    | ✅    | ✅     | ✅           |
| MULTI_PAGE_SINGLE | ✅    | ✅    | ✅     | ✅           |
| BULK_SCANNED_BATCH| ✅    | ✅    | ✅     | ✅           |

**Behavior:**

- Missing any required field → flag for human review (`needs_review=True`, add appropriate issue codes: `MISSING_GRADE`, `MISSING_SCHOOL_NAME`, `MISSING_STUDENT_NAME`, `EMPTY_ESSAY`, `SHORT_ESSAY`).
- No doc type is exempt; all fields are essential for the contest.

### Config layer

- **Location:** `pipeline/validation_config.py`
- **Structure:** `VALIDATION_RULES[DocClass]` defines which fields are required per doc type.
- **Usage:** `validate_record()` and `can_approve_record()` look up rules by `doc_class`; core validation logic is driven by config, not hardcoded rules.

### Adding a new doc type

1. Add a new `DocClass` enum value in `pipeline/schema.py`.
2. Add a corresponding entry in `VALIDATION_RULES` in `pipeline/validation_config.py`.
3. No changes to `pipeline/validate.py` core logic.

## Acceptance criteria

- [x] All doc types require essay, grade, school, and student name.
- [x] Missing any required field flags the record for human review.
- [x] Validation is config-driven; no hardcoded rules per doc type in core logic.

## Definition of done

- [x] Config-driven rule system is in place (`validation_config.py`).
- [x] Adding a new doc type requires no core rewrite.
- [x] All existing doc types use the same strict rules (all fields required).

## Risk notes

- **Misconfigured rules** could relax validation; config changes require clear ownership and review.
- **Strict rules for all types** means more forms may be flagged for review when grade/school are missing or illegible (by design).
