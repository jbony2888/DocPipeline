"""
CSV writer module: safely appends records to CSV files with frozen headers.
"""

import csv
import os
from pathlib import Path
from pipeline.schema import SubmissionRecord


# Frozen CSV headers
CSV_HEADERS = [
    "submission_id",
    "student_name",
    "school_name",
    "grade",
    "teacher_name",
    "city_or_location",
    "word_count",
    "ocr_confidence_avg",
    "review_reason_codes",
    "artifact_dir"
]


def _ensure_csv_headers(filepath: str) -> None:
    """
    Ensures CSV file exists with correct headers.
    Creates file with headers if it doesn't exist.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    if not path.exists():
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()


def append_to_csv(record: SubmissionRecord, output_dir: str = "outputs") -> str:
    """
    Appends a submission record to the appropriate CSV file.
    
    Routes to:
        - submissions_clean.csv (if not needs_review)
        - submissions_needs_review.csv (if needs_review)
    
    Args:
        record: SubmissionRecord to write
        output_dir: Output directory for CSV files
        
    Returns:
        Path to the CSV file written
    """
    # Determine target file
    if record.needs_review:
        filename = "submissions_needs_review.csv"
    else:
        filename = "submissions_clean.csv"
    
    filepath = os.path.join(output_dir, filename)
    
    # Ensure file exists with headers
    _ensure_csv_headers(filepath)
    
    # Prepare row data
    row = {
        "submission_id": record.submission_id,
        "student_name": record.student_name or "",
        "school_name": record.school_name or "",
        "grade": record.grade if record.grade is not None else "",
        "teacher_name": record.teacher_name or "",
        "city_or_location": record.city_or_location or "",
        "word_count": record.word_count,
        "ocr_confidence_avg": f"{record.ocr_confidence_avg:.2f}" if record.ocr_confidence_avg else "",
        "review_reason_codes": record.review_reason_codes,
        "artifact_dir": record.artifact_dir
    }
    
    # Append row
    with open(filepath, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writerow(row)
    
    return filepath


def get_csv_stats(output_dir: str = "outputs") -> dict:
    """
    Returns statistics about CSV files.
    
    Returns:
        dict with counts for clean and needs_review records
    """
    stats = {
        "clean_count": 0,
        "needs_review_count": 0,
        "clean_file": os.path.join(output_dir, "submissions_clean.csv"),
        "needs_review_file": os.path.join(output_dir, "submissions_needs_review.csv")
    }
    
    # Count clean records
    clean_path = Path(stats["clean_file"])
    if clean_path.exists():
        with open(clean_path, 'r', encoding='utf-8') as f:
            stats["clean_count"] = sum(1 for _ in csv.DictReader(f))
    
    # Count needs_review records
    review_path = Path(stats["needs_review_file"])
    if review_path.exists():
        with open(review_path, 'r', encoding='utf-8') as f:
            stats["needs_review_count"] = sum(1 for _ in csv.DictReader(f))
    
    return stats

