#!/usr/bin/env python3
"""
Create a compressed ZIP archive of all artifacts.

Features:
- Preserves directory structure
- Includes metadata manifest
- Progress reporting for large archives
- Compression to reduce storage
"""

from pathlib import Path
import zipfile
from datetime import datetime
import json
import sys

def archive_artifacts(artifacts_dir="artifacts", output_zip=None, include_metadata=True):
    """
    Create a compressed ZIP archive of all artifacts.
    
    Args:
        artifacts_dir: Path to artifacts directory
        output_zip: Output ZIP file path (default: artifacts_archive_YYYYMMDD_HHMMSS.zip)
        include_metadata: Whether to include ARCHIVE_MANIFEST.json in the archive
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
    
    if total_dirs == 0:
        print("❌ No artifact directories found")
        return
    
    manifest = {
        "archive_date": datetime.now().isoformat(),
        "total_submissions": total_dirs,
        "submissions": []
    }
    
    total_size = 0
    
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
                except Exception:
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
    
    # Write manifest to archive if requested
    if include_metadata:
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
    if include_metadata:
        print(f"   • Manifest: ARCHIVE_MANIFEST.json (included in archive)")

if __name__ == "__main__":
    output_file = sys.argv[1] if len(sys.argv) > 1 else None
    archive_artifacts(output_zip=output_file)

