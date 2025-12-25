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
    "father_figure_name",
    "phone",
    "email",
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
        "father_figure_name": record.father_figure_name or "",
        "phone": record.phone or "",
        "email": record.email or "",
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


def load_records_from_csv(csv_type: str, output_dir: str = "outputs") -> list[dict]:
    """
    Loads all records from a CSV file.
    
    Args:
        csv_type: "clean" or "needs_review"
        output_dir: Output directory for CSV files
        
    Returns:
        List of record dictionaries
    """
    if csv_type == "clean":
        filename = "submissions_clean.csv"
    elif csv_type == "needs_review":
        filename = "submissions_needs_review.csv"
    else:
        raise ValueError(f"csv_type must be 'clean' or 'needs_review', got '{csv_type}'")
    
    filepath = os.path.join(output_dir, filename)
    records = []
    
    if Path(filepath).exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            records = list(reader)
    
    return records


def remove_record_from_csv(submission_id: str, csv_type: str, output_dir: str = "outputs") -> bool:
    """
    Removes a record from a CSV file by submission_id.
    
    Args:
        submission_id: The submission ID to remove
        csv_type: "clean" or "needs_review"
        output_dir: Output directory for CSV files
        
    Returns:
        True if record was found and removed, False otherwise
    """
    if csv_type == "clean":
        filename = "submissions_clean.csv"
    elif csv_type == "needs_review":
        filename = "submissions_needs_review.csv"
    else:
        raise ValueError(f"csv_type must be 'clean' or 'needs_review', got '{csv_type}'")
    
    filepath = os.path.join(output_dir, filename)
    
    if not Path(filepath).exists():
        return False
    
    # Read all records
    records = []
    found = False
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("submission_id") != submission_id:
                records.append(row)
            else:
                found = True
    
    # Write back all records except the one to remove
    if found:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(records)
    
    return found


def update_record_in_csv(record: SubmissionRecord, csv_type: str, output_dir: str = "outputs") -> bool:
    """
    Updates a record in a CSV file. If the record doesn't exist, does nothing.
    
    Args:
        record: The updated SubmissionRecord
        csv_type: "clean" or "needs_review"
        output_dir: Output directory for CSV files
        
    Returns:
        True if record was found and updated, False otherwise
    """
    if csv_type == "clean":
        filename = "submissions_clean.csv"
    elif csv_type == "needs_review":
        filename = "submissions_needs_review.csv"
    else:
        raise ValueError(f"csv_type must be 'clean' or 'needs_review', got '{csv_type}'")
    
    filepath = os.path.join(output_dir, filename)
    
    if not Path(filepath).exists():
        return False
    
    # Read all records
    records = []
    found = False
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("submission_id") == record.submission_id:
                # Update this record
                row = {
                    "submission_id": record.submission_id,
                    "student_name": record.student_name or "",
                    "school_name": record.school_name or "",
                    "grade": record.grade if record.grade is not None else "",
                    "teacher_name": record.teacher_name or "",
                    "city_or_location": record.city_or_location or "",
                    "father_figure_name": record.father_figure_name or "",
                    "phone": record.phone or "",
                    "email": record.email or "",
                    "word_count": record.word_count,
                    "ocr_confidence_avg": f"{record.ocr_confidence_avg:.2f}" if record.ocr_confidence_avg else "",
                    "review_reason_codes": record.review_reason_codes,
                    "artifact_dir": record.artifact_dir
                }
                found = True
            records.append(row)
    
    # Write back all records
    if found:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(records)
    
    return found


def move_record_between_csvs(submission_id: str, from_type: str, to_type: str, output_dir: str = "outputs") -> bool:
    """
    Moves a record from one CSV file to another.
    
    Args:
        submission_id: The submission ID to move
        from_type: "clean" or "needs_review" - source file
        to_type: "clean" or "needs_review" - destination file
        output_dir: Output directory for CSV files
        
    Returns:
        True if record was found and moved, False otherwise
    """
    # Load the record from source
    source_records = load_records_from_csv(from_type, output_dir)
    record_to_move = None
    
    for record in source_records:
        if record.get("submission_id") == submission_id:
            record_to_move = record
            break
    
    if not record_to_move:
        return False
    
    # Remove from source
    remove_record_from_csv(submission_id, from_type, output_dir)
    
    # Convert dict to SubmissionRecord and add to destination
    # Handle missing optional fields
    grade = record_to_move.get("grade", "")
    grade = int(grade) if grade and grade.strip() else None
    
    ocr_conf = record_to_move.get("ocr_confidence_avg", "")
    ocr_conf = float(ocr_conf) if ocr_conf and ocr_conf.strip() else None
    
    word_count = record_to_move.get("word_count", "0")
    word_count = int(word_count) if word_count and word_count.strip() else 0
    
    # Determine needs_review based on destination
    needs_review = (to_type == "needs_review")
    
    new_record = SubmissionRecord(
        submission_id=record_to_move.get("submission_id", ""),
        student_name=record_to_move.get("student_name") or None,
        school_name=record_to_move.get("school_name") or None,
        grade=grade,
        teacher_name=record_to_move.get("teacher_name") or None,
        city_or_location=record_to_move.get("city_or_location") or None,
        father_figure_name=record_to_move.get("father_figure_name") or None,
        phone=record_to_move.get("phone") or None,
        email=record_to_move.get("email") or None,
        word_count=word_count,
        ocr_confidence_avg=ocr_conf,
        needs_review=needs_review,
        review_reason_codes=record_to_move.get("review_reason_codes", ""),
        artifact_dir=record_to_move.get("artifact_dir", "")
    )
    
    # Add to destination
    append_to_csv(new_record, output_dir)
    
    return True


