# EssayFlow (IFI Essay Tool) — Project Outline & Features

A short reference for architecture, features, and current state.

---

## 1. What It Is

- **Name:** EssayFlow (IFI Essay Gateway / DocPipeline)
- **Purpose:** Turn handwritten IFI Fatherhood Essay Contest submissions into structured, searchable data.
- **Stack:** Python, Flask, Supabase (DB + Auth + Storage), Redis/RQ, Google Vision OCR, Groq LLM.
- **Deploy:** Render (production), Docker Compose (local). Flask UI (not Streamlit).

---

## 2. High-Level Architecture

```
Upload (Flask) → Ingest → OCR (Google Vision) → Segment → Extract (LLM + rules) → Validate → Persist (Supabase/CSV) → Human Review → Approve/Reject
```

- **Ingest:** `pipeline/ingest.py` — submission_id, artifact dir, save file (Supabase Storage).
- **OCR:** `pipeline/ocr.py` — Google Vision (or EasyOCR/stub), confidence, `OcrResult` (incl. `ocr_failed`).
- **Segment:** `pipeline/segment.py` — split contact block vs essay block.
- **Extract:** `pipeline/extract_ifi.py`, `extract_llm.py` — LLM + rules; deterministic verification in `classify.py` and field checks.
- **Validate:** `pipeline/validate.py` — required fields, word count, confidence thresholds, reason codes (e.g. `OCR_FAILED`, `LOW_CONFIDENCE`, `ESCALATED`).
- **Persist:** `pipeline/supabase_db.py`, `csv_writer.py` — Supabase rows, optional CSV; status: PENDING_REVIEW / PROCESSED / APPROVED / FAILED.
- **Audit:** `pipeline/audit.py`, `pipeline/supabase_audit.py` — decision traces and events in Supabase (DBF).
- **Orchestration:** `pipeline/runner.py` — runs stages, builds trace, calls Supabase audit.
- **Jobs:** `jobs/redis_queue.py`, `jobs/process_submission.py` — enqueue and process submissions; duplicate check → skip + `DUPLICATE_SKIPPED` when applicable.

---

## 3. Features

### Upload & Processing
- Single and multi-file upload (PDF/PNG/JPG).
- Background processing via Redis/RQ; optional embedded worker (e.g. Render) or standalone `worker_rq.py`.
- Multi-entry PDFs: `pipeline/pdf_splitter.py` (PyMuPDF) splits and processes per entry.
- Processing status and job polling in the UI.

### Data Extraction
- **OCR:** Google Cloud Vision (primary), EasyOCR/stub options; confidence scoring; on failure: `ocr_failed=True`, confidence 0, `OCR_FAILED` reason code.
- **LLM:** Groq (Llama) for field extraction and OCR correction; temperature=0; classification is advisory only — final doc type from `classify.py`.
- **Deterministic verification:** `classify.py` (doc type), `verify_extracted_fields()` (e.g. student name, school, grade present in OCR text).
- **Segmentation:** Contact block vs essay block; word count and basic metrics.

### Review & Approval
- Filter by status / needs_review; view original PDF and extracted data.
- Inline edit; approve/reject; batch grouping by school.
- Approval sets status=APPROVED and writes `APPROVED` audit event (Supabase).
- Deterministic gating (`can_approve_record`) before approval.

### Persistence & Export
- **Supabase:** submissions table (with status), storage for PDFs; audit tables: `submission_audit_traces`, `submission_audit_events`.
- Optional CSV export of approved records.
- Artifacts per submission (e.g. OCR, structured JSON, validation, optional `decision_log.json`); Supabase is source of truth for audit.

### Security & Auth
- Supabase Auth (e.g. magic link); user-scoped data where applicable.
- Credentials via env (e.g. `.env`); no secrets in repo.

### DBF (Decision Boundary Framework) Compliance
- **Audit:** Every run → trace row; major stages → event rows (e.g. INGESTED, OCR_COMPLETE, EXTRACTION_COMPLETE, VALIDATION_COMPLETE, SAVED, APPROVED, DUPLICATE_SKIPPED, ERROR).
- **No unverified action:** Irreversible “action” = APPROVED/downstream publish; persistence and audit logging allowed before approval.
- **Determinism:** temperature=0; doc type and field verification in code.
- **Idempotency:** Duplicate submission check; skip and `DUPLICATE_SKIPPED` when already PROCESSED/APPROVED.
- **Safe degradation:** OCR/LLM failures don’t crash job; `OCR_FAILED` vs `LOW_CONFIDENCE`; escalation (e.g. very low confidence) and ERROR events.

---

## 4. Key Repo Paths

