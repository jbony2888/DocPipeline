#!/usr/bin/env python3
"""
Generate 5 test case PDFs for the standard IFI typed form (26-IFI-Essay-Form-Eng-and-Spanish).
Reads the filled reference PDF, overwrites form fields with 5 different datasets,
and writes tc01..tc05 into docs/typed-form-submission/.

Usage (from repo root or IFI Essay tool):
  python scripts/generate_typed_form_test_cases.py
  python scripts/generate_typed_form_test_cases.py path/to/source-filled.pdf
"""
import sys
from pathlib import Path

import fitz

# Default: run from "IFI Essay tool" or repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
TYPED_FORM_DIR = REPO_ROOT / "docs" / "typed-form-submission"
DEFAULT_SOURCE = TYPED_FORM_DIR / "26-IFI-Essay-Form-Eng-and-Spanish-filled.pdf"

# 5 test cases with distinct student/school/grade/essay/parent data for client testing
# Essay field: 3000 character max per form; these use longer blocks for realistic testing.
TEST_CASES = [
    {
        "id": "tc01",
        "student_name": "Jordan Altman",
        "grade": "10",
        "school": "Arbury Hills School",
        "essay": "My dad has always been my role model. He works long hours but never misses a game or a school play. When I was little he taught me to ride a bike in the park, and when I fell he didn't make a big deal—he just said get back on. That's how he is about everything: calm, steady, and there.\n\nI used to get frustrated when he had to travel for work. Now I see how hard he works so we can have a good life, and I try to tell him I notice. We don't always talk a lot, but when we do it matters. He's the one who told me it's okay to not have everything figured out yet, and that trying counts more than being perfect.\n\nI want to be like him when I grow up—someone who shows up, who keeps his word, and who makes people feel like they matter. I'm grateful for my dad.",
        "dad_name": "Michael Altman",
        "dad_email": "m.altman@example.com",
        "dad_phone": "312-555-0101",
        "dad_response": "Jordan wrote this on his own. I am very proud of him.",
    },
    {
        "id": "tc02",
        "student_name": "Maria Santos",
        "grade": "6",
        "school": "Bridgeport Catholic Academy",
        "essay": "My grandfather taught me to garden. Every summer we plant tomatoes and peppers and herbs in his backyard. At first I thought it was boring—just dirt and waiting. But he said patience is the key to everything, and when the first tomato turned red I was so excited I ran inside to show my mom.\n\nAbuelo also tells me stories about when he was a boy in Mexico. He had to walk a long way to school and help his family on the farm. He says that's why he loves the soil and growing things—it reminds him of home. When we're in the garden he teaches me the names of plants in Spanish and English.\n\nSometimes we don't even talk; we just water and pull weeds together. I feel close to him there. I hope we can keep gardening together for a long time. My grandfather is my favorite father-figure because he is kind, patient, and he always has time for me.",
        "dad_name": "Carlos Santos",
        "dad_email": "c.santos@example.com",
        "dad_phone": "773-555-0102",
        "dad_response": "Thank you for this contest. Maria loves writing about her abuelo.",
    },
    {
        "id": "tc03",
        "student_name": "Alex Chen",
        "grade": "12",
        "school": "Charles J Sahs",
        "essay": "My stepdad came into my life when I was eight. My mom had been single for a while, and I wasn't sure I wanted someone else in our house. I remember being cold to him at first—short answers, staying in my room. He didn't push. He just kept showing up: breakfast on weekends, help with homework, rides to practice.\n\nIt took a few years before I really let him in. There was one night I had a huge fight with my mom and I didn't know where to go. He sat with me on the porch and didn't give a lecture. He said he wasn't trying to replace my dad, but he was there if I needed him. That meant a lot.\n\nNow I'm a senior and I call him Dad. He's the one who helped me fill out college applications and who drives me to visit schools. He chose us every day even when I didn't make it easy. I'm grateful for his patience and his love. That's what a father-figure means to me.",
        "dad_name": "James Chen",
        "dad_email": "j.chen@example.com",
        "dad_phone": "847-555-0103",
        "dad_response": "This means a lot. Alex has grown so much. Grateful to be part of this family.",
    },
    {
        "id": "tc04",
        "student_name": "Sofia Williams",
        "grade": "3",
        "school": "Chicago World Language Academy",
        "essay": "My daddy reads me stories every night before bed. He does the best voices—sometimes he sounds like a bear and sometimes like a little mouse. My favorite is when he reads the dragon book and he makes a big roar. I laugh every time.\n\nOn weekends we go to the park and he pushes me on the swing really high. He says hold on tight and I do. When I'm scared of something like the dark he sits with me until I fall asleep. He says dads are here to keep you safe.\n\nHe also helps me with my homework and we do science experiments in the kitchen. Last week we made a volcano with baking soda and it exploded everywhere. Mommy was not happy but Daddy said it was a good experiment. I love my daddy so much. He is the best dad in the whole world.",
        "dad_name": "David Williams",
        "dad_email": "d.williams@example.com",
        "dad_phone": "630-555-0104",
        "dad_response": "Sofia worked hard on this. We are so proud of our little writer.",
    },
    {
        "id": "tc05",
        "student_name": "Ethan Johnson",
        "grade": "K",
        "school": "Colin Powell Middle School",
        "essay": "I love my dad. He plays with me every day. We go to the park and he pushes me on the swing. We play catch with the ball. Sometimes we build with blocks and he makes really tall towers and I knock them down and we laugh.\n\nMy dad reads me a story at night. He tucks me in and gives me a hug. He says goodnight and I say goodnight dad. I love when he is home on the weekend because we have pancakes and he lets me put the syrup on. He is really strong and he carries me on his shoulders so I can see high. I feel safe when my dad is here. I love my dad.",
        "dad_name": "Robert Johnson",
        "dad_email": "r.johnson@example.com",
        "dad_phone": "815-555-0105",
        "dad_response": "Ethan is in kindergarten and wanted to participate. Thank you for the opportunity.",
    },
    # Test case with MISSING GRADE – use for frontend to verify submission is flagged (needs_review, MISSING_GRADE).
    {
        "id": "tc06",
        "student_name": "Sam Rivera",
        "grade": "",  # Intentionally empty – should be flagged for missing grade
        "school": "Columbia Explorers Academy",
        "essay": "My dad works at the hospital. He helps people get better. I want to be like him when I grow up. He always has time to play with me on his days off.",
        "dad_name": "Miguel Rivera",
        "dad_email": "m.rivera@example.com",
        "dad_phone": "312-555-0199",
        "dad_response": "Sam wrote this himself. We are proud of him.",
    },
    # Test case with MISSING STUDENT NAME – should be flagged (needs_review, MISSING_STUDENT_NAME).
    {
        "id": "tc07",
        "student_name": "",  # Intentionally empty – required for minimum submission
        "grade": "8",
        "school": "Gage Park High School",
        "essay": "My father is a firefighter. He is brave and helps people. I want to be like him when I grow up.",
        "dad_name": "Chris Moore",
        "dad_email": "c.moore@example.com",
        "dad_phone": "312-555-0200",
        "dad_response": "Proud of my son for entering this contest.",
    },
    # Test case with MISSING SCHOOL NAME – should be flagged (needs_review, MISSING_SCHOOL_NAME).
    {
        "id": "tc08",
        "student_name": "Jasmine Lee",
        "grade": "7",
        "school": "",  # Intentionally empty – required for minimum submission
        "essay": "My dad coaches my soccer team. He is fair and never yells. We practice every week and he says effort matters more than winning.",
        "dad_name": "Daniel Lee",
        "dad_email": "d.lee@example.com",
        "dad_phone": "773-555-0201",
        "dad_response": "Jasmine loves writing. Thank you for this opportunity.",
    },
]


