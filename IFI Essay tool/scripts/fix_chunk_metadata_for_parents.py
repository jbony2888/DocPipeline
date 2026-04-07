#!/usr/bin/env python3
"""
Fix over-split chunk submissions by propagating canonical metadata across sibling chunks.

Use when a single multi-page PDF was incorrectly split into per-page chunk rows, leaving
many children with missing school/grade even though another sibling chunk has them.

For each parent_submission_id, this script:
- loads all child rows (is_container_parent=false) for that parent
- derives canonical student_name / school_name / grade from the best-available sibling(s)
- updates only the missing fields on each child
- recomputes needs_review + review_reason_codes using pipeline.metadata_essay_link.recompute_review_after_link

Dry run by default; pass --execute to apply updates.

Usage:
  python scripts/fix_chunk_metadata_for_parents.py --parent-ids 84b491ae026c 2979ad1a92a3 c2d59bb23c71
  python scripts/fix_chunk_metadata_for_parents.py --parent-ids ... --execute
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from pipeline.metadata_essay_link import recompute_review_after_link  # noqa: E402
from pipeline.supabase_db import _get_service_role_client  # noqa: E402


def _clean_str(v: Any) -> str | None:
    s = str(v or "").strip()
    return s or None


def _clean_grade(v: Any) -> Any:
    if v is None:
        return None
    # Preserve "K" and other text grades; coerce digit strings to int.
    s = str(v).strip()
    if not s:
        return None
    if s.isdigit():
        try:
            return int(s)
        except Exception:
            return s
    return s


def _wc_int(v: Any) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def _pick_canonical(children: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Pick canonical metadata from siblings.
    Strategy:
    - prefer the most common non-empty values across chunks
    - break ties by choosing from the chunk with highest word_count (often the essay chunk)
    """
    name_counts = Counter([_clean_str(c.get("student_name")) for c in children if _clean_str(c.get("student_name"))])
    school_counts = Counter([_clean_str(c.get("school_name")) for c in children if _clean_str(c.get("school_name"))])
    grade_counts = Counter([_clean_grade(c.get("grade")) for c in children if _clean_grade(c.get("grade")) is not None])

    # Fallback row order for tie-breaking
    best_by_wc = sorted(children, key=lambda c: (-_wc_int(c.get("word_count")), str(c.get("submission_id") or "")))

    def pick(counter: Counter, getter):
        if counter:
            top, top_n = counter.most_common(1)[0]
            return top
        for c in best_by_wc:
            v = getter(c)
            if v is not None and (not isinstance(v, str) or v.strip()):
                return v
        return None

    canonical = {
        "student_name": pick(name_counts, lambda c: _clean_str(c.get("student_name"))),
        "school_name": pick(school_counts, lambda c: _clean_str(c.get("school_name"))),
        "grade": pick(grade_counts, lambda c: _clean_grade(c.get("grade"))),
    }
    return canonical


def _fetch_children(sb, parent_id: str) -> list[dict[str, Any]]:
    fields = (
        "submission_id, parent_submission_id, filename, student_name, school_name, grade, "
        "word_count, ocr_confidence_avg, doc_class, needs_review, review_reason_codes, "
        "chunk_index, chunk_page_start, chunk_page_end, is_chunk, is_container_parent"
    )
    res = (
        sb.table("submissions")
        .select(fields)
        .eq("parent_submission_id", parent_id)
        .eq("is_container_parent", False)
        .order("chunk_index", desc=False)
        .limit(200)
        .execute()
    )
    return list(res.data or [])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent-ids", nargs="+", required=True, help="Parent submission_id(s)")
    p.add_argument("--execute", action="store_true", help="Apply updates (default is dry run)")
    args = p.parse_args()

    sb = _get_service_role_client()
    if not sb:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 2

    any_changes = False
    for pid_raw in args.parent_ids:
        pid = str(pid_raw or "").strip()
        if not pid:
            continue
        children = _fetch_children(sb, pid)
        if not children:
            print(f"\nparent={pid}: no children found")
            continue

        canonical = _pick_canonical(children)
        print(
            f"\nparent={pid} children={len(children)} canonical="
            f"{{name={canonical.get('student_name')!r}, school={canonical.get('school_name')!r}, grade={canonical.get('grade')!r}}}"
        )

        for ch in children:
            sid = str(ch.get("submission_id") or "").strip()
            if not sid:
                continue

            updates: dict[str, Any] = {}
            if not _clean_str(ch.get("student_name")) and canonical.get("student_name"):
                updates["student_name"] = canonical["student_name"]
            if not _clean_str(ch.get("school_name")) and canonical.get("school_name"):
                updates["school_name"] = canonical["school_name"]
            if _clean_grade(ch.get("grade")) is None and canonical.get("grade") is not None:
                updates["grade"] = canonical["grade"]

            if not updates:
                continue

            merged = {**ch, **updates}
            wc = _wc_int(merged.get("word_count"))
            needs_review, codes = recompute_review_after_link(merged, wc)
            updates["needs_review"] = needs_review
            updates["review_reason_codes"] = codes
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()

            any_changes = True
            pages = f"{ch.get('chunk_page_start')}-{ch.get('chunk_page_end')}".strip("-")
            print(
                f"  child={sid} pages={pages or '?'} apply={updates} "
                f"(was school={ch.get('school_name')!r} grade={ch.get('grade')!r})"
            )

            if args.execute:
                sb.table("submissions").update(updates).eq("submission_id", sid).execute()

    if not any_changes:
        print("\nNo changes needed.")
        return 0

    if not args.execute:
        print("\nDry run only. Re-run with --execute to apply.")
    else:
        print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

