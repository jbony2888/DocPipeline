"""
Import existing processed artifacts into the database.

Scans artifacts directory and imports all processed records.
"""

import json
import sys
from pathlib import Path
from pipeline.database import init_database, save_record
from pipeline.schema import SubmissionRecord
from pipeline.validate import validate_record


def import_artifacts(artifacts_dir: str = "artifacts"):
    """Import all artifacts from the artifacts directory into the database."""
    artifacts_path = Path(artifacts_dir)
    
    if not artifacts_path.exists():
        print(f"❌ Artifacts directory not found: {artifacts_dir}")
        return
    
    # Initialize database
    init_database()
    print(f"✅ Database initialized")
    
    # Find all artifact directories
    artifact_dirs = [d for d in artifacts_path.iterdir() if d.is_dir()]
    
    if not artifact_dirs:
        print(f"⚠️  No artifact directories found in {artifacts_dir}")
        return
    
    print(f"📁 Found {len(artifact_dirs)} artifact directories")
    
    imported = 0
    skipped = 0
    errors = 0
    
    for artifact_dir in artifact_dirs:
        try:
            # Read metadata.json
            metadata_path = artifact_dir / "metadata.json"
            if not metadata_path.exists():
                print(f"⚠️  Skipping {artifact_dir.name}: no metadata.json")
                skipped += 1
                continue
            
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            
            submission_id = metadata.get("submission_id") or artifact_dir.name
            original_filename = metadata.get("original_filename", "unknown")
            artifact_dir_str = str(artifact_dir)
            
            # Read structured.json
            structured_path = artifact_dir / "structured.json"
            if not structured_path.exists():
                print(f"⚠️  Skipping {submission_id}: no structured.json")
                skipped += 1
                continue
            
            with open(structured_path, "r", encoding="utf-8") as f:
                structured = json.load(f)
            
            # Read ocr.json for confidence
            ocr_confidence = None
            ocr_path = artifact_dir / "ocr.json"
            if ocr_path.exists():
                with open(ocr_path, "r", encoding="utf-8") as f:
                    ocr_data = json.load(f)
                    ocr_confidence = ocr_data.get("confidence_avg")
            
            # Read validation.json if exists (but we'll override needs_review)
            review_reason_codes = ""
            validation_path = artifact_dir / "validation.json"
            if validation_path.exists():
                with open(validation_path, "r", encoding="utf-8") as f:
                    validation = json.load(f)
                    review_reason_codes = validation.get("review_reason_codes", "")
            
            # Remove _ifi_metadata from structured data if present
            structured_clean = {k: v for k, v in structured.items() if k != "_ifi_metadata"}
            
            # Build partial record dict for validation
            partial_record = {
                "submission_id": submission_id,
                "artifact_dir": artifact_dir_str,
                "word_count": structured_clean.get("word_count", 0),
                "ocr_confidence_avg": ocr_confidence,
                **structured_clean
            }
            
            # Validate and create record (this will set needs_review=True by default)
            record, validation_report = validate_record(partial_record)
            
            # Override review_reason_codes with existing one if it exists, otherwise use new one
            if review_reason_codes:
                record.review_reason_codes = review_reason_codes
            
            # Save to database
            success = save_record(record, filename=original_filename)
            
            if success:
                print(f"✅ Imported: {submission_id} - {original_filename}")
                imported += 1
            else:
                print(f"❌ Failed to save: {submission_id}")
                errors += 1
                
        except Exception as e:
            print(f"❌ Error importing {artifact_dir.name}: {e}")
            errors += 1
    
    print("\n" + "="*50)
    print(f"📊 Import Summary:")
    print(f"   ✅ Imported: {imported}")
    print(f"   ⚠️  Skipped: {skipped}")
    print(f"   ❌ Errors: {errors}")
    print(f"   📁 Total: {len(artifact_dirs)}")
    print("="*50)


if __name__ == "__main__":
    artifacts_dir = sys.argv[1] if len(sys.argv) > 1 else "artifacts"
    import_artifacts(artifacts_dir)

