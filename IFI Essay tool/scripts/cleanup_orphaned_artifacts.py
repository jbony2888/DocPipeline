#!/usr/bin/env python3
"""
Clean up orphaned artifact directories.

Removes artifact directories that don't have corresponding database records.
This is safe because it only removes artifacts NOT in the database.
"""

from pathlib import Path
import shutil
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.database import get_db_records, init_database

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
        total_size = 0
        for d in orphaned[:10]:
            size = sum(f.stat().st_size for f in d.rglob('*') if f.is_file())
            total_size += size
            print(f"   • {d.name} ({size / 1024:.1f} KB)")
        if len(orphaned) > 10:
            # Calculate remaining size
            for d in orphaned[10:]:
                size = sum(f.stat().st_size for f in d.rglob('*') if f.is_file())
                total_size += size
            print(f"   ... and {len(orphaned) - 10} more")
        
        total_size_mb = total_size / (1024 * 1024)
        print(f"\n💾 Total space to free: {total_size_mb:.2f} MB")
        
        if not dry_run:
            confirm = input(f"\n⚠️  Delete {len(orphaned)} orphaned artifact directories? (yes/no): ")
            if confirm.lower() == "yes":
                for artifact_dir in orphaned:
                    shutil.rmtree(artifact_dir)
                    print(f"   Deleted {artifact_dir.name}")
                print(f"\n✅ Deleted {len(orphaned)} orphaned artifact directories")
                print(f"   Freed {total_size_mb:.2f} MB of disk space")
            else:
                print("❌ Cleanup cancelled")
        else:
            print("\n🔍 [DRY RUN] No files deleted.")
            print("   Run with --execute to actually delete files.")
    else:
        print("\n✅ No orphaned artifacts found. Database and artifacts are in sync.")

if __name__ == "__main__":
    dry_run = "--execute" not in sys.argv
    if dry_run:
        print("🔍 DRY RUN MODE")
        print("   Add --execute flag to actually delete files\n")
    cleanup_orphaned_artifacts(dry_run=dry_run)

