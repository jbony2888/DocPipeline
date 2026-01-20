# Artifact Management Guide

## What Are Artifacts?

Each processed submission generates an **artifact directory** containing:
- `original.pdf` / `original.jpg` - Original uploaded file
- `ocr.json` - Raw OCR output with confidence scores
- `raw_text.txt` - Full extracted text
- `contact_block.txt` - Segmented contact section
- `essay_block.txt` - Segmented essay content
- `structured.json` - Extracted fields
- `validation.json` - Validation results
- `extraction_debug.json` - Debugging information
- `metadata.json` - File metadata

**Purpose:** Full audit trail and debugging capability for each submission.

---

## Should You Keep Artifacts?

### ✅ **Keep Artifacts If:**

1. **Active Contest Period**
   - You're still processing submissions
   - Volunteers may need to reference original PDFs
   - Debugging extraction issues is ongoing

2. **Quality Assurance**
   - You want to audit extraction accuracy
   - Need to verify OCR quality
   - Debugging why specific fields weren't extracted

3. **Historical Reference**
   - Contest records need to be maintained
   - Legal/compliance requirements
   - Future reference for similar submissions

4. **Limited Storage Concerns**
   - Artifacts are typically small (30-50 KB per submission)
   - 1,000 submissions ≈ 30-50 MB
   - 10,000 submissions ≈ 300-500 MB

### 🗑️ **Clean Up Artifacts If:**

1. **After Contest Ends**
   - All submissions processed and approved
   - No longer need debugging capabilities
   - Contest results finalized

2. **Privacy/Security Requirements**
   - Need to remove student data after contest
   - GDPR/compliance requirements
   - Storage policy restrictions

3. **Storage Constraints**
   - Running low on disk space
   - Cloud storage costs are a concern
   - Archiving to long-term storage

4. **Performance Issues**
   - Thousands of artifact directories
   - File system operations slowing down
   - Backup processes taking too long

---

## Recommended Strategy

### **Option 1: Keep All Artifacts (Recommended for Active Use)**

**When:** During active contest processing and for 1-2 years after

**Benefits:**
- Full audit trail
- Easy debugging
- Reference for volunteers
- Can reprocess if needed

**Storage:** Typically < 1 GB for 10,000+ submissions

### **Option 2: Archive After Contest**

**When:** After contest ends and all records are approved/exported

**Steps:**
1. Export all clean records to CSV (already done)
2. Create backup of artifacts (optional)
3. Archive to long-term storage (cloud/tape)
4. Delete local artifacts

**Retention:** Keep archived copy for compliance period (e.g., 7 years)

### **Option 3: Selective Cleanup**

**When:** Want to reduce storage but keep important artifacts

**Strategy:**
- Keep artifacts for records in database (active records)
- Delete artifacts for old/rejected records
- Keep artifacts with extraction issues (for debugging)

---

## Cleanup Scripts

### Script 1: Clean Up Old Artifacts (Keep Database Records)

Removes artifact directories that are NOT in the database:

```python
# cleanup_orphaned_artifacts.py
from pathlib import Path
from pipeline.database import get_db_records, init_database
import shutil

def cleanup_orphaned_artifacts(artifacts_dir="artifacts", dry_run=True):
    """
    Remove artifact directories that don't have corresponding database records.
    
    Args:
        artifacts_dir: Path to artifacts directory
        dry_run: If True, only show what would be deleted (don't actually delete)
    """
    init_database()
    
    # Get all submission IDs from database
    all_records = get_db_records(needs_review=None)  # Get all records
    db_submission_ids = {r["submission_id"] for r in all_records}
    
    # Get all artifact directories
    artifacts_path = Path(artifacts_dir)
    if not artifacts_path.exists():
        print(f"Artifacts directory {artifacts_dir} does not exist")
        return
    
    artifact_dirs = [d for d in artifacts_path.iterdir() if d.is_dir()]
    orphaned = []
    kept = []
    
    for artifact_dir in artifact_dirs:
        submission_id = artifact_dir.name
        if submission_id not in db_submission_ids:
            orphaned.append(artifact_dir)
        else:
            kept.append(artifact_dir)
    
    print(f"Found {len(kept)} artifact directories with database records")
    print(f"Found {len(orphaned)} orphaned artifact directories")
    
    if orphaned:
        print("\nOrphaned directories (would be deleted):")
        for d in orphaned[:10]:  # Show first 10
            print(f"  - {d.name}")
        if len(orphaned) > 10:
            print(f"  ... and {len(orphaned) - 10} more")
        
        if not dry_run:
            confirm = input(f"\nDelete {len(orphaned)} orphaned artifact directories? (yes/no): ")
            if confirm.lower() == "yes":
                for artifact_dir in orphaned:
                    shutil.rmtree(artifact_dir)
                    print(f"Deleted {artifact_dir.name}")
                print(f"\n✅ Deleted {len(orphaned)} orphaned artifact directories")
            else:
                print("Cleanup cancelled")
        else:
            print("\n[DRY RUN] No files deleted. Run with dry_run=False to actually delete.")
    else:
        print("\n✅ No orphaned artifacts found")

if __name__ == "__main__":
    import sys
    dry_run = "--execute" not in sys.argv
    if dry_run:
        print("🔍 DRY RUN MODE - No files will be deleted")
        print("Add --execute flag to actually delete files\n")
    cleanup_orphaned_artifacts(dry_run=dry_run)
```

### Script 2: Archive Artifacts to ZIP

Creates a compressed archive of all artifacts:

