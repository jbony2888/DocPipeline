# Test cases for client submission

| Document type      | Location / files | Notes |
|--------------------|------------------|--------|
| **Standard form**  | This folder: `tc01_standard_form_26-IFI-filled.pdf` … `tc08_standard_form_missing_school_name.pdf` | 8 generated test cases (tc06–tc08 have one required field missing each). |
| **Scanned images** | Existing scanned PDFs in repo | Use as-is; no generation needed. |
| **Typed essays**   | Existing typed freeform PDFs in repo | Use as-is; no generation needed. |

---

# Standard form test cases (26-IFI typed form)

Eight test case PDFs for the **standard IFI typed form** (26-IFI-Essay-Form-Eng-and-Spanish). tc01–tc05 verify extraction; tc06–tc08 have one **required** field left empty each and should be **flagged** (Review Reasons: Missing Grade, Missing School Name, or Missing Student Name).

**Design rule (missing fields):** Submissions with missing required fields (name, grade, or school) must **never fail** processing. They must be **flagged for review** (`needs_review` + the appropriate reason code) and a **record must always be produced** so the submission can be saved and a **human can fill in the missing data**. The regression harness validates this for tc06/tc07/tc08.

## How to generate the PDFs

From the repo root, `cd` into the `IFI Essay tool` folder first:

```bash
cd "IFI Essay tool"
python scripts/generate_typed_form_test_cases.py
```

Optional: pass the filled reference PDF if it is elsewhere:

```bash
python scripts/generate_typed_form_test_cases.py path/to/26-IFI-Essay-Form-Eng-and-Spanish-filled.pdf
```

Outputs are written to `docs/typed-form-submission/` as `tc01_standard_form_26-IFI-filled.pdf` … `tc05_standard_form_26-IFI-filled.pdf`, plus `tc06` (missing grade), `tc07` (missing student name), `tc08` (missing school name).

## Test case manifest (expected extraction)

| File | student_name | school_name | grade | Notes |
|------|--------------|-------------|-------|--------|
| tc01_standard_form_26-IFI-filled.pdf | Jordan Altman | Lincoln Park High School | 10 | High school |
| tc02_standard_form_26-IFI-filled.pdf | Maria Santos | Roosevelt Elementary | 6 | Essay about grandfather |
| tc03_standard_form_26-IFI-filled.pdf | Alex Chen | Whitney Young Magnet High School | 12 | Stepdad / father-figure |
| tc04_standard_form_26-IFI-filled.pdf | Sofia Williams | Oak Park Elementary | 3 | Lower elementary |
| tc05_standard_form_26-IFI-filled.pdf | Ethan Johnson | Early Learning Center | K | Kindergarten |
| tc06_standard_form_missing_grade.pdf | Sam Rivera | Westside Middle School | *(empty)* | **Missing grade** – Review Reasons: Missing Grade |
| tc07_standard_form_missing_student_name.pdf | *(empty)* | Northside Academy | 8 | **Missing student name** – Review Reasons: Missing Student Name |
| tc08_standard_form_missing_school_name.pdf | Jasmine Lee | *(empty)* | 7 | **Missing school name** – Review Reasons: Missing School Name |

## Running the pipeline on these

From the repo root, `cd` into the `IFI Essay tool` folder, then run only the 8 test case PDFs (tc01–tc08):

```bash
cd "IFI Essay tool"
python scripts/regression_check.py --pdf-dir "docs/typed-form-submission" --pdf-glob "tc*.pdf" --output-dir artifacts/harness_runs/typed_form_test_cases
```

The harness will:
- Process all 8 PDFs (no hard failure; each produces a record).
- For tc06/tc07/tc08, assert they are **flagged for review** with the correct reason code (`MISSING_GRADE`, `MISSING_STUDENT_NAME`, `MISSING_SCHOOL_NAME`) so a human can fill in the missing data.

To run on every PDF in the folder (including other sample forms), omit `--pdf-glob` or use `--pdf-glob "*.pdf"`.

Or process individually through the app; each PDF should be classified as typed form (`native_text`, IFI official layout) and yield the corresponding `student_name`, `school_name`, and `grade` in the extracted output.
