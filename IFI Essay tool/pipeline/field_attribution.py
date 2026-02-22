"""
Backward-compatible wrapper around guardrails attribution core.
"""

from idp_guardrails_core.core import (
    assert_expected_attribution,
    build_field_attribution_debug_payload,
    compute_field_attribution_confidence,
    compute_field_source_pages,
    find_grade_page,
    find_value_page,
    write_field_attribution_debug_artifact,
    load_per_page_text,
    normalize_text,
)

