# Context: 8 Failed – Why and What to Check (paste into another chat)

## What this project does

- **IFI Essay tool** (inside DocPipeline repo): Flask app + Redis/RQ worker process essay PDFs.
- **Flow**: Upload → Supabase Storage → worker runs `process_submission_job` → OCR (Google Vision) → extraction (Groq LLM or fallback) → validation → save to Supabase `submissions` table.
- **Ways to run**: (1) **Batch script** `scripts/batch_process_to_db.py --input-dir ... --pattern "*.pdf"` (runs job in-process, no queue), (2) **UI upload** (enqueues job to Redis; worker picks it up).

---

## Why things fail (and what we fixed)

### 1. Batch script: all files fail at “upload to Supabase”

- **Error**: `Failed to upload file to Supabase Storage: [Errno 8] nodename nor servname provided, or not known`
- **Cause**: DNS/network from the machine running the batch script (can’t resolve Supabase host). Often when running the script without network or with wrong env (e.g. `.env` not loaded, or different shell).
- **Fix**: Run batch with network; load `.env` (e.g. from project root, or `python -c "from dotenv import load_dotenv; load_dotenv()"` then run script). Confirm `SUPABASE_URL` is set and reachable (e.g. `curl` the URL).

### 2. Worker (Docker): Groq 401 – jobs still complete

- **Log**: `IFI LLM extraction failed: Error code: 401 - {'error': {'message': 'Invalid API Key', ...}}`
- **Cause**: `GROQ_API_KEY` in Docker not set or invalid. Pipeline falls back to non-LLM extraction; job usually **succeeds** (record saved).
- **Fix**: Set valid `GROQ_API_KEY` in `.env` and ensure Docker gets it (`env_file: .env` in docker-compose; restart containers).

### 3. Save to DB fails (records with missing name/school/grade)

- **Error**: e.g. null value in column `school_source` / `grade_source` / `teacher_source`, or “column does not exist”.
- **Cause**: Supabase migration 005 adds NOT NULL columns; payload must include them. Records with missing student_name/school/grade are **intended** to be saved and flagged (needs_review), not rejected.
- **Fix (already in code)**: `pipeline/supabase_db.py` `save_record()` now adds `school_source`, `grade_source`, `teacher_source` with value `"extracted"` if missing; on “column does not exist” it retries without those keys for older schemas. Failed save returns `error` in result so job status shows the real DB error.

### 4. Missing name / grade / school should be “processed and flagged”, not “failed”

- **Intent**: tc06 (missing grade), tc07 (missing name), tc08 (missing school) should **succeed** and appear in UI as “Needs Review” with codes like MISSING_GRADE, MISSING_STUDENT_NAME, MISSING_SCHOOL_NAME.
- **Fix (already in code)**: Validation sets `needs_review` and `review_reason_codes`; we never treat “missing required field” as a hard failure. DB allows null for student_name, school_name, grade.

---

### 5. Real run (UI + Docker): all jobs failed, 0 records on dashboard

- **Symptom**: You upload via the UI; every job shows failed; Dashboard shows 0 Total Records (no records saved).
- **What to do**: Run `docker compose logs worker` from the `IFI Essay tool` directory and look for the first `FAILED processing` line and the exception after it. Common causes: (A) "Failed to upload file to Supabase Storage" or "nodename nor servname" = worker cannot reach Supabase (check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in `.env`, restart with `docker compose up -d --force-recreate`); (B) save_record error (column missing / null) = run Supabase migration or fix schema; (C) "Could not initialize Supabase client" = `.env` not loaded in container (ensure `env_file: .env` and `.env` next to docker-compose.yml). The job status page in the UI shows the same error for each failed job.

---

## Where to see what failed

- **Batch run**:  
  - `logs/batch_process_<timestamp>.summary.json` → `failed_count`, `failed_files`.  
  - `logs/batch_process_<timestamp>.jsonl` → per-file `status` and `error`.  
  - `logs/batch_process_<timestamp>.failed.txt` → one filename per line (if that run had failures).
- **Worker (Docker)**:  
  - `docker compose logs worker` or `logs/processing.log` (if you tee’d worker output).  
  - Look for `FAILED document: <filename> (job …): <error>`.
- **Job status UI**: Failed job shows filename and error (we added `failed_document` and `filename` to the status response).

---

## If “8 failed” is a new run

- **Batch of 8 files (e.g. tc01–tc08)**: Check the **latest** `logs/batch_process_*.summary.json` and `*.jsonl` (or `*.failed.txt`) for that run. Same failure modes apply: upload (Supabase/DNS), save_record (DB), or exception in pipeline.
- **8 jobs from UI**: Check worker logs and job status API for each job’s `error` and `failed_document`/`filename`.

---

## Key code paths (for debugging in another chat)

| What | Where |
|------|--------|
| Batch process, one PDF at a time | `scripts/batch_process_to_db.py` |
| Job entrypoint | `jobs/process_submission.py` → `process_submission_job()` |
| Upload to Supabase Storage | `pipeline/supabase_storage.py` → `ingest_upload_supabase()` |
| Full pipeline (OCR → extract → validate) | `pipeline/runner.py` → `process_submission()` |
| Validation (needs_review, review_reason_codes) | `pipeline/validate.py` → `validate_record()` |
| Save to DB (with source columns fallback) | `pipeline/supabase_db.py` → `save_record()` |
| Worker (RQ) | `worker_rq.py`; logs “FAILED document: …” on failure |
| Env check (no placeholders) | `scripts/ensure_api_keys.py` (read-only check) |
| Env check (all keys) | `scripts/check_env.py` |

---

## One-line summary for the other chat

“IFI Essay tool: 8 submissions failed. Need to find why — check batch logs (`logs/batch_process_*.jsonl` / `*.summary.json` / `*.failed.txt`) or worker logs (`docker compose logs worker`). Failures are usually: (1) batch upload to Supabase fails with ‘nodename nor servname’ (DNS/network), (2) worker Groq 401 (invalid key; job may still complete with fallback), (3) save_record DB error (we added school_source/grade_source/teacher_source and retry without them if column missing). Missing name/grade/school should be processed and flagged, not failed. Key code: `jobs/process_submission.py`, `pipeline/runner.py`, `pipeline/supabase_db.py`, `pipeline/validate.py`.”
