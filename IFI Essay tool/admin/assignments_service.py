"""
Assignment service layer for admin grade-level reader assignments.

Scope is intentionally narrow for v1:
- grade-level assignment only (reader gets all approved essays for grade)
- no per-essay assignment tables
- email delivery is a post-assignment hook only
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from collections import defaultdict
from typing import Any


EMAIL_REGEX = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)
ESSAYS_PER_ASSIGNMENT_BATCH = 30


def parse_and_validate_reader_emails(raw_value: Any) -> tuple[list[str], list[str]]:
    """
    Parse and validate reader emails.

    Supports:
    - list input from API
    - string input with commas/newlines
    - mixed whitespace
    Returns (valid_unique_emails, invalid_tokens)
    """
    if isinstance(raw_value, list):
        tokens = [str(v or "").strip() for v in raw_value]
    else:
        text = str(raw_value or "")
        tokens = re.split(r"[\n,]+", text)

    valid: list[str] = []
    invalid: list[str] = []
    seen = set()

    for token in tokens:
        email = (token or "").strip().lower()
        if not email:
            continue
        if not EMAIL_REGEX.match(email):
            invalid.append(email)
            continue
        if email in seen:
            continue
        seen.add(email)
        valid.append(email)

    return valid, invalid


def _is_approved_submission_row(row: dict[str, Any]) -> bool:
    """Mirror admin dashboard approval logic for consistency."""
    has_all_data = bool(row.get("student_name") and row.get("school_name") and row.get("grade") is not None)
    has_reason = bool((row.get("review_reason_codes") or "").strip())
    if has_all_data and not has_reason:
        return True
    if row.get("needs_review"):
        return False
    return True


def _grade_query_value(grade: str) -> Any:
    value = str(grade or "").strip()
    if value.isdigit():
        return int(value)
    return value


def _normalize_school_text(value: str) -> str:
    text = (value or "").casefold()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _resolve_canonical_school_name(school: str, validator: Any) -> str | None:
    """
    Resolve raw school text to a canonical reference-school name.
    Returns None for unmatched values.
    """
    value = str(school or "").strip()
    if not value or not validator:
        return None

    normalized = _normalize_school_text(value)
    rows = list(getattr(validator, "_rows", []) or [])
    normalized_rows = list(getattr(validator, "_normalized_rows", []) or [])
    if not rows or not normalized_rows or len(rows) != len(normalized_rows):
        return None

    # Exact normalized match to reference.
    for idx, ref_norm in enumerate(normalized_rows):
        if normalized == ref_norm:
            return rows[idx]

    # Partial containment match.
    for idx, ref_norm in enumerate(normalized_rows):
        if ref_norm in normalized or normalized in ref_norm:
            return rows[idx]

    # Best fuzzy match.
    best_idx = -1
    best_ratio = 0.0
    in_words = {w for w in normalized.split() if len(w) >= 2}
    for idx, ref_norm in enumerate(normalized_rows):
        ratio = SequenceMatcher(None, normalized, ref_norm).ratio()
        ref_words = {w for w in ref_norm.split() if len(w) >= 2}
        overlap = len(in_words & ref_words)
        # Require at least one meaningful token overlap to avoid person-name drift.
        if overlap < 1:
            continue
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = idx
    if best_idx >= 0 and best_ratio >= 0.78:
        return rows[best_idx]
    return None


def _standardized_school_label(canonical_school: str) -> str | None:
    """
    Restrict assignment dropdown to standardized school buckets.
    """
    value = str(canonical_school or "").strip().casefold()
    if not value:
        return None
    if "carson" in value:
        return "Rachel Carson Elementary School"
    if "la salle" in value or "lasalle" in value:
        return "De La Salle Institute"
    if "mundelein" in value or "munderein" in value:
        return "Munderein HS"
    return None


STANDARD_SCHOOL_OPTIONS = (
    "De La Salle Institute",
    "Rachel Carson Elementary School",
    "Munderein HS",
)


def _resolve_standard_school_label(raw_school: str, validator: Any) -> str | None:
    direct_match = _standardized_school_label(raw_school)
    if direct_match:
        return direct_match
    canonical = _resolve_canonical_school_name(raw_school, validator)
    if not canonical:
        return None
    return _standardized_school_label(canonical)


def normalize_school_to_standard(raw_school: str | None) -> str | None:
    """
    Normalize raw school text into one of the standard school labels.
    Returns None when no standard mapping is found.
    """
    try:
        from idp_guardrails_core.core import SchoolReferenceValidator

        validator = SchoolReferenceValidator()
    except Exception:
        validator = None
    return _resolve_standard_school_label(str(raw_school or ""), validator)


def calculate_assignment_batch_count(essay_count: int) -> int:
    """
    Split assignments into batches of up to 30 approved essays.
    """
    count = max(0, int(essay_count or 0))
    if count <= 0:
        return 0
    return ((count - 1) // ESSAYS_PER_ASSIGNMENT_BATCH) + 1


def get_batch_bounds(batch_number: int, total_items: int) -> tuple[int, int]:
    """
    Return zero-based [start, end) indexes for a 1-based batch number.
    """
    total = max(0, int(total_items or 0))
    batch = max(1, int(batch_number or 1))
    start = (batch - 1) * ESSAYS_PER_ASSIGNMENT_BATCH
    end = min(start + ESSAYS_PER_ASSIGNMENT_BATCH, total)
    return start, end


def count_approved_essays_for_batch(sb: Any, school: str, grade: str) -> int:
    """
    Count approved submissions for a selected grade.
    """
    query_value = _grade_query_value(grade)
    selected_school = str(school or "").strip()
    try:
        from idp_guardrails_core.core import SchoolReferenceValidator
        validator = SchoolReferenceValidator()
    except Exception:
        validator = None

    result = (
        sb.table("submissions")
        .select("grade, school_name, student_name, needs_review, review_reason_codes")
        .eq("grade", query_value)
        .limit(10000)
        .execute()
    )
    rows = result.data or []
    count = 0
    for row in rows:
        standardized = _resolve_standard_school_label(str(row.get("school_name") or ""), validator)
        if not standardized:
            continue
        if standardized != selected_school:
            continue
        if _is_approved_submission_row(row):
            count += 1
    return count


def list_approved_submissions_for_batch(sb: Any, school: str, grade: str) -> list[dict[str, Any]]:
    """
    Return approved submissions for one standardized school+grade bucket.
    """
    query_value = _grade_query_value(grade)
    selected_school = str(school or "").strip()
    try:
        from idp_guardrails_core.core import SchoolReferenceValidator

        validator = SchoolReferenceValidator()
    except Exception:
        validator = None

    result = (
        sb.table("submissions")
        .select("submission_id, filename, artifact_dir, created_at, grade, school_name, student_name, needs_review, review_reason_codes")
        .eq("grade", query_value)
        .limit(10000)
        .execute()
    )
    rows = result.data or []
    filtered: list[dict[str, Any]] = []
    for row in rows:
        standardized = _resolve_standard_school_label(str(row.get("school_name") or ""), validator)
        if standardized != selected_school:
            continue
        if not _is_approved_submission_row(row):
            continue
        filtered.append(dict(row))
    filtered.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("submission_id") or "")))
    return filtered


def list_assignment_submission_rows(
    sb: Any,
    *,
    school: str,
    grade: str,
    batch_number: int,
) -> list[dict[str, Any]]:
    """
    Resolve the submission rows belonging to one assignment batch.
    """
    submissions = list_approved_submissions_for_batch(sb, school=school, grade=grade)
    if not submissions:
        return []
    start, end = get_batch_bounds(int(batch_number or 1), len(submissions))
    return submissions[start:end]


def list_approved_batches_by_school(sb: Any) -> list[dict[str, Any]]:
    """
    Return approved essay batches grouped by school, then grade.
    """
    try:
        from idp_guardrails_core.core import SchoolReferenceValidator
        validator = SchoolReferenceValidator()
    except Exception:
        validator = None

    result = (
        sb.table("submissions")
        .select("grade, school_name, student_name, needs_review, review_reason_codes, owner_user_id")
        .limit(10000)
        .execute()
    )
    rows = result.data or []

    grouped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    owner_ids_by_bucket: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in rows:
        raw_school = str(row.get("school_name") or "").strip()
        school = _resolve_standard_school_label(raw_school, validator)
        grade = str(row.get("grade") or "").strip()
        if not school or not grade:
            continue
        if not _is_approved_submission_row(row):
            continue
        grouped[school][grade] += 1
        owner_user_id = str(row.get("owner_user_id") or "").strip()
        if owner_user_id:
            owner_ids_by_bucket[school][grade].add(owner_user_id)

    teacher_email_by_owner_id = _load_teacher_emails_by_owner_id(sb, owner_ids_by_bucket)

    out: list[dict[str, Any]] = []
    for school in STANDARD_SCHOOL_OPTIONS:
        grade_items = []
        for grade, count in sorted(
            grouped.get(school, {}).items(),
            key=lambda item: (not str(item[0]).isdigit(), str(item[0]).casefold()),
        ):
            owner_ids = sorted(owner_ids_by_bucket.get(school, {}).get(grade, set()))
            teacher_emails = [
                teacher_email_by_owner_id[owner_id]
                for owner_id in owner_ids
                if teacher_email_by_owner_id.get(owner_id)
            ]
            grade_items.append(
                {
                    "grade": grade,
                    "approvedCount": count,
                    "teacherEmails": teacher_emails,
                    "teacherEmailCount": len(teacher_emails),
                }
            )
        out.append({"school": school, "grades": grade_items})
    return out


def _load_teacher_emails_by_owner_id(
    sb: Any,
    owner_ids_by_bucket: dict[str, dict[str, set[str]]],
) -> dict[str, str]:
    """
    Resolve submission owner_user_id values to teacher emails via Supabase Auth admin.
    """
    owner_ids = {
        owner_id
        for grade_map in owner_ids_by_bucket.values()
        for ids in grade_map.values()
        for owner_id in ids
        if owner_id
    }
    if not owner_ids:
        return {}

    resolved: dict[str, str] = {}
    page = 1
    per_page = 1000
    while True:
        batch = sb.auth.admin.list_users(page=page, per_page=per_page)
        users = list(batch or [])
        if not users:
            break
        for user in users:
            user_id = str(getattr(user, "id", "") or "").strip()
            email = str(getattr(user, "email", "") or "").strip().lower()
            if user_id in owner_ids and email:
                resolved[user_id] = email
        if len(users) < per_page or len(resolved) == len(owner_ids):
            break
        page += 1

    return resolved


def resolve_or_create_readers(sb: Any, emails: list[str]) -> list[dict[str, Any]]:
    """
    Resolve readers by email and create missing reader records.
    """
    if not emails:
        return []

    existing_result = sb.table("readers").select("id, email").in_("email", emails).execute()
    existing_rows = existing_result.data or []
    existing_by_email = {str(r.get("email") or "").lower(): r for r in existing_rows}

    missing = [email for email in emails if email not in existing_by_email]
    if missing:
        insert_rows = [{"email": email, "name": None} for email in missing]
        # Upsert keeps this idempotent/race-safe if another request inserts first.
        sb.table("readers").upsert(
            insert_rows,
            on_conflict="email",
            ignore_duplicates=True,
        ).execute()

    final_result = sb.table("readers").select("id, email").in_("email", emails).execute()
    return final_result.data or []


def create_batch_assignments(
    sb: Any,
    reader_ids: list[Any],
    school: str,
    grade: str,
    total_batches: int,
) -> None:
    """
    Create school+grade batch assignments with one reader per batch.
    """
    if not reader_ids:
        return
    if total_batches <= 0:
        return
    payload = [
        {
            "reader_id": reader_id,
            "school_name": str(school).strip(),
            "grade": str(grade).strip(),
            "batch_number": batch_number,
            "total_batches": total_batches,
        }
        for batch_number, reader_id in enumerate(reader_ids[:total_batches], start=1)
    ]
    sb.table("assignments").upsert(
        payload,
        on_conflict="reader_id,school_name,grade,batch_number",
        ignore_duplicates=True,
    ).execute()


def add_batch_assignment(
    sb: Any,
    *,
    reader_id: Any,
    school: str,
    grade: str,
    batch_number: int,
    total_batches: int,
) -> None:
    """
    Add one reader assignment for a specific school+grade batch.
    """
    school_name = str(school).strip()
    grade_value = str(grade).strip()
    batch_value = int(batch_number)
    sb.table("assignments").upsert(
        [
            {
                "reader_id": reader_id,
                "school_name": school_name,
                "grade": grade_value,
                "batch_number": batch_value,
                "total_batches": int(total_batches),
            }
        ],
        on_conflict="reader_id,school_name,grade,batch_number",
        ignore_duplicates=True,
    ).execute()


def list_batch_assignments_for_school_grade(sb: Any, school: str, grade: str) -> list[dict[str, Any]]:
    """
    Return assignment rows for one school+grade keyed by batch.
    """
    result = (
        sb.table("assignments")
        .select("id, school_name, grade, batch_number, total_batches, created_at, readers(id, email, name)")
        .eq("school_name", str(school).strip())
        .eq("grade", str(grade).strip())
        .order("batch_number")
        .limit(100)
        .execute()
    )
    rows = result.data or []
    out: list[dict[str, Any]] = []
    for row in rows:
        reader = row.get("readers") or {}
        out.append(
            {
                "id": row.get("id"),
                "batchNumber": row.get("batch_number"),
                "totalBatches": row.get("total_batches"),
                "readerId": reader.get("id"),
                "readerEmail": reader.get("email"),
                "readerName": reader.get("name"),
                "createdAt": row.get("created_at"),
            }
        )
    return out


def get_reader_by_email(sb: Any, email: str) -> dict[str, Any] | None:
    """
    Look up one reader record by email.
    """
    normalized = str(email or "").strip().lower()
    if not normalized:
        return None
    result = sb.table("readers").select("id, email, name").eq("email", normalized).limit(1).execute()
    rows = result.data or []
    return rows[0] if rows else None


def upsert_reader_name(sb: Any, *, email: str, name: str) -> dict[str, Any] | None:
    """
    Ensure a reader exists and persist the latest submitted display name.
    """
    normalized_email = str(email or "").strip().lower()
    cleaned_name = str(name or "").strip()
    if not normalized_email:
        return None

    reader = get_reader_by_email(sb, normalized_email)
    if reader:
        if cleaned_name and cleaned_name != str(reader.get("name") or "").strip():
            sb.table("readers").update({"name": cleaned_name}).eq("id", reader.get("id")).execute()
            reader["name"] = cleaned_name
        return reader

    inserted = (
        sb.table("readers")
        .upsert(
            [{"email": normalized_email, "name": cleaned_name or None}],
            on_conflict="email",
            ignore_duplicates=False,
        )
        .execute()
    )
    rows = inserted.data or []
    if rows:
        return rows[0]
    return get_reader_by_email(sb, normalized_email)


def list_assignments_for_reader(sb: Any, reader_id: Any) -> list[dict[str, Any]]:
    """
    Return assignment rows for one reader id.
    """
    result = (
        sb.table("assignments")
        .select("id, school_name, grade, batch_number, total_batches, created_at")
        .eq("reader_id", reader_id)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    return result.data or []


def get_assignment_with_reader(sb: Any, assignment_id: int) -> dict[str, Any] | None:
    """
    Return one assignment row joined with its reader.
    """
    result = (
        sb.table("assignments")
        .select("id, reader_id, school_name, grade, batch_number, total_batches, created_at, readers(id, email, name)")
        .eq("id", int(assignment_id))
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def list_rankings_for_assignment(sb: Any, *, assignment_id: int, reader_id: Any) -> list[dict[str, Any]]:
    """
    Return saved rankings for one reader assignment.
    """
    result = (
        sb.table("essay_rankings")
        .select(
            "id, assignment_id, reader_id, submission_id, school_name, grade, batch_number, "
            "rank_position, reader_name, reader_email, created_at, updated_at"
        )
        .eq("assignment_id", int(assignment_id))
        .eq("reader_id", reader_id)
        .order("rank_position")
        .limit(500)
        .execute()
    )
    return result.data or []


def replace_assignment_rankings(
    sb: Any,
    *,
    assignment_id: int,
    reader_id: Any,
    school: str,
    grade: str,
    batch_number: int,
    reader_name: str,
    reader_email: str,
    rankings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Replace the saved ranking set for one assignment.
    """
    sb.table("essay_rankings").delete().eq("assignment_id", int(assignment_id)).eq("reader_id", reader_id).execute()
    payload = [
        {
            "assignment_id": int(assignment_id),
            "reader_id": reader_id,
            "submission_id": str(item.get("submission_id") or "").strip(),
            "school_name": str(school or "").strip(),
            "grade": str(grade or "").strip(),
            "batch_number": int(batch_number),
            "rank_position": int(item.get("rank_position")),
            "reader_name": str(reader_name or "").strip(),
            "reader_email": str(reader_email or "").strip().lower(),
        }
        for item in rankings
    ]
    result = sb.table("essay_rankings").upsert(
        payload,
        on_conflict="assignment_id,reader_id,submission_id",
        ignore_duplicates=False,
    ).execute()
    return result.data or []


