#!/usr/bin/env python3
"""
Fill the 26-IFI-Essay-Form (Eng-and-Spanish) with test data and save.
Usage: python scripts/fill_ifi_form.py <input.pdf> <output.pdf>
"""
import sys
from pathlib import Path

import fitz


TEST_DATA = {
    "Student's Name": "Test Student Garcia",
    "Grade": "8",
    "School": "Lincoln Middle School",
    "Essay": "My father means the world to me. He taught me how to ride a bike and always supports my dreams. I am grateful for his love and guidance.",
    "Dad's Name": "Jose Garcia",
    "Dad's Email": "jose.garcia@example.com",
    "Dad's Phone": "555-123-4567",
    "Dad's Response": "I am so proud of my child. This essay touched my heart. Thank you for this opportunity.",
}


def fill_form(input_path: str, output_path: str) -> None:
    doc = fitz.open(input_path)
    page = doc.load_page(0)
    widgets = list(page.widgets())
    for w in widgets:
        name = w.field_name
        if name in TEST_DATA:
            w.field_value = TEST_DATA[name]
            w.update()
        elif name == "Group1":
            pass
    # Set Group1 (Writing About) first option = Father
    group1_radios = [w for w in widgets if w.field_name == "Group1"]
    if group1_radios:
        group1_radios[0].field_value = "On"
        group1_radios[0].update()
    doc.save(output_path, incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
    doc.close()
    print(f"Filled form saved to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python fill_ifi_form.py <input.pdf> <output.pdf>")
        sys.exit(1)
    fill_form(sys.argv[1], sys.argv[2])
