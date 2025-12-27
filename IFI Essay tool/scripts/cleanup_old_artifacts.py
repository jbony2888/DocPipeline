#!/usr/bin/env python3
"""
Clean up artifact directories older than specified days.

Uses metadata.json creation date if available,
otherwise falls back to directory modification time.
"""

from pathlib import Path
import shutil
from datetime import datetime, timedelta
import json
import sys

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
            except Exception:
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
        
        total_size_mb = total_size / (1024 * 1024)
        print(f"\n💾 Total space to free: {total_size_mb:.2f} MB")
        
        if not dry_run:
            confirm = input(f"\n⚠️  Delete {len(old_artifacts)} old artifact directories? (yes/no): ")
            if confirm.lower() == "yes":
                for artifact_dir, _ in old_artifacts:
                    shutil.rmtree(artifact_dir)
                print(f"\n✅ Deleted {len(old_artifacts)} old artifact directories")
                print(f"   Freed {total_size_mb:.2f} MB of disk space")
            else:
                print("❌ Cleanup cancelled")
        else:
            print("\n🔍 [DRY RUN] No files deleted.")
            print("   Run with --execute to actually delete files.")
    else:
        print(f"\n✅ No artifacts older than {days_old} days found.")

if __name__ == "__main__":
    # Parse arguments
    days = 365
    dry_run = True
    
    for arg in sys.argv[1:]:
        if arg == "--execute":
            dry_run = False
        elif arg.isdigit():
            days = int(arg)
    
    if dry_run:
        print("🔍 DRY RUN MODE")
        print(f"   Would delete artifacts older than {days} days")
        print("   Add --execute to actually delete files\n")
    
    cleanup_old_artifacts(days_old=days, dry_run=dry_run)

