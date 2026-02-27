"""
Supabase Storage for file uploads.
Saves files to the 'essay-submissions' bucket.
"""

import os
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from auth.supabase_client import get_supabase_client
from storage3.exceptions import StorageApiError


BUCKET_NAME = "essay-submissions"


def upload_file(
    file_bytes: bytes,
    file_path: str,
    content_type: Optional[str] = None,
    access_token: Optional[str] = None
) -> Dict:
    """
    Upload a file to Supabase Storage bucket.
    
    Args:
        file_bytes: File content as bytes
        file_path: Path within the bucket (e.g., "submission_id/original.pdf")
        content_type: MIME type (e.g., "application/pdf", "image/png")
        
    Returns:
        dict with:
            - success: bool
            - url: Public URL if successful
            - path: Path in bucket
            - error: Error message if failed
    """
    try:
        # Create client and apply bearer token (if provided) for storage RLS.
        supabase = get_supabase_client(access_token=access_token)
        
        # Upload to storage
        result = supabase.storage.from_(BUCKET_NAME).upload(
            path=file_path,
            file=file_bytes,
            file_options={
                "content-type": content_type or "application/octet-stream",
                "upsert": "true"  # Overwrite if exists
            }
        )
        
        # Get public URL
        url_result = supabase.storage.from_(BUCKET_NAME).get_public_url(file_path)
        
        return {
            "success": True,
            "url": url_result,
            "path": file_path
        }
    except Exception as e:
        print(f"❌ Error uploading file to Supabase Storage: {e}")
        return {
            "success": False,
            "error": str(e),
            "path": file_path
        }


def ingest_upload_supabase(
    uploaded_bytes: bytes,
    original_filename: str,
    owner_user_id: str,
    access_token: Optional[str] = None
) -> Dict:
    """
    Save uploaded file to Supabase Storage and create metadata.
    
    Args:
        uploaded_bytes: Raw file bytes from upload
        original_filename: Original filename from user
        owner_user_id: User ID who uploaded the file
        
    Returns:
        dict with:
            - submission_id: First 12 chars of SHA256 hash
            - artifact_dir: Path prefix in bucket
            - original_path: Full path in bucket
            - storage_url: Public URL to file
    """
    # Compute deterministic submission_id from SHA256 hash
    sha256_hash = hashlib.sha256(uploaded_bytes).hexdigest()
    submission_id = sha256_hash[:12]
    
    # Determine file extension
    file_ext = Path(original_filename).suffix.lower()
    if not file_ext:
        file_ext = ".bin"
    
    # Create path in bucket: owner_user_id/submission_id/original.ext
    artifact_dir = f"{owner_user_id}/{submission_id}"
    file_path = f"{artifact_dir}/original{file_ext}"
    
    # Determine content type
    content_type_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    content_type = content_type_map.get(file_ext, "application/octet-stream")
    
    # Upload to Supabase Storage
    upload_result = upload_file(
        file_bytes=uploaded_bytes,
        file_path=file_path,
        content_type=content_type,
        access_token=access_token
    )
    
    if not upload_result["success"]:
        raise Exception(f"Failed to upload file to Supabase Storage: {upload_result.get('error')}")
    
    return {
        "submission_id": submission_id,
        "artifact_dir": artifact_dir,
        "original_path": file_path,
        "storage_url": upload_result["url"],
        "sha256": sha256_hash,
        "created_at": datetime.now().isoformat()
    }


