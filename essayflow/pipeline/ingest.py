"""
Ingestion module: handles file upload, storage, and metadata generation.
"""

import os
import uuid
from pathlib import Path
from datetime import datetime


def ingest_upload(
    uploaded_bytes: bytes,
    original_filename: str,
    base_artifacts_dir: str = "artifacts"
) -> dict:
    """
    Saves the uploaded file, generates a submission_id,
    creates an artifact directory, and returns metadata.
    
    Args:
        uploaded_bytes: Raw file bytes from upload
        original_filename: Original filename from user
        base_artifacts_dir: Base directory for artifacts
        
    Returns:
        dict with:
            - submission_id
            - artifact_dir
            - original_filename
            - saved_path
            - timestamp
    """
    # Generate unique submission ID
    submission_id = f"sub_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    # Create artifact directory
    artifact_dir = Path(base_artifacts_dir) / submission_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    # Save uploaded file
    file_ext = Path(original_filename).suffix.lower()
    saved_path = artifact_dir / f"original{file_ext}"
    
    with open(saved_path, "wb") as f:
        f.write(uploaded_bytes)
    
    return {
        "submission_id": submission_id,
        "artifact_dir": str(artifact_dir),
        "original_filename": original_filename,
        "saved_path": str(saved_path),
        "timestamp": datetime.now().isoformat()
    }

