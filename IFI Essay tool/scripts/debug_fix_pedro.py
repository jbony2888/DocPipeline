from pathlib import Path

from pipeline.ocr import get_ocr_provider
from pipeline.runner import split_contact_vs_essay
from pipeline.extract import (
    extract_value_near_label,
    STUDENT_NAME_ALIASES,
    SCHOOL_ALIASES,
    GRADE_ALIASES,
    parse_grade,
)


PDF_PATH = Path("docs/pedro.pdf").resolve()


def main() -> None:
    print(f"Using PDF: {PDF_PATH}")
    provider = get_ocr_provider("google")

    # Run OCR (full page text)
    ocr_res = provider.process_image(str(PDF_PATH))
    full_text = ocr_res.text or ""
    print(f"OCR chars: {len(full_text)}")

    # Use the same segmentation splitter, but we only care about the contact block
    contact_block, _ = split_contact_vs_essay(full_text)
    lines = [ln.strip() for ln in contact_block.split("\n") if ln.strip()]
    print(f"Contact lines: {len(lines)}")

    # Strict rule: only take values that come AFTER the labels, never from other header text
    student_name = extract_value_near_label(
        lines, STUDENT_NAME_ALIASES, max_length=40, value_after_label_only=True
    )
    school_name = extract_value_near_label(
        lines, SCHOOL_ALIASES, max_length=120, value_after_label_only=True
    )
    grade_text = extract_value_near_label(
        lines, GRADE_ALIASES, max_length=30, value_after_label_only=True
    )
    grade = parse_grade(grade_text) if grade_text else None

    print("\n=== STRICT LABEL-BASED RESULT (pedro.pdf) ===")
    print("Student (from Student's Name label):", repr(student_name))
    print("School  (from School/Escuela label):", repr(school_name))
    print("Grade   (from Grade/Grado label):", repr(grade))
    print("Raw grade_text:", repr(grade_text))


if __name__ == "__main__":
    main()

