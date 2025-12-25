"""
Ingestion module: handles file upload, storage, and metadata generation.
"""

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime


def ingest_upload(
    uploaded_bytes: bytes,
    original_filename: str,
    base_artifacts_dir: str = "artifacts"
) -> dict:
    """
    Saves the uploaded file with deterministic submission_id based on file contents.
    Creates artifact directory and writes metadata.json.
    
    Args:
        uploaded_bytes: Raw file bytes from upload
        original_filename: Original filename from user
        base_artifacts_dir: Base directory for artifacts
        
    Returns:
        dict with:
            - submission_id: First 12 chars of SHA256 hash (deterministic)
            - artifact_dir: Path to created artifact directory
            - original_path: Path to saved original file
    """
    # Compute deterministic submission_id from SHA256 hash
    sha256_hash = hashlib.sha256(uploaded_bytes).hexdigest()
    submission_id = sha256_hash[:12]
    byte_size = len(uploaded_bytes)
    
    # Create artifact directory
    artifact_dir = Path(base_artifacts_dir) / submission_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine file extension (with fallback)
    file_ext = Path(original_filename).suffix.lower()
    if not file_ext:
        file_ext = ".bin"
    
    # Save uploaded file as original.<ext>
    stored_filename = f"original{file_ext}"
    original_path = artifact_dir / stored_filename
    
    with open(original_path, "wb") as f:
        f.write(uploaded_bytes)
    
    # Create metadata.json
    metadata = {
        "submission_id": submission_id,
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "original_path": str(original_path),
        "artifact_dir": str(artifact_dir),
        "byte_size": byte_size,
        "sha256": sha256_hash,
        "created_at": datetime.now().isoformat()
    }
    
    metadata_path = artifact_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    
    return {
        "submission_id": submission_id,
        "artifact_dir": str(artifact_dir),
        "original_path": str(original_path)
    }

