# School → Grade Grouping System

## Overview

The grouping system automatically organizes submission records into:
- **Needs Review**: Records missing required fields or flagged for review
- **School → Grade Buckets**: Records organized by school name, then by grade level

## How It Works

### Grouping Rules

1. **Needs Review Group**:
   - Records with `needs_review == True`
   - Records missing `school_name`
   - Records missing `grade`
   - Records with empty `school_name` or `grade` strings

2. **School → Grade Buckets**:
   - Only records with both `school_name` AND `grade` AND `needs_review == False`
   - Grouped by school name (normalized for case-insensitive matching)
   - Then grouped by grade within each school

### Normalization

- **School names** and **grades** are normalized for grouping:
  - Whitespace trimmed
  - Multiple spaces collapsed to single space
  - Case-folded (case-insensitive matching)
- **Display values** preserve original formatting

### Auto-Reassignment

When a record is updated:
1. If `school_name` and `grade` are added to a record that was missing them
2. And the record now has all required fields (`student_name`, `school_name`, `grade`)
3. The record is **automatically approved** (`needs_review = False`)
4. It immediately appears in the correct School → Grade bucket on next page load

## UI Organization

### Needs Review Tab
- Shows flat list of all records needing review
- Each record can be edited and approved individually

### Approved Records Tab
- Shows collapsible sections:
  - **School** (header with export button)
    - **Grade** (subheader with export button)
      - Table of submissions for that grade
- Records are automatically sorted by school name, then by grade

## Export Functionality

### Export All Clean Records
- Route: `/export`
- Exports all approved records to a single CSV
- Includes PDF URLs for essay readers

### Export by School
- Route: `/export/school/<school_name>`
- Exports all records for a specific school
- Includes all grades for that school

### Export by School and Grade
- Route: `/export/school/<school_name>/grade/<grade>`
- Exports records for a specific school and grade combination
- Perfect for creating grade-level batches

## Implementation Details

### Files

- **`pipeline/grouping.py`**: Core grouping logic
  - `group_records()`: Main grouping function
  - `normalize_key()`: Key normalization
  - Helper functions for accessing grouped data

- **`flask_app.py`**: 
  - Updated `/review` route to use grouping
  - Auto-reassignment logic in record update handler
  - Export routes for school/grade batches

- **`templates/review.html`**: 
  - Shows grouped view for approved records
  - Shows flat list for needs review

### Grouping Function

```python
grouped = group_records(records)
# Returns:
{
    "needs_review": [...],  # List of records needing review
    "schools": {
        "School A": {
            "5": [...],  # List of records for Grade 5
            "6": [...]   # List of records for Grade 6
        },
        "School B": {
            "4": [...]
        }
    }
}
```

## Testing

Run unit tests:
```bash
python -m pytest tests/test_grouping.py
```

Or:
```bash
python tests/test_grouping.py
```

## Manual Test Plan

1. **Upload mixed batch**:
   - Upload files with different schools and grades
   - Some with missing school/grade fields
   - Verify they appear in correct groups

2. **Edit and auto-reassign**:
   - Edit a record in "Needs Review" that's missing school
   - Add school name and grade
   - Verify it automatically moves to the correct School → Grade bucket

3. **Export batches**:
   - Export all records
   - Export by school
   - Export by school and grade
   - Verify CSV includes PDF URLs

4. **Case insensitivity**:
   - Upload records with "School A" and "SCHOOL A"
   - Verify they're grouped together

## Benefits

- ✅ **Automatic Organization**: No manual sorting needed
- ✅ **Auto-Reassignment**: Records move to correct bucket when fields are added
- ✅ **Flexible Export**: Export by school, grade, or all records
- ✅ **Case-Insensitive**: Handles variations in school name capitalization
- ✅ **Computed at Read-Time**: No need for separate batch tables



