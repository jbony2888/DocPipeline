"""
Helpers for persisting document processing performance metrics to Supabase.
"""

import os
from typing import Any, Dict

from auth.supabase_client import normalize_supabase_url


def _get_service_role_client():
    """Create a Supabase client using service role credentials."""
    from supabase import create_client as create_supabase_client

    supabase_url = normalize_supabase_url(os.environ.get("SUPABASE_URL"))
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        return None
    return create_supabase_client(supabase_url, service_key)


def save_processing_metric(metric: Dict[str, Any]) -> bool:
    """
    Insert one row into processing_metrics.
    Returns False on failure (best-effort telemetry, never block pipeline).
    """
    try:
        supabase = _get_service_role_client()
        if not supabase:
            print("⚠️ Metrics skipped: missing Supabase service-role configuration")
            return False

        payload = dict(metric)
        payload["status"] = (payload.get("status") or "success").strip().lower()
        payload["filename"] = (payload.get("filename") or "").strip() or None
        payload["error_message"] = (payload.get("error_message") or "").strip() or None

        supabase.table("processing_metrics").insert(payload).execute()
        return True
    except Exception as e:
        print(f"⚠️ Failed to save processing metric: {e}")
        return False
