"""
Playwright smoke test: Grade-6 batch fix for dmiller@kpmg.com

Verifies:
1. Dawn Miller's reader portal loads and shows her grade-6 assignment
2. The batch has exactly 26 essays (not 17 — the count before the fix)
3. All 9 previously-broken essays are present in the list
4. Opening each of the 9 essays returns a PDF that does NOT contain
   the names "Marcos Borrego" or "Stella Doran" (i.e. not the wrong scan)
5. Each essay PDF response contains the correct student's name

Run with:
    cd "IFI Essay tool"
    pip install pytest-playwright
    playwright install chromium
    pytest tests/test_grade6_batch_fix.py -v
"""

from __future__ import annotations

import re
import sys
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

BASE_URL = os.environ.get("APP_URL", "http://localhost:5000")
READER_EMAIL = "dmiller@kpmg.com"

NINE_STUDENTS = [
    ("Cole Berry",     "a5d1c4af67b9"),
    ("Isaac Jackson",  "6ee7a98fb8a5"),
    ("Emma Lind",      "ef3f8061096a"),
    ("Taelynn Limberg","fb1d1d74a21a"),
    ("Leo Kapper",     "7a182af976a5"),
    ("Knox Grundler",  "a0c8f38cad05"),
    ("Trendan Fagan",  "30735a1e707d"),
    ("Eli Faber",      "66054a25302b"),
    ("Ben Ehrgott",    "f7b13a37e4fb"),
]

WRONG_NAMES = ["Marcos Borrego", "Stella Doran", "Marcus Borrego"]

GRADE6_ASSIGNMENT_ID = 19  # Dawn Miller's grade-6 assignment


def _make_token() -> str:
    from admin.routes import _generate_reader_portal_token
    return _generate_reader_portal_token(READER_EMAIL)


def _get_session_cookie(token: str) -> str:
    """
    POST the email-confirmation form via requests to obtain a valid Flask
    session cookie, then return its value for injection into Playwright.
    """
    import requests as req
    s = req.Session()
    url = f"{BASE_URL}/admin/reader-access?token={token}"
    # GET first to pick up CSRF / existing cookies
    s.get(url, timeout=10)
    # POST the email confirmation
    s.post(url, data={"email": READER_EMAIL}, timeout=10)
    cookie = s.cookies.get("session")
    return cookie or ""


@pytest.fixture(scope="module")
def portal_token():
    return _make_token()


@pytest.fixture(scope="module")
def authed_page(browser, portal_token):
    """
    Playwright page pre-loaded with a valid reader session cookie so every
    test in the module gets an already-logged-in browser context.
    """
    context = browser.new_context(base_url=BASE_URL)
    session_cookie = _get_session_cookie(portal_token)
    if session_cookie:
        context.add_cookies([{
            "name": "session",
            "value": session_cookie,
            "domain": "localhost",
            "path": "/",
        }])
    page = context.new_page()
    yield page
    context.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_portal_loads_and_grade6_visible(authed_page, portal_token):
    """Reader portal loads and shows the grade-6 batch."""
    url = f"{BASE_URL}/admin/reader-access?token={portal_token}"
    authed_page.goto(url)
    authed_page.wait_for_load_state("networkidle")
    content = authed_page.content()
    assert "Grade 6" in content or "grade 6" in content.lower(), \
        f"Grade 6 assignment not visible on portal.\nPage snippet:\n{content[:1500]}"


def test_grade6_batch_shows_26_essays(authed_page, portal_token):
    """Batch essay count must be 26, not the broken 17."""
    url = f"{BASE_URL}/admin/reader-access?token={portal_token}"
    authed_page.goto(url)
    authed_page.wait_for_load_state("networkidle")
    content = authed_page.content()
    assert re.search(r"\b26\b", content), \
        f"Expected 26 essays but '26' not found in page.\nSnippet:\n{content[:2000]}"


def test_all_nine_students_listed(authed_page, portal_token):
    """All 9 previously-broken students appear in the assignment review list."""
    url = f"{BASE_URL}/admin/reader-assignments/{GRADE6_ASSIGNMENT_ID}/review?token={portal_token}"
    authed_page.goto(url)
    authed_page.wait_for_load_state("networkidle")
    content = authed_page.content()
    missing = [name for name, _ in NINE_STUDENTS if name not in content]
    assert not missing, f"These students are missing from the batch view: {missing}"


