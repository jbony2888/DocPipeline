# DBF Remediation Implementation Plan

**Target:** DBF-STRONG Compliance  
**Timeline:** 6 Milestones  
**Status:** In Progress

---

## Milestones Overview

| Milestone | Goal | Files to Touch | Acceptance Criteria |
|-----------|------|----------------|---------------------|
| **M1** | Supabase Audit Writer | `pipeline/audit.py`, `pipeline/supabase_audit.py`, `supabase/migrations/006_audit_tables.sql` | Every submission has trace + events in Supabase |
| **M2** | Demote LLM Classification | `pipeline/classify.py`, `pipeline/extract_ifi.py` | doc_type_final never from LLM directly |
| **M3** | Determinism Hardening | `pipeline/extract_ifi.py`, `pipeline/schema.py`, `pipeline/runner.py` | Re-run yields identical outcomes |
| **M4** | Idempotency Enforcement | `jobs/process_submission.py`, `pipeline/supabase_db.py` | Duplicate uploads skip processing |
| **M5** | Safe Degradation | `pipeline/ocr.py`, `pipeline/validate.py`, `flask_app.py` | No crashes, explicit status model |
| **M6** | DBF Test Suite | `tests/test_dbf_compliance.py`, `tests/test_failure_injection.py` | All tests pass, assert audit calls |

---

## M1: Supabase Audit Writer

**New Files:**
- `pipeline/audit.py` - Audit trace building and event emission
- `pipeline/supabase_audit.py` - Supabase repository functions
- `supabase/migrations/006_audit_tables.sql` - Database schema

**Modified Files:**
- `pipeline/runner.py` - Call audit functions at each stage
- `flask_app.py` - Emit APPROVED/REJECTED events
- `jobs/process_submission.py` - Emit INGESTED, OCR_COMPLETE, etc.

**Acceptance:**
- Every submission has 1 trace row in `submission_audit_traces`
- Every stage emits event in `submission_audit_events`
- Approval creates APPROVED event

---

## M2: Demote LLM Classification

**New Files:**
- `pipeline/classify.py` - Deterministic classification rules

**Modified Files:**
- `pipeline/extract_ifi.py` - Remove authoritative classification from prompt, add verification
- `pipeline/runner.py` - Use verified doc_type_final

**Acceptance:**
- doc_type_final determined by code, not LLM
- Unverified signals defer to review with reason codes

---

## M3: Determinism Hardening

**Modified Files:**
- `pipeline/extract_ifi.py` - Set temperature=0, add caching
- `pipeline/schema.py` - Add LLM result cache schema
- `pipeline/runner.py` - Check cache before LLM call

**Acceptance:**
- Re-run produces identical doc_type_final
- Audit shows CACHED_LLM_RESULT event when reused

---

## M4: Idempotency Enforcement

**Modified Files:**
- `jobs/process_submission.py` - Check duplicate before processing
- `pipeline/supabase_db.py` - Return existing record if duplicate

**Acceptance:**
- Duplicate uploads skip OCR/LLM, return existing record
- DUPLICATE_SKIPPED event logged

---

## M5: Safe Degradation

**Modified Files:**
- `pipeline/ocr.py` - Return low-confidence result instead of raising
- `pipeline/validate.py` - Add escalation threshold (confidence < 0.3)
- `pipeline/schema.py` - Add status field
- `flask_app.py` - Handle errors gracefully

**Acceptance:**
- OCR errors don't crash, produce FAILED status + audit
- Low confidence (< 0.3) escalates with ESCALATED event

---

## M6: DBF Test Suite

**New Files:**
- `tests/test_dbf_compliance.py` - Invariant tests
- `tests/test_failure_injection.py` - Failure scenario tests

**Acceptance:**
- Tests assert audit insert calls occur
- Determinism, idempotency, failure injection tests pass

---

## Execution Order

1. **B) Database Work** - Create tables first
2. **M1** - Audit infrastructure
3. **M2** - Remove LLM authority
4. **M3** - Determinism
5. **M4** - Idempotency
6. **M5** - Safe degradation
7. **M6** - Tests

---

## Success Criteria

- All invariants (5.1-5.5) pass
- No anti-patterns remain
- Audit trail complete in Supabase
- Tests demonstrate compliance