def download_file(file_path: str, access_token: Optional[str] = None) -> Optional[bytes]:
    """
    Download a file from Supabase Storage.
    
    Args:
        file_path: Path in bucket (e.g., "user_id/submission_id/original.pdf")
        access_token: Optional access token for authenticated requests (required for RLS)
        
    Returns:
        File bytes or None if error
    """
    try:
        # Create client and apply bearer token (if provided) for storage RLS.
        supabase = get_supabase_client(access_token=access_token)
        
        result = supabase.storage.from_(BUCKET_NAME).download(file_path)
        return result
    except StorageApiError as e:
        if getattr(e, "code", None) == "not_found" or str(e).lower().find("not_found") >= 0:
            print(f"⚠️ File not found in Supabase Storage: {file_path}")
            return None
        print(f"❌ Error downloading file from Supabase Storage: {e}")
        import traceback
        print(traceback.format_exc())
        return None
    except Exception as e:
        print(f"❌ Error downloading file from Supabase Storage: {e}")
        import traceback
        print(traceback.format_exc())
        return None


def delete_file(file_path: str) -> bool:
    """
    Delete a file from Supabase Storage.
    
    Args:
        file_path: Path in bucket
        
    Returns:
        True if successful
    """
    try:
        supabase = get_supabase_client()
        result = supabase.storage.from_(BUCKET_NAME).remove([file_path])
        return True
    except Exception as e:
        print(f"❌ Error deleting file from Supabase Storage: {e}")
        return False


def _list_all_paths(sb, bucket: str, prefix: str) -> list:
    """Recursively list all file paths under a prefix. Requires service-role client."""
    paths = []
    try:
        result = sb.storage.from_(bucket).list(prefix or None, {"limit": 1000})
    except Exception:
        return paths
    for item in result or []:
        name = item.get("name", "")
        if not name:
            continue
        full_path = f"{prefix}/{name}" if prefix else name
        try:
            children = sb.storage.from_(bucket).list(full_path, {"limit": 1})
            if children:
                paths.extend(_list_all_paths(sb, bucket, full_path))
                continue
        except Exception:
            pass
        paths.append(full_path)
    return paths


def delete_artifact_dir(artifact_dir: str, supabase_client) -> bool:
    """
    Delete all files in storage under artifact_dir (e.g. user_id/submission_id).
    Use when deleting a submission so storage is cleaned up.
    
    Args:
        artifact_dir: Path prefix in bucket (e.g. "user_id/sub_id" or "user_id/run_id/artifacts/...")
        supabase_client: Supabase client with service role (for storage admin)
        
    Returns:
        True if successful or nothing to delete, False on error
    """
    if not artifact_dir or not artifact_dir.strip():
        return True
    try:
        normalized = artifact_dir.strip().rstrip("/")
        parts = [p for p in normalized.split("/") if p]

        # Delete the provided prefix and, for chunk-level paths, also delete the
        # run root (<owner>/<run_id>) where original uploads and analysis files live.
        prefixes = [normalized]
        if len(parts) >= 2 and "/artifacts/" in normalized:
            run_root = f"{parts[0]}/{parts[1]}"
            if run_root not in prefixes:
                prefixes.append(run_root)

        to_delete = []
        for prefix in prefixes:
            to_delete.extend(_list_all_paths(supabase_client, BUCKET_NAME, prefix))

        unique_paths = sorted(set(to_delete))
        if not unique_paths:
            return True

        for i in range(0, len(unique_paths), 100):
            batch = unique_paths[i : i + 100]
            supabase_client.storage.from_(BUCKET_NAME).remove(batch)
        return True
    except Exception as e:
        print(f"❌ Error deleting artifact dir {artifact_dir}: {e}")
        return False


def get_file_url(file_path: str, access_token: Optional[str] = None) -> Optional[str]:
    """
    Get public URL for a file in Supabase Storage.
    
    Args:
        file_path: Path in bucket
        access_token: Optional access token for authenticated requests (required for RLS)
        
    Returns:
        Public URL or None if error
    """
    try:
        # Create client and apply bearer token (if provided) for storage RLS.
        supabase = get_supabase_client(access_token=access_token)
        
        result = supabase.storage.from_(BUCKET_NAME).get_public_url(file_path)
        return result
    except Exception as e:
        print(f"❌ Error getting file URL from Supabase Storage: {e}")
        return None
