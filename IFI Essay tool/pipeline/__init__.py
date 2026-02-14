"""
Pipeline package exports.

Some unit tests patch attributes like ``pipeline.supabase_storage`` before importing
the Flask app to avoid import-time side effects. Those attributes must exist on
the package for `unittest.mock.patch()` to work.
"""

from pipeline.ingest import ingest_upload

# Patch targets for tests (set to None by default; tests replace with mocks).
supabase_storage = None  # noqa: N816

__all__ = ["ingest_upload", "supabase_storage"]