def compute_ranking_results(sb: Any, *, grade: str, school: str | None = None) -> list[dict[str, Any]]:
    """
    Compute final ranking results for a grade, optionally filtered to one school.
    """
    query = (
        sb.table("essay_rankings")
        .select(
            "submission_id, school_name, grade, rank_position, reader_id, reader_name, reader_email"
        )
        .eq("grade", str(grade).strip())
        .limit(10000)
    )
    if school:
        query = query.eq("school_name", str(school).strip())
    rankings = query.execute().data or []
    if not rankings:
        return []

    submission_ids = sorted({str(row.get("submission_id") or "").strip() for row in rankings if str(row.get("submission_id") or "").strip()})
    submissions_result = (
        sb.table("submissions")
        .select("submission_id, student_name, school_name, grade")
        .in_("submission_id", submission_ids)
        .limit(max(1, len(submission_ids)))
        .execute()
    )
    submissions = {str(row.get("submission_id") or ""): row for row in (submissions_result.data or [])}

    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"total_rank": 0, "num_ranks": 0, "breakdown": []})
    for row in rankings:
        submission_id = str(row.get("submission_id") or "").strip()
        if not submission_id:
            continue
        rank_value = int(row.get("rank_position") or 0)
        grouped[submission_id]["total_rank"] += rank_value
        grouped[submission_id]["num_ranks"] += 1
        grouped[submission_id]["breakdown"].append(
            {
                "readerId": row.get("reader_id"),
                "readerName": row.get("reader_name"),
                "readerEmail": row.get("reader_email"),
                "rankPosition": rank_value,
            }
        )

    results: list[dict[str, Any]] = []
    for submission_id, aggregate in grouped.items():
        submission = submissions.get(submission_id) or {}
        num_ranks = int(aggregate["num_ranks"])
        average_rank = float(aggregate["total_rank"]) / num_ranks if num_ranks else 0.0
        results.append(
            {
                "submissionId": submission_id,
                "studentName": submission.get("student_name"),
                "schoolName": submission.get("school_name"),
                "grade": submission.get("grade"),
                "numRanks": num_ranks,
                "averageRank": average_rank,
                "readerBreakdown": sorted(aggregate["breakdown"], key=lambda item: (item["rankPosition"], str(item["readerEmail"] or ""))),
            }
        )

    results.sort(key=lambda item: (item["averageRank"], -item["numRanks"], str(item["submissionId"])))
    for index, item in enumerate(results, start=1):
        item["finalPosition"] = index
    return results


