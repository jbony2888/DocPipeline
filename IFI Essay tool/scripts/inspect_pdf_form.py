#!/usr/bin/env python3
"""
Inspect a PDF's form widgets and page-0 text layer. Use to debug extraction:
  python scripts/inspect_pdf_form.py path/to/form.pdf

Shows whether the PDF has AcroForm widgets (and their names/values) or is flattened,
and prints the first 60 lines of page-0 text so you can see label/value order.
"""
import sys
from pathlib import Path

# Allow running from repo root or from IFI Essay tool
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_pdf_form.py <path/to.pdf>", file=sys.stderr)
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    doc = fitz.open(str(path))
    page = doc.load_page(0)
    print("=== Page 0 widgets ===")
    widgets = list(page.widgets())
    if not widgets:
        print("(none – PDF may be flattened; extraction will use text layer only)")
    else:
        for w in widgets:
            name = w.field_name or ""
            val = (w.field_value or "").strip()
            if len(val) > 60:
                val = val[:57] + "..."
            print(f"  {name!r} => {val!r}")
    print("\n=== Page 0 text (first 60 lines) ===")
    text = (page.get_text("text") or "").strip()
    for i, ln in enumerate(text.split("\n")[:60]):
        print(f"{i:2} {ln!r}")
    doc.close()


if __name__ == "__main__":
    main()
