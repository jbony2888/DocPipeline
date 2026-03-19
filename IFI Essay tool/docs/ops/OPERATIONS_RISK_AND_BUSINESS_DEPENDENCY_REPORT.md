# Operations, Risk & Business Dependency Report

**IFI Essay Gateway (DocPipeline)**  
**Audience:** Stakeholders where outcomes affect budget, contest integrity, or legal exposure.  
**Source:** Repository inspection (Flask app, worker, Supabase migrations, pipeline, existing cost docs).  
**Disclaimer:** This is a technical assessment, not legal or financial advice.

---

## 1. Executive summary

This system **ingests IFI Fatherhood Essay Contest PDFs/images**, runs **OCR (typically Google Cloud Vision)** and **LLM extraction (typically Groq)**, and stores **structured rows in Supabase Postgres** plus **files and JSON audit artifacts in Supabase Storage**.

**If money or reputation depends on this stack, the critical truths are:**

| Topic | Finding |
|--------|---------|
| **Official “submission” count** | **`submissions` table** is the operational system of record. It can contain **multiple rows per uploaded file** (chunks, retries, multi-student PDFs). **Do not equate row count with unique contest entries** without deduplication rules. |
| **Eligibility / quality** | **Automated extraction is not authoritative.** `needs_review` and `review_reason_codes` flag gaps; **human review and export** remain the gate for “clean” lists. |
| **Audit trail** | **Telemetry:** `processing_metrics` (Postgres). **Detail:** JSON files in Storage (`pipeline_log.json`, `traceability.json`, `ocr_summary.json`, etc.). **Queue:** `jobs` table. There is **no single table named `audit_logs`**. |
| **Runaway cost risk** | Costs scale with **Vision pages** and **Groq tokens** per processed unit; chunked PDFs can **increase Vision calls**. See §6. |
| **Availability** | Depends on **Render (or similar)**, **Supabase**, **Redis** (optional; sync fallback exists), **worker process**, and **third-party APIs** (Vision, Groq). |

---

## 2. What the business should treat as authoritative

### 2.1 For “how many essays did we receive?”

- **Raw technical count:** Rows in `public.submissions` (subject to RLS per user; admins/service role see all).
- **Caveat:** One upload can produce **several rows** because:
  - **Bulk / multi-page batch** classification splits a PDF into **one row per chunk** (`make_chunk_submission_id`, `jobs/process_submission.py`).
  - **Re-uploads** and **upserts** on the same `submission_id` update a row but **different parent runs** can still appear as separate chunk IDs.
  - **Multi-entry PDFs** (e.g. one file, many students) intentionally create **one row per extracted student**.

**Recommendation for finance/contest reporting:** Define a **reporting rule** (e.g. “count distinct `(owner_user_id, filename, parent run)`” or “only `needs_review = false` after coordinator sign-off”) and document it. The admin UI **loads up to 1000 recent rows**; it is **not** a full historical census.

### 2.2 For “which submissions are acceptable?”

- Use **`needs_review = false`** after your process treats **approved** records as final, **plus** any manual checks you require.
- **`review_reason_codes`** explain why something stayed in review (missing fields, short/empty essay, template-only, OCR confidence, etc.).

---

## 3. Supabase: what lives where

### 3.1 PostgreSQL (Supabase DB)

| Object | Role |
|--------|------|
| **`submissions`** | Primary business record: names, school, grade, word count, review flags, `artifact_dir`, `filename`, `upload_batch_id`, etc. |
| **`processing_metrics`** | Per-chunk / per-job **telemetry**: timings, `chunk_index`, `parent_submission_id`, `status`, `error_message`, duplicate flag. Best **SQL-accessible** audit for operations. |
| **`jobs`** | **Queue**: `job_data`, `result`, errors, status. Good for “why did this job fail?” |
| **`upload_batches`** | Batch metadata for grouped uploads. |

### 3.2 Supabase Storage (bucket `essay-submissions`)

- **Original uploads** (e.g. `.../original.pdf`).
- **Per-chunk artifacts** (when applicable): `pipeline_log.json`, `traceability.json`, `ocr_summary.json`, `validation.json`, `extracted_fields.json`, etc.
- These support **debugging and contest administration**; they are **not** mirrored in full in Postgres.