def form_data_for_test_case(tc: dict) -> dict:
    """Map test case dict to form field names used by 26-IFI PDF."""
    return {
        "Student's Name": tc["student_name"],
        "Grade": tc["grade"],
        "School": tc["school"],
        "Essay": tc["essay"],
        "Dad's Name": tc["dad_name"],
        "Dad's Email": tc["dad_email"],
        "Dad's Phone": tc["dad_phone"],
        "Dad's Response": tc["dad_response"],
    }


def fill_form_from_data(doc: fitz.Document, data: dict) -> None:
    """Overwrite form fields on page 0 with data. Handles Group1 (Writing About) if present. Empty strings clear the field."""
    page = doc.load_page(0)
    widgets = list(page.widgets())
    for w in widgets:
        name = w.field_name
        if name in data:
            val = data[name] if data[name] is not None else ""
            w.field_value = val
            w.update()
    # Writing About: first radio = Father (same as reference)
    group1_radios = [w for w in widgets if w.field_name == "Group1"]
    if group1_radios:
        group1_radios[0].field_value = "On"
        group1_radios[0].update()


def clear_field_by_name(doc: fitz.Document, field_name: str) -> None:
    """Force-clear a form field by name (so empty value actually shows as blank in viewers)."""
    page = doc.load_page(0)
    for w in page.widgets():
        if w.field_name == field_name:
            w.field_value = ""
            w.update()
            break


# Output filenames for validation test cases (missing required field)
MISSING_FIELD_OUTPUT_NAMES = {
    "tc06": "tc06_standard_form_missing_grade.pdf",
    "tc07": "tc07_standard_form_missing_student_name.pdf",
    "tc08": "tc08_standard_form_missing_school_name.pdf",
}


def generate_test_case_pdfs(source_pdf: Path, out_dir: Path) -> list[Path]:
    """Generate test case PDFs (tc01–tc05 + tc06–tc08 missing-field cases); return list of output paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for tc in TEST_CASES:
        doc = fitz.open(str(source_pdf))
        data = form_data_for_test_case(tc)
        fill_form_from_data(doc, data)
        # Force-clear fields that must be empty so viewers show them blank (tc06=Grade, tc07=Student, tc08=School)
        if tc.get("id") == "tc06":
            clear_field_by_name(doc, "Grade")
        elif tc.get("id") == "tc07":
            clear_field_by_name(doc, "Student's Name")
        elif tc.get("id") == "tc08":
            clear_field_by_name(doc, "School")
        out_name = MISSING_FIELD_OUTPUT_NAMES.get(tc.get("id")) or f"{tc['id']}_standard_form_26-IFI-filled.pdf"
        out_path = out_dir / out_name
        doc.save(str(out_path), incremental=False, encryption=fitz.PDF_ENCRYPT_NONE, clean=True)
        doc.close()
        created.append(out_path)
        print(f"  {out_path.name}")
    return created


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.is_file():
        print(f"Source PDF not found: {source}")
        print("Usage: python scripts/generate_typed_form_test_cases.py [path/to/filled.pdf]")
        sys.exit(1)
    print(f"Source: {source}")
    print(f"Output dir: {TYPED_FORM_DIR}")
    print("Generating test case PDFs (including tc06–tc08 missing required fields):")
    generate_test_case_pdfs(source, TYPED_FORM_DIR)
    print("Done. See docs/typed-form-submission/TEST_CASES.md for expected extraction.")


if __name__ == "__main__":
    main()
