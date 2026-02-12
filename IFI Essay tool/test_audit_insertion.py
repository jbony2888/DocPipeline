"""
Simple script to test audit insertion directly.
Run this after verifying Supabase connection works.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def test_audit_insertion():
    """Test inserting audit trace and event to Supabase."""
    
    # Check environment
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        print("   Set them in your environment or .env file")
        return False
    
    print("🔍 Testing audit insertion to Supabase...")
    print(f"   Supabase URL: {supabase_url[:30]}...")
    print()
    
    try:
        from pipeline.audit import build_decision_trace
        from pipeline.supabase_audit import insert_audit_trace, insert_audit_event
        
        # Build test trace
        trace = build_decision_trace(
            submission_id="local_test_001",
            filename="test_local.pdf",
            owner_user_id="test-user-local",
            ocr_result={
                "confidence_avg": 0.65,
                "text": "Name: Test Student\nSchool: Test School",
                "lines": ["Name: Test Student", "School: Test School"]
            },
            extracted_fields={
                "student_name": "Test Student",
                "school_name": "Test School",
                "grade": 5
            },
            validation_result={
                "needs_review": True,
                "review_reason_codes": "PENDING_REVIEW"
            },
            rules_applied=[
                {
                    "rule_id": "required_student_name",
                    "description": "student_name is required",
                    "params": {},
                    "evaluated": "Test Student",
                    "result": True,
                    "triggered": False
                }
            ]
        )
        
        # Insert trace
        print("📝 Inserting audit trace...")
        trace_result = insert_audit_trace(
            submission_id="local_test_001",
            owner_user_id="test-user-local",
            trace_dict=trace
        )
        
        if trace_result:
            print("✅ Audit trace inserted successfully")
        else:
            print("❌ Audit trace insertion failed")
            return False
        
        # Insert event
        print("📝 Inserting audit event...")
        event_result = insert_audit_event(
            submission_id="local_test_001",
            actor_role="system",
            event_type="TEST_EVENT",
            event_payload={"test": True, "local": True}
        )
        
        if event_result:
            print("✅ Audit event inserted successfully")
        else:
            print("❌ Audit event insertion failed")
            return False
        
        print()
        print("=" * 60)
        print("✅ Audit insertion test passed!")
        print("=" * 60)
        print()
        print("Verify in Supabase:")
        print(f"  SELECT * FROM submission_audit_traces WHERE submission_id = 'local_test_001';")
        print(f"  SELECT * FROM submission_audit_events WHERE submission_id = 'local_test_001';")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print()
        print("This may be a Pydantic version issue.")
        print("Try: pip install 'pydantic>=2.0' 'supabase>=2.0'")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_audit_insertion()
    sys.exit(0 if success else 1)
