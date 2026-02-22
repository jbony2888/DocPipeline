from scripts.export_logs import (
    build_artifact_index_entry,
    compute_summary_metrics,
    hash_or_plain,
    normalize_reason_codes,
)


def test_hashing_default_no_plain_pii():
    value = "Lincoln Elementary"
    out = hash_or_plain(value=value, include_pii=False, salt="unit-test-salt")
    assert out is not None
    assert out != value
    assert len(out) == 64


def test_reason_code_normalization_to_enum_list():
    raw = "missing_grade; EMPTY_ESSAY,low_confidence; EMPTY_ESSAY"
    out = normalize_reason_codes(raw)
    assert out == ["EMPTY_ESSAY", "LOW_CONFIDENCE", "MISSING_GRADE"]


def test_artifact_index_marks_missing_files():
    available = [
        "user/run/artifacts/run/chunk_0_abcd1234ef56/validation.json",
        "user/run/artifacts/run/chunk_0_abcd1234ef56/ocr_summary.json",
    ]
    entry = build_artifact_index_entry(
        submission_id="abcd1234ef56",
        expected_files=["analysis.json", "validation.json", "ocr_summary.json", "traceability.json"],
        available_paths=available,
    )
    assert entry["artifact_missing"] is True
    assert "analysis.json" in entry["missing_files"]
    assert entry["present_flags"]["validation.json"] is True


def test_summary_metrics_fixture_values():
    submissions = [
        {
            "submission_id": "s1",
            "doc_class": "SINGLE_TYPED",
            "needs_review": True,
            "reason_codes": ["EMPTY_ESSAY", "MISSING_GRADE"],
            "format": "native_text",
            "ocr_conf_avg": 0.9,
            "ocr_conf_min": 0.8,
            "ocr_conf_p10": 0.85,
            "ocr_char_count": 400,
            "_student_name_raw_for_metrics": "This is a sentence fragment",
            "parent_submission_id": "p1",
            "page_count": 8,
        },
        {
            "submission_id": "s2",
            "doc_class": "SINGLE_TYPED",
            "needs_review": False,
            "reason_codes": [],
            "format": "native_text",
            "ocr_conf_avg": 0.95,
            "ocr_conf_min": 0.9,
            "ocr_conf_p10": 0.92,
            "ocr_char_count": 500,
            "_student_name_raw_for_metrics": "John Doe",
            "parent_submission_id": "p1",
            "page_count": 8,
        },
        {
            "submission_id": "s3",
            "doc_class": "SINGLE_SCANNED",
            "needs_review": True,
            "reason_codes": ["LOW_CONFIDENCE"],
            "format": "image_only",
            "ocr_conf_avg": 0.35,
            "ocr_conf_min": 0.2,
            "ocr_conf_p10": 0.25,
            "ocr_char_count": 120,
            "_student_name_raw_for_metrics": "Jane Smith",
            "parent_submission_id": "p2",
            "page_count": 1,
        },
    ]
    chunks = [
        {"artifact_missing": False},
        {"artifact_missing": True},
        {"artifact_missing": False},
    ]
    artifacts = [
        {"artifact_missing": False},
        {"artifact_missing": True},
        {"artifact_missing": False},
    ]
    summary = compute_summary_metrics(submissions, chunks, artifacts)

    assert summary["counts_by_doc_class"]["SINGLE_TYPED"] == 2
    assert "LOW_CONFIDENCE" in summary["reason_code_counts"]
    assert summary["artifacts_missing_rate"] == (1 / 3)
    assert summary["false_empty_essay_rate"] == 1.0
    assert isinstance(summary["top_reason_pairs"], list)
    assert "native_text" in summary["ocr_confidence_histograms"]
    # parent p1 has two chunks/submissions -> multi detected.
    assert summary["multi_chunk_stats"]["multi_detection_rate"] > 0.0