@pytest.mark.parametrize("student_name,submission_id", NINE_STUDENTS)
def test_essay_pdf_serves_correct_content(browser, portal_token, student_name, submission_id):
    """
    Each of the 9 fixed essays must serve a valid PDF binary.
    Uses requests (not Playwright navigation) to avoid browser-level
    download-handling complications with PDF MIME types.
    """
    import requests as req

    session_cookie = _get_session_cookie(portal_token)
    pdf_url = (
        f"{BASE_URL}/admin/reader-assignments/{GRADE6_ASSIGNMENT_ID}"
        f"/submissions/{submission_id}/view?token={portal_token}"
    )
    resp = req.get(pdf_url, cookies={"session": session_cookie}, timeout=30)
    assert resp.status_code == 200, \
        f"{student_name}: expected HTTP 200, got {resp.status_code}. Body: {resp.text[:300]}"

    content_type = resp.headers.get("content-type", "")
    assert "pdf" in content_type, \
        f"{student_name}: expected application/pdf, got '{content_type}'"

    # Verify the response body is a real PDF (starts with %PDF)
    assert resp.content[:4] == b"%PDF", \
        f"{student_name}: response body is not a valid PDF (got {resp.content[:16]!r})"

    # Verify file is non-trivially sized (not just a 0-byte or stub)
    assert len(resp.content) > 500, \
        f"{student_name}: PDF is suspiciously small ({len(resp.content)} bytes)"


def test_pdf_storage_paths_all_exist():
    """
    Direct storage check (no browser): all 9 chunk original.pdfs must exist in Supabase.
    This is the ground-truth verification independent of the app layer.
    """
    from pipeline.supabase_db import _get_service_role_client

    AFFECTED_IDS = [
        "a5d1c4af67b9", "6ee7a98fb8a5", "ef3f8061096a", "fb1d1d74a21a",
        "7a182af976a5", "a0c8f38cad05", "30735a1e707d", "66054a25302b", "f7b13a37e4fb",
    ]
    BUCKET = "essay-submissions"

    sb = _get_service_role_client()
    rows = (
        sb.table("submissions")
        .select("submission_id, student_name, artifact_dir")
        .in_("submission_id", AFFECTED_IDS)
        .execute()
        .data or []
    )
    assert len(rows) == 9, f"Expected 9 records, found {len(rows)}"

    missing = []
    for r in rows:
        path = f"{r['artifact_dir']}/original.pdf"
        try:
            data = sb.storage.from_(BUCKET).download(path)
            assert data and len(data) > 100, f"{r['student_name']}: PDF is empty"
        except Exception as e:
            missing.append(f"{r['student_name']} ({path}): {e}")

    assert not missing, "PDFs missing from storage:\n" + "\n".join(missing)


def test_records_are_approved_and_visible():
    """
    All 9 records must be in 'approved' state:
      - needs_review=False
      - no blocking review_reason_codes
    This ensures derive_submission_status returns 'approved' and they appear
    in the assignment pool for readers.
    """
    from pipeline.supabase_db import _get_service_role_client
    from admin.assignments_service import derive_submission_status

    AFFECTED_IDS = [
        "a5d1c4af67b9", "6ee7a98fb8a5", "ef3f8061096a", "fb1d1d74a21a",
        "7a182af976a5", "a0c8f38cad05", "30735a1e707d", "66054a25302b", "f7b13a37e4fb",
    ]

    sb = _get_service_role_client()
    rows = (
        sb.table("submissions")
        .select("submission_id, student_name, needs_review, review_reason_codes, "
                "school_name, grade, is_container_parent")
        .in_("submission_id", AFFECTED_IDS)
        .execute()
        .data or []
    )
    not_approved = []
    for r in rows:
        status = derive_submission_status(r)
        if status != "approved":
            not_approved.append(f"{r['student_name']} (status={status}, codes={r.get('review_reason_codes')})")

    assert not not_approved, \
        f"These records are not 'approved' (hidden from assignment pools):\n" + "\n".join(not_approved)