def trigger_assignment_send_hook(school: str, grade: str, essay_count: int, reader_emails: list[str]) -> None:
    """
    Email/job hook stub for assignment sends.
    Replace with queue/mailer integration when delivery is enabled.
    """
    print(
        "[assignment-send-hook] "
        f"school={school} grade={grade} essay_count={essay_count} readers={','.join(reader_emails)}",
        flush=True,
    )


def list_assignment_records(sb: Any) -> list[dict[str, Any]]:
    """
    Return assignment records joined with reader email/name for admin display.
    """
    result = (
        sb.table("assignments")
        .select("id, school_name, grade, batch_number, total_batches, created_at, readers(id, email, name)")
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )
    rows = result.data or []
    out: list[dict[str, Any]] = []
    for row in rows:
        reader = row.get("readers") or {}
        out.append(
            {
                "id": row.get("id"),
                "school": row.get("school_name"),
                "grade": row.get("grade"),
                "batchNumber": row.get("batch_number"),
                "totalBatches": row.get("total_batches"),
                "createdAt": row.get("created_at"),
                "readerId": reader.get("id"),
                "readerEmail": reader.get("email"),
                "readerName": reader.get("name"),
            }
        )
    return out


def remove_assignment(sb: Any, assignment_id: int) -> bool:
    """
    Delete one assignment row by id.
    """
    result = sb.table("assignments").delete().eq("id", assignment_id).execute()
    return bool(result.data)
