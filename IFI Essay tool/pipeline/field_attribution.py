"""
Backward-compatible wrapper around guardrails attribution core.
"""

from pipeline.guardrails.attribution import (
    assert_expected_attribution,
    build_field_attribution_debug_payload,
    compute_field_attribution_confidence,
    compute_field_source_pages,
    load_per_page_text,
    normalize_text,
)