```python
# archive_artifacts.py
from pathlib import Path
import zipfile
from datetime import datetime

def archive_artifacts(artifacts_dir="artifacts", output_zip=None):
    """
    Create a ZIP archive of all artifacts.
    
    Args:
        artifacts_dir: Path to artifacts directory
        output_zip: Output ZIP file path (default: artifacts_archive_YYYYMMDD.zip)
    """
    artifacts_path = Path(artifacts_dir)
    if not artifacts_path.exists():
        print(f"Artifacts directory {artifacts_dir} does not exist")
        return
    
    if output_zip is None:
        timestamp = datetime.now().strftime("%Y%m%d")
        output_zip = f"artifacts_archive_{timestamp}.zip"
    
    print(f"Creating archive: {output_zip}")
    print("This may take a while for large artifact directories...")
    
    artifact_dirs = [d for d in artifacts_path.iterdir() if d.is_dir()]
    total_dirs = len(artifact_dirs)
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for idx, artifact_dir in enumerate(artifact_dirs, 1):
            submission_id = artifact_dir.name
            # Add all files in artifact directory
            for file_path in artifact_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(artifacts_path.parent)
                    zipf.write(file_path, arcname)
            
            if idx % 100 == 0:
                print(f"  Processed {idx}/{total_dirs} directories...")
    
    zip_size = Path(output_zip).stat().st_size / (1024 * 1024)  # MB
    print(f"\n✅ Archive created: {output_zip} ({zip_size:.1f} MB)")
    print(f"   Contains {total_dirs} artifact directories")

if __name__ == "__main__":
    archive_artifacts()
```

### Script 3: Clean Up by Date

Removes artifacts older than a specified number of days:

```python
# cleanup_old_artifacts.py
from pathlib import Path
import shutil
from datetime import datetime, timedelta

def cleanup_old_artifacts(artifacts_dir="artifacts", days_old=365, dry_run=True):
    """
    Remove artifact directories older than specified days.
    
    Args:
        artifacts_dir: Path to artifacts directory
        days_old: Delete artifacts older than this many days
        dry_run: If True, only show what would be deleted
    """
    artifacts_path = Path(artifacts_dir)
    if not artifacts_path.exists():
        print(f"Artifacts directory {artifacts_dir} does not exist")
        return
    
    cutoff_date = datetime.now() - timedelta(days=days_old)
    artifact_dirs = [d for d in artifacts_path.iterdir() if d.is_dir()]
    
    old_artifacts = []
    for artifact_dir in artifact_dirs:
        # Check metadata.json for creation date
        metadata_file = artifact_dir / "metadata.json"
        if metadata_file.exists():
            import json
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    created_at = metadata.get("created_at")
                    if created_at:
                        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        if created_date < cutoff_date:
                            old_artifacts.append((artifact_dir, created_date))
            except Exception as e:
                # If can't read metadata, check directory modification time
                dir_mtime = datetime.fromtimestamp(artifact_dir.stat().st_mtime)
                if dir_mtime < cutoff_date:
                    old_artifacts.append((artifact_dir, dir_mtime))
    
    if old_artifacts:
        print(f"Found {len(old_artifacts)} artifact directories older than {days_old} days")
        print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d')}\n")
        
        print("Oldest artifacts (would be deleted):")
        for artifact_dir, date in sorted(old_artifacts, key=lambda x: x[1])[:10]:
            print(f"  - {artifact_dir.name} (created: {date.strftime('%Y-%m-%d')})")
        if len(old_artifacts) > 10:
            print(f"  ... and {len(old_artifacts) - 10} more")
        
        if not dry_run:
            confirm = input(f"\nDelete {len(old_artifacts)} old artifact directories? (yes/no): ")
            if confirm.lower() == "yes":
                for artifact_dir, _ in old_artifacts:
                    shutil.rmtree(artifact_dir)
                print(f"\n✅ Deleted {len(old_artifacts)} old artifact directories")
            else:
                print("Cleanup cancelled")
        else:
            print("\n[DRY RUN] No files deleted. Run with dry_run=False to actually delete.")
    else:
        print(f"✅ No artifacts older than {days_old} days found")

if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 365
    dry_run = "--execute" not in sys.argv
    
    if dry_run:
        print(f"🔍 DRY RUN MODE - No files will be deleted")
        print(f"Would delete artifacts older than {days} days")
        print("Add --execute flag to actually delete files\n")
    
    cleanup_old_artifacts(days_old=days, dry_run=dry_run)
```

---

## Recommendations

### **For Active Contest Processing:**
✅ **Keep all artifacts** - You'll need them for debugging and reference

### **After Contest Ends:**
1. Export all clean records to CSV (for long-term storage)
2. Create ZIP archive of artifacts (backup)
3. Keep artifacts locally for 1-2 years (in case of questions)
4. After retention period, delete local artifacts (keep archive)

### **For Privacy/Compliance:**
- Review retention requirements
- Archive artifacts securely
- Delete local copies after compliance period
- Use encrypted archives if storing sensitive data

---

## Quick Commands

**Check artifact directory size:**
```bash
du -sh artifacts/
```

**Count artifact directories:**
```bash
find artifacts -type d -maxdepth 1 | wc -l
```

**Create backup archive:**
```bash
python archive_artifacts.py
```

**Clean up orphaned artifacts (dry run):**
```bash
python cleanup_orphaned_artifacts.py
```

**Clean up orphaned artifacts (execute):**
```bash
python cleanup_orphaned_artifacts.py --execute
```

**Clean up artifacts older than 1 year (dry run):**
```bash
python cleanup_old_artifacts.py 365
```

**Clean up artifacts older than 1 year (execute):**
```bash
python cleanup_old_artifacts.py 365 --execute
```

---

## Summary

**Recommendation:** Keep artifacts during active use, archive after contest ends, and clean up based on your retention policy.

The artifact files are relatively small, and having them available provides valuable debugging and audit capabilities. Only clean up when:
- Contest is fully complete
- You have backups/archives
- You need to free up space
- Compliance requires removal






