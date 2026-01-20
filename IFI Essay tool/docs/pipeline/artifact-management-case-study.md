# Artifact Management: A Case Study & Tutorial

**Managing Intermediate Files and Audit Trails in Production Document Processing Systems**

---

## Table of Contents

1. [Introduction: What Are Artifacts and Why Do They Matter?](#introduction)
2. [Case Study: IFI Essay Gateway Artifact Strategy](#case-study)
3. [Decision Framework: Keep, Archive, or Delete?](#decision-framework)
4. [Tutorial: Implementing Artifact Management](#tutorial)
5. [Best Practices and Patterns](#best-practices)
6. [Common Pitfalls and Solutions](#pitfalls)
7. [Advanced Strategies](#advanced-strategies)
8. [Conclusion](#conclusion)

---

## Introduction: What Are Artifacts and Why Do They Matter? {#introduction}

### What Are Artifacts?

In document processing pipelines, **artifacts** are intermediate files generated at each stage of processing. They represent the complete transformation path from raw input to final output.

**Example from IFI Essay Gateway:**

```
Original Upload → OCR → Segmentation → Extraction → Validation → Database
     ↓              ↓          ↓            ↓            ↓
 original.pdf   ocr.json  contact_block  structured  validation
                              .txt        .json        .json
                             essay_block
                                .txt
```

### Why Artifacts Matter

1. **Debugging & Troubleshooting**
   - When extraction fails, artifacts show exactly where it broke
   - OCR artifacts reveal text quality issues
   - Segmentation artifacts show boundary detection problems

2. **Quality Assurance & Auditing**
   - Verify extraction accuracy
   - Trace decisions back to source data
   - Compliance and audit requirements

3. **Reprocessing & Recovery**
   - Fix extraction logic and reprocess old submissions
   - Recover from processing errors
   - Handle updated requirements

4. **Transparency & Trust**
   - Stakeholders can verify system behavior
   - Volunteers can review original documents
   - Clear audit trail for contest administration

### The Storage Trade-Off

**The Challenge:**
- Artifacts provide value but consume storage
- Need to balance usefulness vs. cost
- Storage costs grow with volume
- But debugging without artifacts is nearly impossible

**Key Insight:** Artifact storage is usually cheap compared to the cost of debugging without them.

---

## Case Study: IFI Essay Gateway Artifact Strategy {#case-study}

### Project Context

**Challenge:** Process thousands of handwritten essay submissions annually with high accuracy and accountability.

**Requirements:**
- Full audit trail for contest administration
- Ability to debug extraction failures
- Volunteers need access to original PDFs
- Long-term storage needs unclear

### Artifact Structure

Each submission generates:

```
artifacts/
└── {submission_id}/
    ├── original.pdf              # 30-600 KB
    ├── metadata.json             # < 1 KB
    ├── ocr.json                  # 5-20 KB
    ├── raw_text.txt              # 2-10 KB
    ├── contact_block.txt         # 1-5 KB
    ├── essay_block.txt           # 2-50 KB
    ├── structured.json           # 1-2 KB
    ├── validation.json           # < 1 KB
    └── extraction_debug.json     # 2-5 KB

Total: ~50-700 KB per submission
```

### Real-World Storage Analysis

**Current State (December 2024):**
- 12 submissions processed
- Total artifact storage: 2.6 MB
- Average per submission: ~217 KB
- Largest artifact: 630 KB (high-resolution PDF)
- Smallest artifact: 30 KB (low-resolution PDF)

**Projected at Scale:**
- 1,000 submissions: ~200 MB
- 10,000 submissions: ~2 GB
- 100,000 submissions: ~20 GB

**Key Finding:** Storage scales linearly and remains manageable even at large volumes.

### Decision Process

**Initial Strategy (Active Contest Period):**
✅ **Keep All Artifacts**

**Rationale:**
1. Storage is minimal (even at 10K submissions = 2 GB)
2. Debugging extraction issues requires artifacts
3. Volunteers frequently reference original PDFs
4. Contest administration needs audit trail

**Future Strategy (Post-Contest):**
🔄 **Archive, Then Selective Cleanup**

**Planned Steps:**
1. Export all clean records to CSV (structured data)
2. Create ZIP archive of artifacts (compressed backup)
3. Keep artifacts locally for 1-2 years
4. After retention period, delete local artifacts (keep archive)

**Rationale:**
1. CSV export contains all structured data needed
2. Archive provides recovery capability
3. Local artifacts not needed after review period
4. Archive satisfies compliance/audit requirements

### Lessons Learned

1. **Artifacts Enabled Rapid Debugging**
   - Fixed essay segmentation issue in hours (not days)
   - OCR artifacts revealed text quality problems
   - Segmentation artifacts showed boundary detection failures

2. **Original PDFs Are Essential**
   - Volunteers frequently reference original documents
   - Debugging extraction failures requires source files
   - Quality assurance needs access to originals

3. **Storage Costs Are Negligible**
   - Even at 10K submissions, artifacts < 2 GB
   - Cloud storage: $0.023/GB/month (AWS S3)
   - Cost for 10K submissions: ~$0.05/month
   - Far cheaper than debugging without artifacts

4. **Artifact Organization Matters**
   - Organized by submission_id enables easy lookup
   - Consistent naming across stages enables automation
   - JSON artifacts enable programmatic analysis

---

## Decision Framework: Keep, Archive, or Delete? {#decision-framework}

### Step 1: Assess Your Needs

Ask yourself:

| Question | Keep | Archive | Delete |
|----------|------|---------|--------|
| **Active processing?** | ✅ | ❌ | ❌ |
| **Frequent debugging?** | ✅ | ❌ | ❌ |
| **QA/audit requirements?** | ✅ | ✅ | ❌ |
| **Storage constraints?** | ⚠️ | ✅ | ✅ |
| **Privacy/compliance?** | ⚠️ | ✅ | ✅ |

### Step 2: Calculate Storage Costs

**Formula:**
```
Total Storage (GB) = (Avg Artifact Size × Number of Submissions) / 1024³
Monthly Cost = Total Storage × Storage Cost per GB
```

**Example:**
```
Average artifact size: 250 KB
Submissions: 10,000
Total Storage = (250 KB × 10,000) / 1,073,741,824 = 2.33 GB
AWS S3 Cost = 2.33 GB × $0.023/GB = $0.054/month
```

**Key Insight:** Even at 100K submissions (23 GB), cost is only $0.53/month.

### Step 3: Evaluate Use Cases

**Keep Artifacts If:**

1. **Active Development/Debugging**
   - Still fixing extraction issues
   - Improving segmentation logic
   - Testing new extraction methods

2. **Frequent Reference Needed**
   - Volunteers access original PDFs regularly
   - QA team reviews extraction quality
   - Stakeholders need audit trail

3. **Reprocessing Likely**
   - May need to reprocess with improved logic
   - Handling updated requirements
   - Fixing systematic errors

**Archive Artifacts If:**

1. **Post-Processing Phase**
   - Contest ended, records finalized
   - No longer debugging extraction issues
   - Want backup but don't need immediate access

2. **Compliance Requirements**
   - Need long-term storage for audit
   - Legal retention requirements
   - Historical reference needed

3. **Cost Optimization**
   - Want to reduce local storage
   - Archive storage is cheaper
   - Can restore from archive if needed

**Delete Artifacts If:**

1. **Retention Period Expired**
   - Compliance requirements met
   - Archive backup created
   - No longer needed for any purpose

2. **Storage Constraints**
   - Disk space is critical
   - Can't afford even minimal storage
   - Alternative solutions available

3. **Privacy Requirements**
   - Must remove student data immediately
   - GDPR/compliance requires deletion
   - No archive needed (data fully anonymized)

### Decision Matrix

```
┌─────────────────────────────────────────────────────────────┐
│                    DECISION MATRIX                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Active Processing?                                         │
│      YES → Keep Artifacts ✅                                │
│      NO  ↓                                                   │
│                                                              │
│  Need for Debugging/QA?                                     │
│      YES → Keep Artifacts ✅                                │
│      NO  ↓                                                   │
│                                                              │
│  Compliance/Audit Requirements?                             │
│      YES → Archive Artifacts 📦                             │
│      NO  ↓                                                   │
│                                                              │
│  Storage Constraints?                                       │
│      YES → Archive, Then Delete 📦→🗑️                       │
│      NO  → Keep Artifacts ✅                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Tutorial: Implementing Artifact Management {#tutorial}

### Tutorial 1: Basic Artifact Cleanup (Orphaned Records)

**Scenario:** You've deleted records from the database but artifact directories remain.

**Step 1: Create the Cleanup Script**

```python
# cleanup_orphaned_artifacts.py
from pathlib import Path
from pipeline.database import get_db_records, init_database
import shutil

def cleanup_orphaned_artifacts(artifacts_dir="artifacts", dry_run=True):
    """
    Remove artifact directories that don't have corresponding database records.
    
    This is safe to run because:
    1. Only removes artifacts NOT in database
    2. Dry run mode shows what would be deleted
    3. Requires explicit confirmation before deletion
    """
    init_database()
    
    # Get all submission IDs from database
    all_records = get_db_records(needs_review=None)
    db_submission_ids = {r["submission_id"] for r in all_records}
    
    # Get all artifact directories
    artifacts_path = Path(artifacts_dir)
    if not artifacts_path.exists():
        print(f"❌ Artifacts directory {artifacts_dir} does not exist")
        return
    
    artifact_dirs = [d for d in artifacts_path.iterdir() if d.is_dir()]
    orphaned = []
    kept = []
    
    # Classify artifacts
    for artifact_dir in artifact_dirs:
        submission_id = artifact_dir.name
        if submission_id not in db_submission_ids:
            orphaned.append(artifact_dir)
        else:
            kept.append(artifact_dir)
    
    # Report findings
    print(f"📊 Analysis Results:")
    print(f"   • Artifacts with database records: {len(kept)}")
    print(f"   • Orphaned artifacts (no DB record): {len(orphaned)}")
    
    if orphaned:
        print(f"\n🗑️  Orphaned directories (would be deleted):")
        for d in orphaned[:10]:
            size = sum(f.stat().st_size for f in d.rglob('*') if f.is_file())
            print(f"   • {d.name} ({size / 1024:.1f} KB)")
        if len(orphaned) > 10:
            print(f"   ... and {len(orphaned) - 10} more")
        
        total_size = sum(
            sum(f.stat().st_size for f in d.rglob('*') if f.is_file())
            for d in orphaned
        ) / (1024 * 1024)
        print(f"\n💾 Total space to free: {total_size:.2f} MB")
        
        if not dry_run:
            confirm = input(f"\n⚠️  Delete {len(orphaned)} orphaned artifact directories? (yes/no): ")
            if confirm.lower() == "yes":
                for artifact_dir in orphaned:
                    shutil.rmtree(artifact_dir)
                print(f"\n✅ Deleted {len(orphaned)} orphaned artifact directories")
                print(f"   Freed {total_size:.2f} MB of disk space")
            else:
                print("❌ Cleanup cancelled")
        else:
            print("\n🔍 [DRY RUN] No files deleted.")
            print("   Run with --execute to actually delete files.")
    else:
        print("\n✅ No orphaned artifacts found. Database and artifacts are in sync.")

if __name__ == "__main__":
    import sys
    dry_run = "--execute" not in sys.argv
    if dry_run:
        print("🔍 DRY RUN MODE")
        print("   Add --execute flag to actually delete files\n")
    cleanup_orphaned_artifacts(dry_run=dry_run)
```

**Step 2: Run in Dry-Run Mode (Safe Preview)**

```bash
cd "/Users/jerrybony/Documents/GitHub/DocPipeline/IFI Essay tool"
python cleanup_orphaned_artifacts.py
```

**Expected Output:**
```
🔍 DRY RUN MODE
   Add --execute flag to actually delete files

📊 Analysis Results:
   • Artifacts with database records: 10
   • Orphaned artifacts (no DB record: 2

🗑️  Orphaned directories (would be deleted):
   • abc123def456 (250.5 KB)
   • xyz789ghi012 (180.3 KB)

💾 Total space to free: 0.42 MB

🔍 [DRY RUN] No files deleted.
   Run with --execute to actually delete files.
```

**Step 3: Execute Cleanup (After Review)**

```bash
python cleanup_orphaned_artifacts.py --execute
```

**Expected Output:**
```
⚠️  Delete 2 orphaned artifact directories? (yes/no): yes

✅ Deleted 2 orphaned artifact directories
   Freed 0.42 MB of disk space
```

---

### Tutorial 2: Creating Artifact Archives

**Scenario:** Contest ended, you want to backup artifacts before cleanup.

**Step 1: Create the Archive Script**

```python
# archive_artifacts.py
from pathlib import Path
import zipfile
from datetime import datetime
import json

def archive_artifacts(artifacts_dir="artifacts", output_zip=None, include_metadata=True):
    """
    Create a compressed ZIP archive of all artifacts.
    
    Features:
    - Preserves directory structure
    - Includes metadata manifest
    - Progress reporting for large archives
    - Compression to reduce storage
    """
    artifacts_path = Path(artifacts_dir)
    if not artifacts_path.exists():
        print(f"❌ Artifacts directory {artifacts_dir} does not exist")
        return
    
    # Generate output filename
    if output_zip is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_zip = f"artifacts_archive_{timestamp}.zip"
    
    output_path = Path(output_zip)
    
    # Check if output file already exists
    if output_path.exists():
        confirm = input(f"⚠️  {output_zip} already exists. Overwrite? (yes/no): ")
        if confirm.lower() != "yes":
            print("❌ Archive cancelled")
            return
    
    print(f"📦 Creating archive: {output_zip}")
    print("   This may take a while for large artifact directories...\n")
    
    artifact_dirs = sorted([d for d in artifacts_path.iterdir() if d.is_dir()])
    total_dirs = len(artifact_dirs)
    manifest = {
        "archive_date": datetime.now().isoformat(),
        "total_submissions": total_dirs,
        "submissions": []
    }
    
    total_size = 0
    compressed_size = 0
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for idx, artifact_dir in enumerate(artifact_dirs, 1):
            submission_id = artifact_dir.name
            dir_size = 0
            files_added = 0
            
            # Read metadata if available
            metadata = {}
            metadata_file = artifact_dir / "metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                except:
                    pass
            
            # Add all files in artifact directory
            for file_path in artifact_dir.rglob('*'):
                if file_path.is_file():
                    file_size = file_path.stat().st_size
                    dir_size += file_size
                    total_size += file_size
                    
                    # Preserve directory structure relative to artifacts parent
                    arcname = file_path.relative_to(artifacts_path.parent)
                    zipf.write(file_path, arcname)
                    files_added += 1
            
            manifest["submissions"].append({
                "submission_id": submission_id,
                "files": files_added,
                "size_bytes": dir_size,
                "created_at": metadata.get("created_at", "unknown")
            })
            
            # Progress reporting
            if idx % 10 == 0 or idx == total_dirs:
                progress = (idx / total_dirs) * 100
                print(f"   Progress: {idx}/{total_dirs} ({progress:.1f}%) - {submission_id}")
    
    # Get compressed size
    compressed_size = output_path.stat().st_size
    
    # Write manifest to archive
    with zipfile.ZipFile(output_path, 'a') as zipf:
        manifest_json = json.dumps(manifest, indent=2)
        zipf.writestr("ARCHIVE_MANIFEST.json", manifest_json)
    
    # Summary
    compression_ratio = (1 - compressed_size / total_size) * 100 if total_size > 0 else 0
    print(f"\n✅ Archive created successfully!")
    print(f"   • Output: {output_zip}")
    print(f"   • Submissions: {total_dirs}")
    print(f"   • Original size: {total_size / (1024*1024):.2f} MB")
    print(f"   • Compressed size: {compressed_size / (1024*1024):.2f} MB")
    print(f"   • Compression: {compression_ratio:.1f}%")
    print(f"   • Manifest: ARCHIVE_MANIFEST.json (included in archive)")

if __name__ == "__main__":
    import sys
    output_file = sys.argv[1] if len(sys.argv) > 1 else None
    archive_artifacts(output_zip=output_file)
```

**Step 2: Create Archive**

```bash
python archive_artifacts.py
```

**Expected Output:**
```
📦 Creating archive: artifacts_archive_20241224_143022.zip
   This may take a while for large artifact directories...

   Progress: 10/12 (83.3%) - d47d564b5693
   Progress: 12/12 (100.0%) - faa91f274edc

✅ Archive created successfully!
   • Output: artifacts_archive_20241224_143022.zip
   • Submissions: 12
   • Original size: 2.60 MB
   • Compressed size: 2.45 MB
   • Compression: 5.8%
   • Manifest: ARCHIVE_MANIFEST.json (included in archive)
```

**Step 3: Verify Archive**

```bash
# List archive contents
unzip -l artifacts_archive_20241224_143022.zip | head -20

# Extract manifest
unzip -p artifacts_archive_20241224_143022.zip ARCHIVE_MANIFEST.json | python -m json.tool
```

---

### Tutorial 3: Age-Based Cleanup

**Scenario:** Remove artifacts older than 1 year, keeping recent ones.

**Step 1: Create Age-Based Cleanup Script**

```python
# cleanup_old_artifacts.py
from pathlib import Path
import shutil
from datetime import datetime, timedelta
import json

def cleanup_old_artifacts(artifacts_dir="artifacts", days_old=365, dry_run=True):
    """
    Remove artifact directories older than specified days.
    
    Uses metadata.json creation date if available,
    otherwise falls back to directory modification time.
    """
    artifacts_path = Path(artifacts_dir)
    if not artifacts_path.exists():
        print(f"❌ Artifacts directory {artifacts_dir} does not exist")
        return
    
    cutoff_date = datetime.now() - timedelta(days=days_old)
    artifact_dirs = [d for d in artifacts_path.iterdir() if d.is_dir()]
    
    old_artifacts = []
    recent_artifacts = []
    
    for artifact_dir in artifact_dirs:
        submission_id = artifact_dir.name
        created_date = None
        
        # Try to get creation date from metadata.json
        metadata_file = artifact_dir / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    created_at = metadata.get("created_at")
                    if created_at:
                        # Handle ISO format with or without timezone
                        created_at = created_at.replace('Z', '+00:00')
                        created_date = datetime.fromisoformat(created_at)
                        if created_date.tzinfo:
                            created_date = created_date.replace(tzinfo=None)
            except Exception as e:
                pass
        
        # Fallback to directory modification time
        if created_date is None:
            created_date = datetime.fromtimestamp(artifact_dir.stat().st_mtime)
        
        # Classify by age
        if created_date < cutoff_date:
            old_artifacts.append((artifact_dir, created_date))
        else:
            recent_artifacts.append((artifact_dir, created_date))
    
    # Report findings
    print(f"📊 Age Analysis (cutoff: {cutoff_date.strftime('%Y-%m-%d')}):")
    print(f"   • Recent artifacts (kept): {len(recent_artifacts)}")
    print(f"   • Old artifacts (> {days_old} days): {len(old_artifacts)}")
    
    if old_artifacts:
        print(f"\n🗑️  Oldest artifacts (would be deleted):")
        sorted_old = sorted(old_artifacts, key=lambda x: x[1])
        total_size = 0
        
        for artifact_dir, date in sorted_old[:10]:
            size = sum(f.stat().st_size for f in artifact_dir.rglob('*') if f.is_file())
            total_size += size
            print(f"   • {artifact_dir.name} (created: {date.strftime('%Y-%m-%d')}, {size/1024:.1f} KB)")
        
        if len(old_artifacts) > 10:
            # Calculate remaining size
            for artifact_dir, _ in sorted_old[10:]:
                size = sum(f.stat().st_size for f in artifact_dir.rglob('*') if f.is_file())
                total_size += size
            print(f"   ... and {len(old_artifacts) - 10} more")
        
        print(f"\n💾 Total space to free: {total_size / (1024*1024):.2f} MB")
        
        if not dry_run:
            confirm = input(f"\n⚠️  Delete {len(old_artifacts)} old artifact directories? (yes/no): ")
            if confirm.lower() == "yes":
                for artifact_dir, _ in old_artifacts:
                    shutil.rmtree(artifact_dir)
                print(f"\n✅ Deleted {len(old_artifacts)} old artifact directories")
                print(f"   Freed {total_size / (1024*1024):.2f} MB of disk space")
            else:
                print("❌ Cleanup cancelled")
        else:
            print("\n🔍 [DRY RUN] No files deleted.")
            print("   Run with --execute to actually delete files.")
    else:
        print(f"\n✅ No artifacts older than {days_old} days found.")

if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 365
    dry_run = "--execute" not in sys.argv
    
    if dry_run:
        print("🔍 DRY RUN MODE")
        print(f"   Would delete artifacts older than {days} days")
        print("   Add --execute to actually delete files\n")
    
    cleanup_old_artifacts(days_old=days, dry_run=dry_run)
```

**Step 2: Preview Old Artifacts**

```bash
# Check artifacts older than 90 days
python cleanup_old_artifacts.py 90
```

**Step 3: Delete Old Artifacts**

```bash
# Delete artifacts older than 365 days (1 year)
python cleanup_old_artifacts.py 365 --execute
```

---

### Tutorial 4: Artifact Health Check

**Scenario:** Verify artifact integrity and identify issues.

**Step 1: Create Health Check Script**

```python
# artifact_health_check.py
from pathlib import Path
import json

def artifact_health_check(artifacts_dir="artifacts"):
    """
    Check artifact directory health and integrity.
    
    Reports:
    - Missing required files
    - Corrupted JSON files
    - Size anomalies
    - Orphaned artifacts
    """
    artifacts_path = Path(artifacts_dir)
    if not artifacts_path.exists():
        print(f"❌ Artifacts directory {artifacts_dir} does not exist")
        return
    
    required_files = [
        "original.pdf",
        "metadata.json",
        "ocr.json",
        "raw_text.txt",
        "contact_block.txt",
        "essay_block.txt",
        "structured.json",
        "validation.json"
    ]
    
    artifact_dirs = sorted([d for d in artifacts_path.iterdir() if d.is_dir()])
    
    issues = {
        "missing_files": [],
        "corrupted_json": [],
        "size_anomalies": [],
        "empty_files": []
    }
    
    total_size = 0
    valid_count = 0
    
    print(f"🔍 Health Check: {len(artifact_dirs)} artifact directories\n")
    
    for artifact_dir in artifact_dirs:
        submission_id = artifact_dir.name
        dir_issues = []
        
        # Check for required files
        missing = []
        for req_file in required_files:
            if not (artifact_dir / req_file).exists():
                missing.append(req_file)
        
        if missing:
            issues["missing_files"].append({
                "submission_id": submission_id,
                "missing": missing
            })
            dir_issues.append(f"Missing: {', '.join(missing)}")
        
        # Check JSON file integrity
        json_files = ["metadata.json", "ocr.json", "structured.json", "validation.json"]
        for json_file in json_files:
            json_path = artifact_dir / json_file
            if json_path.exists():
                try:
                    with open(json_path, 'r') as f:
                        json.load(f)
                except json.JSONDecodeError:
                    issues["corrupted_json"].append({
                        "submission_id": submission_id,
                        "file": json_file
                    })
                    dir_issues.append(f"Corrupted: {json_file}")
        
        # Check file sizes
        dir_size = 0
        for file_path in artifact_dir.rglob('*'):
            if file_path.is_file():
                size = file_path.stat().st_size
                dir_size += size
                
                if size == 0:
                    issues["empty_files"].append({
                        "submission_id": submission_id,
                        "file": file_path.name
                    })
                    dir_issues.append(f"Empty: {file_path.name}")
        
        total_size += dir_size
        
        # Size anomaly detection (very small or very large)
        avg_size = 250 * 1024  # 250 KB average
        if dir_size < 10 * 1024:  # Less than 10 KB
            issues["size_anomalies"].append({
                "submission_id": submission_id,
                "size_kb": dir_size / 1024,
                "reason": "Very small (possible incomplete processing)"
            })
        elif dir_size > 2 * 1024 * 1024:  # Larger than 2 MB
            issues["size_anomalies"].append({
                "submission_id": submission_id,
                "size_kb": dir_size / 1024,
                "reason": "Very large (high-res PDF or many files)"
            })
        
        if not dir_issues:
            valid_count += 1
        else:
            print(f"⚠️  {submission_id}:")
            for issue in dir_issues:
                print(f"      • {issue}")
    
    # Summary
    print(f"\n📊 Health Check Summary:")
    print(f"   • Total artifacts: {len(artifact_dirs)}")
    print(f"   • Valid artifacts: {valid_count}")
    print(f"   • Total storage: {total_size / (1024*1024):.2f} MB")
    print(f"   • Average size: {(total_size / len(artifact_dirs)) / 1024:.1f} KB per artifact")
    
    if issues["missing_files"]:
        print(f"\n❌ Missing Files: {len(issues['missing_files'])} artifacts")
        for item in issues["missing_files"][:5]:
            print(f"   • {item['submission_id']}: {', '.join(item['missing'])}")
    
    if issues["corrupted_json"]:
        print(f"\n❌ Corrupted JSON: {len(issues['corrupted_json'])} files")
        for item in issues["corrupted_json"][:5]:
            print(f"   • {item['submission_id']}: {item['file']}")
    
    if issues["size_anomalies"]:
        print(f"\n⚠️  Size Anomalies: {len(issues['size_anomalies'])} artifacts")
        for item in issues["size_anomalies"][:5]:
            print(f"   • {item['submission_id']}: {item['size_kb']:.1f} KB ({item['reason']})")
    
    if issues["empty_files"]:
        print(f"\n⚠️  Empty Files: {len(issues['empty_files'])} files")
        for item in issues["empty_files"][:5]:
            print(f"   • {item['submission_id']}: {item['file']}")
    
    if valid_count == len(artifact_dirs):
        print(f"\n✅ All artifacts are healthy!")

if __name__ == "__main__":
    artifact_health_check()
```

**Step 2: Run Health Check**

```bash
python artifact_health_check.py
```

**Expected Output:**
```
🔍 Health Check: 12 artifact directories

📊 Health Check Summary:
   • Total artifacts: 12
   • Valid artifacts: 12
   • Total storage: 2.60 MB
   • Average size: 217.3 KB per artifact

✅ All artifacts are healthy!
```

---

## Best Practices and Patterns {#best-practices}

### 1. Organize by Submission ID

**Pattern:** Use unique submission ID as directory name.

```python
artifacts/{submission_id}/
```

**Benefits:**
- Easy lookup by ID
- Prevents naming conflicts
- Enables database correlation

### 2. Consistent File Naming

**Pattern:** Use descriptive, consistent names across all stages.

```python
original.{ext}        # Source file
ocr.json             # OCR results
raw_text.txt         # Full text
contact_block.txt    # Segmented contact
essay_block.txt      # Segmented essay
structured.json      # Extracted fields
validation.json      # Validation results
```

**Benefits:**
- Predictable structure
- Easy automation
- Clear purpose

### 3. Include Metadata

**Pattern:** Store metadata.json with creation date, original filename, etc.

```json
{
  "submission_id": "abc123",
  "original_filename": "essay_001.pdf",
  "created_at": "2024-12-24T14:30:22Z",
  "file_type": "pdf",
  "file_size_bytes": 250000
}
```

**Benefits:**
- Enables age-based cleanup
- Tracks original filenames
- Audit trail information

### 4. Preserve Original Files

**Pattern:** Always keep original.pdf/original.jpg.

**Benefits:**
- Volunteers can reference originals
- Debugging extraction failures
- Quality assurance verification

### 5. JSON for Structured Data

**Pattern:** Use JSON for structured artifacts (OCR, extraction, validation).

**Benefits:**
- Machine-readable
- Easy to parse programmatically
- Supports nested structures

### 6. Dry-Run by Default

**Pattern:** All cleanup scripts default to dry-run mode.

**Benefits:**
- Prevents accidental deletion
- Allows preview before execution
- Safe to test

### 7. Archive Before Cleanup

**Pattern:** Create archive before deleting artifacts.

**Benefits:**
- Recovery capability
- Compliance backup
- Peace of mind

---

## Common Pitfalls and Solutions {#pitfalls}

### Pitfall 1: Deleting Artifacts Too Early

**Problem:** Delete artifacts before debugging is complete.

**Solution:** Keep artifacts during active development and debugging phase.

**Rule of Thumb:** Don't delete artifacts until:
- ✅ All extraction issues resolved
- ✅ Contest/processing complete
- ✅ Archive created
- ✅ Review period passed

### Pitfall 2: Not Tracking Artifact Storage

**Problem:** Storage grows unexpectedly.

**Solution:** Regular monitoring and cleanup scripts.

```bash
# Weekly check
du -sh artifacts/
python artifact_health_check.py
```

### Pitfall 3: Inconsistent Naming

**Problem:** Hard to automate artifact management.

**Solution:** Establish naming conventions and enforce them.

```python
# Good: Consistent naming
artifacts/{submission_id}/original.pdf
artifacts/{submission_id}/ocr.json

# Bad: Inconsistent naming
artifacts/{submission_id}/source.pdf
artifacts/{submission_id}/ocr_results.json
```

### Pitfall 4: Missing Metadata

**Problem:** Can't determine artifact age or origin.

**Solution:** Always include metadata.json with creation date.

```python
metadata = {
    "submission_id": submission_id,
    "created_at": datetime.now().isoformat(),
    "original_filename": filename,
    "file_type": file_ext,
    "file_size_bytes": file_size
}
```

### Pitfall 5: Not Archiving Before Cleanup

**Problem:** Deleted artifacts, then needed them later.

**Solution:** Always create archive before cleanup.

```bash
# 1. Create archive
python archive_artifacts.py

# 2. Verify archive
unzip -t artifacts_archive_*.zip

# 3. Then cleanup
python cleanup_old_artifacts.py 365 --execute
```

---

## Advanced Strategies {#advanced-strategies}

### Strategy 1: Tiered Storage

**Concept:** Move old artifacts to cheaper storage tiers.

```
Active (Local Disk) → Archive (S3 Standard) → Glacier (Long-term)
    0-90 days           90-365 days          365+ days
```

**Implementation:**
- Keep recent artifacts on local disk (fast access)
- Archive to S3 after 90 days (cheaper, still accessible)
- Move to Glacier after 1 year (cheapest, retrieval delay)

### Strategy 2: Selective Retention

**Concept:** Keep artifacts for records with issues, delete clean ones.

**Rationale:**
- Clean records unlikely to need debugging
- Problematic records may need reprocessing
- Reduces storage while preserving debugging capability

**Implementation:**
```python
# Keep artifacts for records with review flags
if record.needs_review:
    keep_artifact(artifact_dir)
else:
    # Clean record, can delete artifact after export
    if record.exported_to_csv:
        delete_artifact(artifact_dir)
```

### Strategy 3: Compressed Artifacts

**Concept:** Compress artifacts older than N days.

**Rationale:**
- Reduces storage for old artifacts
- Still accessible (just unzip when needed)
- Transparent to system (auto-decompress on access)

**Implementation:**
```python
# Compress artifacts older than 30 days
if artifact_age > 30:
    compress_artifact(artifact_dir)
    
# Decompress on access
if is_compressed(artifact_dir):
    decompress_artifact(artifact_dir)
```

### Strategy 4: Artifact Indexing

**Concept:** Maintain searchable index of artifacts.

**Rationale:**
- Fast lookup without scanning directories
- Enable search by metadata (school, grade, date)
- Analytics and reporting

**Implementation:**
```python
# Index artifact metadata
index = {
    "submission_id": "abc123",
    "school_name": "Lincoln Elementary",
    "grade": 5,
    "created_at": "2024-12-24",
    "artifact_path": "artifacts/abc123"
}

# Search by school
results = search_index(school_name="Lincoln Elementary")
```

---

## Conclusion {#conclusion}

### Key Takeaways

1. **Artifacts Are Essential for Debugging**
   - Don't delete during active processing
   - Full audit trail enables rapid problem diagnosis
   - Original files needed for quality assurance

2. **Storage Costs Are Usually Negligible**
   - Even at 10K submissions, artifacts < 2 GB
   - Cloud storage: ~$0.05/month for 2 GB
   - Far cheaper than debugging without artifacts

3. **Implement Proper Management**
   - Health checks to identify issues
   - Cleanup scripts for maintenance
   - Archives for long-term storage
   - Dry-run by default for safety

4. **Follow Lifecycle Strategy**
   - **Active:** Keep all artifacts
   - **Post-Processing:** Archive artifacts
   - **Retention Period:** Keep archive, delete local
   - **After Retention:** Delete archive (if compliance allows)

### Recommended Workflow

```
1. Active Processing
   → Keep all artifacts ✅

2. Contest Complete
   → Export clean records to CSV
   → Create artifact archive 📦
   → Keep artifacts locally for 1-2 years

3. After Retention Period
   → Verify archive integrity
   → Delete local artifacts 🗑️
   → Keep archive for compliance

4. After Compliance Period
   → Delete archive (if allowed) 🗑️
```

### Resources

- **Health Check Script:** `artifact_health_check.py`
- **Cleanup Scripts:** `cleanup_orphaned_artifacts.py`, `cleanup_old_artifacts.py`
- **Archive Script:** `archive_artifacts.py`

---

**Document Version:** 1.0  
**Last Updated:** December 24, 2024  
**Author:** IFI Essay Gateway Development Team

