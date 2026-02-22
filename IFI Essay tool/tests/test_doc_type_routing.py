from pathlib import Path

from pipeline.doc_type_routing import detect_pdf_has_acroform_fields, route_doc_type


def test_doc_type_routing_detects_acroform_typed_form():
    repo_root = Path(__file__).resolve().parent.parent
    fixture = repo_root / "docs" / "typed-form-submission" / "tc01_standard_form_26-IFI-filled.pdf"
    assert fixture.exists(), f"Missing fixture: {fixture}"

    has_acroform = detect_pdf_has_acroform_fields(str(fixture))
    assert has_acroform is True

    doc_type = route_doc_type(
        {"format": "native_text", "structure": "single", "form_layout": "ifi_official_typed"},
        text_layer=None,
        has_acroform=has_acroform,
    )
    assert doc_type == "ifi_typed_form_submission"
