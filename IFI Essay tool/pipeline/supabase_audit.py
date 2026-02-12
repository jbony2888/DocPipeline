"""
Supabase audit repository functions for DBF compliance.
Handles insertion of audit traces and events.
"""

import os
from typing import Optional, Dict, Any
from datetime import datetime
from auth.supabase_client import get_supabase_client
from supabase import create_client


def insert_audit_trace(
    submission_id: str,
    owner_user_id: Optional[str],
    trace_dict: Dict[str, Any],
    access_token: Optional[str] = None
) -> bool:
    """
    Insert an audit trace into submission_audit_traces.
    
    Args:
        submission_id: Submission identifier
        owner_user_id: User who owns the submission
        trace_dict: Dictionary with input, signals, rules_applied, outcome, errors
        access_token: Optional access token for authenticated insert
        
    Returns:
        True if successful, False otherwise (never raises)
    """
    try:
        # Use service role key for system inserts (bypasses RLS)
        supabase_url = os.environ.get("SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if service_key and supabase_url:
            admin_client = create_client(supabase_url, service_key)
        else:
            # Fallback to authenticated client
            admin_client = get_supabase_client(access_token=access_token)
            if not admin_client:
                print(f"⚠️ Warning: Could not insert audit trace for {submission_id} - no Supabase client")
                return False
        
        # Prepare trace record
        trace_record = {
            "submission_id": submission_id,
            "owner_user_id": owner_user_id,
            "trace_version": trace_dict.get("trace_version", "dbf-audit-v1"),
            "input": trace_dict.get("input", {}),
            "signals": trace_dict.get("signals", {}),
            "rules_applied": trace_dict.get("rules_applied", []),
            "outcome": trace_dict.get("outcome", {}),
            "errors": trace_dict.get("errors", [])
        }
        
        # Insert (always insert new trace per run, don't upsert)
        result = admin_client.table("submission_audit_traces").insert(trace_record).execute()
        
        return True
        
    except Exception as e:
        # Never block pipeline on audit failure - log and continue
        print(f"⚠️ Warning: Failed to insert audit trace for {submission_id}: {e}")
        import traceback
        traceback.print_exc()
        return False


def insert_audit_event(
    submission_id: str,
    actor_role: str,
    event_type: str,
    event_payload: Optional[Dict[str, Any]] = None,
    actor_user_id: Optional[str] = None,
    access_token: Optional[str] = None
) -> bool:
    """
    Insert an audit event into submission_audit_events.
    
    Args:
        submission_id: Submission identifier
        actor_role: 'system', 'reviewer', or 'admin'
        event_type: Event type (INGESTED, OCR_COMPLETE, APPROVED, etc.)
        event_payload: Optional payload dictionary
        actor_user_id: Optional user ID if actor is a user
        access_token: Optional access token for authenticated insert
        
    Returns:
        True if successful, False otherwise (never raises)
    """
    try:
        # Use service role key for system inserts
        supabase_url = os.environ.get("SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if service_key and supabase_url:
            admin_client = create_client(supabase_url, service_key)
        else:
            admin_client = get_supabase_client(access_token=access_token)
            if not admin_client:
                print(f"⚠️ Warning: Could not insert audit event for {submission_id} - no Supabase client")
                return False
        
        # Prepare event record
        event_record = {
            "submission_id": submission_id,
            "actor_user_id": actor_user_id,
            "actor_role": actor_role,
            "event_type": event_type,
            "event_payload": event_payload or {}
        }
        
        # Insert event
        result = admin_client.table("submission_audit_events").insert(event_record).execute()
        
        return True
        
    except Exception as e:
        # Never block pipeline on audit failure
        print(f"⚠️ Warning: Failed to insert audit event for {submission_id}: {e}")
        import traceback
        traceback.print_exc()
        return False