### 3.3 How to inspect (operations)

- **Table Editor / SQL** with **service role** or project owner for org-wide visibility (RLS restricts end users to their own rows).
- **Storage** browser: navigate using `submissions.artifact_dir` or parent `run_id` paths.

---

## 4. Data quality & integrity risks (product behavior)

Issues observed in production-style admin views are **consistent with known design**, not necessarily “bugs”:

| Risk | Cause (backend) |
|------|------------------|
| **Duplicate-looking rows** (same filename repeated) | Chunk loop **saves one DB row per chunk**; retries/re-uploads add more rows; multi-student PDFs create many rows. |
| **Empty student/school/grade** | OCR/LLM failed to read fields or wrong region; validation sets **missing** reason codes. |
| **Wrong text in wrong column** (e.g. school in student) | **Field attribution** errors from handwritten or noisy OCR; guardrails reduce but do not eliminate this. |
| **“Template only” / “Empty essay”** | Classifier/extractor determined little or no valid essay body. |
| **Empty “Why in review” with Needs review** | Possible **legacy row** or path where `needs_review` is true without backfilled `review_reason_codes` (app may repair on normal Review screen). |

**Business implication:** Automated rows are **inputs to human workflow**, not a guaranteed-correct contest roster.

---

## 5. Security & access (high level)

- **Authentication:** Supabase magic link; sessions in Flask.
- **Admin dashboard:** Token and/or allowlisted **app admin emails** (`auth/app_admin.py`); uses **service role** for cross-tenant submission listing and downloads.
- **Secrets:** `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, API keys (Groq, Google), `FLASK_SECRET_KEY`, optional `ADMIN_TOKEN` — **must stay out of client code and public repos**.

**Risk:** Service role bypasses RLS; restrict who can deploy env vars and access Supabase project settings.

---

## 6. Cost drivers (where money goes)

Detailed math: **`docs/ops/cost-estimate-1000-essays.md`**.

**Summary:**

- **Google Cloud Vision:** ~**one billable unit per page image** sent to document text detection; multi-page and **chunked** processing increases calls.
- **Groq:** ~**one main LLM request per essay/chunk** through IFI extraction; token usage scales with OCR text length.
- **Infrastructure:** Render, Supabase plan, optional Redis — fixed or usage-based per your contracts.

**Risk:** Spike in uploads or **reprocessing** (e.g. bulk re-run) multiplies API usage. **Monitor** Vision and Groq dashboards and set **billing alerts** in GCP / Groq.

---

## 7. Operational dependencies (availability)

| Dependency | Impact if down |
|------------|----------------|
| **Supabase Postgres** | No saves, no reads, app fails. |
| **Supabase Storage** | Upload/download failures; pipeline cannot persist originals. |
| **Worker + queue (Redis RQ or Postgres `jobs`)** | Backlog or stalled processing; Flask may fall back to **sync** processing (slower, load on web dyno). |
| **Google Vision** | OCR fails or degrades depending on fallback configuration. |
| **Groq** | IFI LLM extraction may fail or fall back (check `pipeline` behavior for fallbacks). |

---

## 8. Recommendations (action checklist)

1. **Define official reporting rules** for contest counts (dedupe key, approved-only, date range).
2. **Reconcile admin UI vs SQL:** Run periodic **SQL reports** from `submissions` (+ optional join logic on `parent_submission_id` if column present in your schema) for finance/contest closes.
3. **Use `processing_metrics`** for SLA and failure analysis; use **Storage JSON** for deep dives on individual rows.
4. **Billing alerts** on GCP and Groq; track **pages processed** and **chunk count** as leading indicators.
5. **Retention policy:** Align Storage artifact retention with **privacy policy** and contest rules (FERPA-style sensitivity).
6. **Backup:** Confirm Supabase **backups** and **PITR** match your risk tolerance.

---

## 9. Document control

| Item | Value |
|------|--------|
| **Generated from** | Codebase path `IFI Essay tool/` |
| **Related docs** | `docs/ops/cost-estimate-1000-essays.md`, `docs/pipeline/architecture.md`, `docs/pipeline/artifact-management-case-study.md` |
| **Update when** | Major pipeline, pricing, or schema changes |

---

*End of report.*
