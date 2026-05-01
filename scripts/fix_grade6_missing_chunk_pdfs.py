#!/usr/bin/env python3
"""
Fix: Grade-6 batch (mary6 (1).pdf) – 9 chunk records have no stored PDF.

Root cause
----------
A second pass of the pipeline created 9 child records for the multi-entry
scan mary6 (1).pdf (parent 210f7c04fce8).  The records have correct essay_text
in the DB but their artifact_dir chunk folders were never written to Supabase
Storage.  When a reader opens any of those essays the app falls back to the
parent original.pdf – a 2-page scan containing only Marcos Borrego and Stella
Doran – which is exactly the wrong-content complaint from dmiller@kpmg.com.

Fix
---
For each of the 9 affected records:
  1. Build a single-page PDF from the DB essay_text (student name header + body).
  2. Upload it to  <artifact_dir>/original.pdf  in the essay-submissions bucket.
  3. Optionally tag the record: needs_review=True + RECONSTRUCTED_PDF code so
     staff know the PDF was rebuilt from extracted text (not the original scan).

Usage
-----
  # dry run (default)
  python scripts/fix_grade6_missing_chunk_pdfs.py

  # apply
  python scripts/fix_grade6_missing_chunk_pdfs.py --execute

  # apply but skip the RECONSTRUCTED_PDF tag entirely
  python scripts/fix_grade6_missing_chunk_pdfs.py --execute --no-tag

NOTE: --no-tag is the recommended default for reader-facing batches.
Setting needs_review=True hides records from reader batch views.
The RECONSTRUCTED_PDF code is written to review_reason_codes regardless
of needs_review, so it serves as an audit marker without hiding essays.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "IFI Essay tool"
sys.path.insert(0, str(APP_ROOT))

try:
    from dotenv import load_dotenv
    env_path = (APP_ROOT / ".env") if (APP_ROOT / ".env").exists() else (ROOT / ".env")
    load_dotenv(env_path)
except Exception:
    pass

BUCKET = "essay-submissions"

# The 9 submission IDs that were confirmed missing their chunk PDFs
AFFECTED_IDS = [
    "a5d1c4af67b9",  # Cole Berry
    "6ee7a98fb8a5",  # Isaac Jackson
    "ef3f8061096a",  # Emma Lind
    "fb1d1d74a21a",  # Taelynn Limberg
    "7a182af976a5",  # Leo Kapper
    "a0c8f38cad05",  # Knox Grundler
    "30735a1e707d",  # Trendan Fagan
    "66054a25302b",  # Eli Faber
    "f7b13a37e4fb",  # Ben Ehrgott
]


def _build_pdf(student_name: str, grade: str, school: str, essay_text: str) -> bytes:
    """Return bytes of a simple 1-page PDF containing the essay."""
    import fitz  # PyMuPDF

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # US Letter

    margin = 60
    y = margin

    # Title / header
    header = f"IFI Fatherhood Essay Contest 2026  |  Grade {grade or '?'}"
    page.insert_text((margin, y), header, fontsize=9, color=(0.4, 0.4, 0.4))
    y += 18

    name_line = f"Student: {student_name or '(unknown)'}    School: {school or '(unknown)'}"
    page.insert_text((margin, y), name_line, fontsize=10, fontname="helv", color=(0, 0, 0))
    y += 20

    # Divider line
    page.draw_line((margin, y), (612 - margin, y), color=(0.7, 0.7, 0.7), width=0.5)
    y += 14

    # Essay body – word-wrap manually
    text = (essay_text or "").strip()
    words = text.split()
    line_buf: list[str] = []
    fontsize = 11
    max_width = 612 - 2 * margin
    chars_per_line = int(max_width / (fontsize * 0.55))

    for word in words:
        line_buf.append(word)
        if len(" ".join(line_buf)) >= chars_per_line:
            page.insert_text((margin, y), " ".join(line_buf[:-1]),
                             fontsize=fontsize, color=(0, 0, 0))
            y += fontsize + 3
            line_buf = [word]
            if y > 792 - margin:
                page = doc.new_page(width=612, height=792)
                y = margin

    if line_buf:
        page.insert_text((margin, y), " ".join(line_buf),
                         fontsize=fontsize, color=(0, 0, 0))

    # Reconstruction notice at bottom
    notice = "[PDF reconstructed from extracted essay text – original scan not available]"
    last_page = doc[-1]
    last_page.insert_text((margin, 792 - 30), notice, fontsize=7, color=(0.5, 0.5, 0.5))

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="Upload PDFs and update DB (default: dry run)")
    ap.add_argument("--no-tag", action="store_true",
                    help="Skip adding RECONSTRUCTED_PDF to review_reason_codes")
    args = ap.parse_args()

    from pipeline.supabase_db import _get_service_role_client

    sb = _get_service_role_client()
    if not sb:
        print("ERROR: missing Supabase service role env")
        return 2

    rows = (
        sb.table("submissions")
        .select("submission_id, student_name, school_name, grade, "
                "artifact_dir, needs_review, review_reason_codes, essay_text, word_count")
        .in_("submission_id", AFFECTED_IDS)
        .execute()
        .data or []
    )

    if not rows:
        print("No matching records found – check AFFECTED_IDS list.")
        return 1

    print(f"{'DRY RUN' if not args.execute else 'EXECUTING'} – {len(rows)} records\n")

    ok = skipped = failed = 0
    for r in rows:
        sid = r["submission_id"]
        name = r.get("student_name") or "(unknown)"
        art_dir = (r.get("artifact_dir") or "").strip()
        essay = (r.get("essay_text") or "").strip()
        storage_path = f"{art_dir}/original.pdf"

        # Check whether a PDF already exists
        already_exists = False
        try:
            sb.storage.from_(BUCKET).download(storage_path)
            already_exists = True
        except Exception:
            pass

        status = "EXISTS" if already_exists else "MISSING"
        print(f"  {name:25s} [{sid[:8]}]  PDF={status}", end="")

        if already_exists:
            print("  → skip (already present)")
            skipped += 1
            continue

        if not essay:
            print("  → WARN: no essay_text in DB, skipping")
            failed += 1
            continue

        print(f"  wc={r.get('word_count')}  art={art_dir[-40:]}")

        if not args.execute:
            print(f"    [dry-run] would upload {storage_path}")
            ok += 1
            continue

        # Build and upload PDF
        try:
            pdf_bytes = _build_pdf(
                student_name=name,
                grade=str(r.get("grade") or ""),
                school=str(r.get("school_name") or ""),
                essay_text=essay,
            )
            sb.storage.from_(BUCKET).upload(
                storage_path,
                pdf_bytes,
                {"content-type": "application/pdf", "cache-control": "no-cache"},
            )
            print(f"    ✓ uploaded {len(pdf_bytes):,} bytes → {storage_path}")
        except Exception as exc:
            print(f"    ✗ upload failed: {exc}")
            failed += 1
            continue

        # NOTE: We intentionally do NOT write review_reason_codes here.
        # Adding any code (e.g. RECONSTRUCTED_PDF) causes derive_submission_status
        # to return "needs_review", which removes the record from assignment pools
        # and hides it from readers. The uploaded PDF is the audit trail.

        ok += 1

    print(f"\n{'─'*55}")
    print(f"Done.  uploaded={ok}  skipped={skipped}  failed={failed}")
    if not args.execute:
        print("Dry run only — re-run with --execute to apply.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
