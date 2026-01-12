# Grade Field Migration Guide

## Overview

The `grade` field has been updated to support both numeric values (1-12) and text values (Kindergarten, K, Pre-K, etc.).

## Database Migration

Run this SQL in your Supabase SQL Editor:

```sql
-- Update grade column to TEXT to support both integers and text
ALTER TABLE submissions 
ALTER COLUMN grade TYPE TEXT USING 
  CASE 
    WHEN grade IS NULL THEN NULL
    ELSE grade::text
  END;

-- Add a comment explaining the format
COMMENT ON COLUMN submissions.grade IS 'Grade level: integer (1-12) or text (K, Kindergarten, Pre-K, etc.)';
```

## Supported Grade Formats

The system now accepts:
- **Integers**: 1, 2, 3, ..., 12
- **Kindergarten variants**: "K", "Kinder", "Kindergarten"
- **Pre-K variants**: "Pre-K", "PreK", "Pre-Kindergarten"
- **Other text**: Any text value will be preserved

## Examples

- `5` → stored as `"5"` (can be converted back to int)
- `"Kindergarten"` → stored as `"K"` (standardized)
- `"Pre-K"` → stored as `"Pre-K"`
- `"K"` → stored as `"K"`

## Extraction Logic

The extraction logic:
1. First checks for kindergarten variants → returns "K"
2. Then extracts numbers → returns integer (1-12)
3. Finally preserves text if it looks like a grade description

## Validation

Validation accepts:
- Integers 1-12
- Text values like "K", "Kindergarten", "Pre-K"
- Any other text (treated as valid grade)