| Area | Paths |
|------|--------|
| App entry | `flask_app.py` |
| Pipeline | `pipeline/runner.py`, `ingest.py`, `ocr.py`, `segment.py`, `extract_ifi.py`, `extract_llm.py`, `classify.py`, `validate.py`, `schema.py` |
| Persistence | `pipeline/supabase_db.py`, `supabase_storage.py`, `csv_writer.py` |
| Audit (DBF) | `pipeline/audit.py`, `pipeline/supabase_audit.py` |
| Jobs | `jobs/queue.py`, `redis_queue.py`, `process_submission.py` |
| Worker | `worker_rq.py` |
| Auth | `auth/`, `auth_callback.py` |
| DB schema | `supabase/migrations/` (e.g. `006_audit_tables.sql`) |
| Tests | `tests/test_dbf_compliance.py`, `tests/test_failure_injection.py`, others under `tests/` |
| Docs | `docs/PROJECT_OVERVIEW.md`, `docs/pipeline/architecture.md`, `docs/bdf/` |

---

## 5. How to Run the Project

### Option A: Docker (recommended)

1. **One-time:** Copy `.env.example` to `.env` in `IFI Essay tool` and fill in your keys (Supabase, Groq, Redis URL, etc.).
2. From the **IFI Essay tool** directory:
   ```bash
   cd "IFI Essay tool"
   docker compose up -d
   ```
3. Open **http://localhost:5000** in your browser.
4. To rebuild after code changes: `docker compose build --no-cache && docker compose up -d`.

### Option B: Local (no Docker)

1. **One-time:** Create `.env` in `IFI Essay tool` (see `.env.example`). Install deps: `pip install -r requirements-flask.txt` and `pip install PyMuPDF`.
2. Start **Redis** (e.g. `redis-server` or use a cloud Redis URL in `.env`).
3. Start the **Flask app** (from `IFI Essay tool`):
   ```bash
   cd "IFI Essay tool"
   FLASK_PORT=5000 python flask_app.py
   ```
   Or: `./START_FLASK_APP.sh` (uses port from `.env` or 5000).
4. Open **http://localhost:5000**. The app can start an embedded worker; if port 5000 is in use, try `FLASK_PORT=5001 python flask_app.py`.
5. **Optional:** Run the worker in a separate terminal so jobs are processed even if the embedded worker has issues:
   ```bash
   cd "IFI Essay tool"
   python worker_rq.py
   ```

### Run / Test (Quick Reference)

- **DBF tests:** `cd "IFI Essay tool"` then `pytest tests/test_dbf_compliance.py tests/test_failure_injection.py -v`.
- **Migrations:** Apply `supabase/migrations/*.sql` in order (e.g. in Supabase dashboard or CLI).

### Troubleshooting: "Nothing saved" / Redis

- **Is Redis running?**
  - **Docker:** `docker compose ps` — `redis`, `flask-app`, and `worker` should be Up. If Redis or worker are stopped, run `docker compose up -d`.
  - **Local:** From `IFI Essay tool` run `python test_redis_connection.py`. If it fails, start Redis (e.g. `redis-server`) or set `REDIS_URL` in `.env` to a cloud Redis URL.
- **Is the worker processing jobs?**
  - **Docker:** `docker compose logs worker` — look for "Listening on submissions" and any errors during job run (e.g. Supabase save errors).
  - **Local:** If you only run `python flask_app.py`, the embedded worker may be running; otherwise start `python worker_rq.py` in a second terminal.
- **Why might saves fail?**
  - Missing or wrong `.env`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` must be set so the worker can write to Supabase.
  - RLS: If using anon key + user token, the token might be expired in the worker; the app uses the service role for duplicate checks and can use it for writes if needed.
- **Quick Redis check:** `cd "IFI Essay tool"` then `python test_redis_connection.py`.
- **Make sure Groq is running (LLM extraction):** Groq is a cloud API; the app does not "run" it locally. Ensure `GROQ_API_KEY` is set and valid. From `IFI Essay tool` run `python test_api_keys.py` (load `.env` first if needed: `set -a && . .env && set +a` then run the script). In Docker, `GROQ_API_KEY` is passed via `.env`; confirm it’s set and that `docker compose` loads it.
- **Nothing gets processed (Docker):** Flask and Worker must use the same Redis (same `REDIS_URL` in `.env`). Old failed jobs (e.g. from embedded-worker signal error) stay in the queue as "failed" but don’t block new jobs. To clear failed jobs: inside worker container run `python -c "from rq.registry import FailedJobRegistry; from jobs.redis_queue import get_queue; q=get_queue(); FailedJobRegistry(queue=q).empty()"`. Then upload again and watch `docker compose logs worker -f`.

---

## 6. Current State Summary

- **UI:** Flask on port 5000 (configurable); dashboard, upload, review, approval.
- **Pipeline:** Ingest → OCR → Segment → Extract (LLM + verify) → Validate → Persist + Audit; status and reason codes (including `OCR_FAILED`, escalation) implemented.
- **DBF:** DBF-STRONG targeted: Supabase audit tables, deterministic verification, idempotency, safe degradation, and tests in place.
- **Dependencies:** PyMuPDF (`fitz`) required for PDF splitting when using multi-entry or PDF uploads; Redis required for queue/worker.

This outline is a snapshot; for full architecture and DBF details see `docs/PROJECT_OVERVIEW.md`, `docs/pipeline/architecture.md`, and `docs/bdf/`.
