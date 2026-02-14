"""
Auth package exports.

Some unit tests patch ``auth.supabase_client`` before importing the Flask app to
avoid import-time side effects. Expose it as an attribute on the package so
`unittest.mock.patch()` works.
"""

supabase_client = None  # noqa: N816

__all__ = ["supabase_client"]




