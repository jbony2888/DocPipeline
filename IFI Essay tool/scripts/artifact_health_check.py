#!/usr/bin/env python3
"""
Check artifact directory health and integrity.

Reports:
- Missing required files
- Corrupted JSON files
- Size anomalies
- Orphaned artifacts
"""

from pathlib import Path
import json

def artifact_health_check(artifacts_dir="artifacts"):
    """
    Check artifact directory health and integrity.
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
            # Check for both .pdf and .jpg variants of original
            if req_file == "original.pdf":
                if not (artifact_dir / "original.pdf").exists() and not (artifact_dir / "original.jpg").exists():
                    missing.append("original.pdf/original.jpg")
            elif not (artifact_dir / req_file).exists():
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
    if len(artifact_dirs) > 0:
        print(f"   • Average size: {(total_size / len(artifact_dirs)) / 1024:.1f} KB per artifact")
    
    # Report issues
    if issues["missing_files"]:
        print(f"\n❌ Missing Files: {len(issues['missing_files'])} artifacts")
        for item in issues["missing_files"][:5]:
            print(f"   • {item['submission_id']}: {', '.join(item['missing'])}")
        if len(issues["missing_files"]) > 5:
            print(f"   ... and {len(issues['missing_files']) - 5} more")
    
    if issues["corrupted_json"]:
        print(f"\n❌ Corrupted JSON: {len(issues['corrupted_json'])} files")
        for item in issues["corrupted_json"][:5]:
            print(f"   • {item['submission_id']}: {item['file']}")
        if len(issues["corrupted_json"]) > 5:
            print(f"   ... and {len(issues['corrupted_json']) - 5} more")
    
    if issues["size_anomalies"]:
        print(f"\n⚠️  Size Anomalies: {len(issues['size_anomalies'])} artifacts")
        for item in issues["size_anomalies"][:5]:
            print(f"   • {item['submission_id']}: {item['size_kb']:.1f} KB ({item['reason']})")
        if len(issues["size_anomalies"]) > 5:
            print(f"   ... and {len(issues['size_anomalies']) - 5} more")
    
    if issues["empty_files"]:
        print(f"\n⚠️  Empty Files: {len(issues['empty_files'])} files")
        for item in issues["empty_files"][:5]:
            print(f"   • {item['submission_id']}: {item['file']}")
        if len(issues["empty_files"]) > 5:
            print(f"   ... and {len(issues['empty_files']) - 5} more")
    
    if valid_count == len(artifact_dirs):
        print(f"\n✅ All artifacts are healthy!")

if __name__ == "__main__":
    artifact_health_check()

