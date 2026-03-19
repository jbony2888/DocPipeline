# Archived test records

This folder holds PDFs downloaded from Supabase before deleting test records.

**To archive and delete test records (before March 1):**
```bash
python scripts/cleanup_test_records_before_date.py --date 2026-03-01 --archive-to archived_test_records --execute
```

- Downloads all matching PDFs here
- Saves `manifest.json` with record metadata
- Deletes records and storage from Supabase

**Dry run (list only):**
```bash
python scripts/cleanup_test_records_before_date.py --date 2026-03-01 --confirm
```
