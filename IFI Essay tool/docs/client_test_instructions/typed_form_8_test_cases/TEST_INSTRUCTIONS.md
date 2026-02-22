# Client Test Instructions: Typed Form (8 Test Cases)

This document explains how to test the **8 typed-form test cases** (tc01–tc08) in the IFI Essay tool.

## What You're Testing

Eight PDFs representing the **standard IFI typed form** (26-IFI-Essay-Form-Eng-and-Spanish). The pipeline should:

- **tc01–tc05**: Extract student name, school, and grade correctly.
- **tc06–tc08**: Flag each for **Needs Review** because one required field is missing (grade, student name, or school name). A record is still created so staff can fill in the missing data.

## Test Files

The 8 test PDFs are in **this folder**:

- tc01_standard_form_26-IFI-filled.pdf    → Jordan Altman, Lincoln Park High School, Grade 10
- tc02_standard_form_26-IFI-filled.pdf    → Maria Santos, Roosevelt Elementary, Grade 6
- tc03_standard_form_26-IFI-filled.pdf    → Alex Chen, Whitney Young Magnet High School, Grade 12
- tc04_standard_form_26-IFI-filled.pdf    → Sofia Williams, Oak Park Elementary, Grade 3
- tc05_standard_form_26-IFI-filled.pdf    → Ethan Johnson, Early Learning Center, Grade K
- tc06_standard_form_missing_grade.pdf    → Missing grade → Review Reason: Missing Grade
- tc07_standard_form_missing_student_name.pdf → Missing student name → Review Reason: Missing Student Name
- tc08_standard_form_missing_school_name.pdf  → Missing school name → Review Reason: Missing School Name

## How to Test via the Web App

1. Go to the **IFI Essay Gateway** dashboard.
2. Open **1️⃣ Upload Entry Forms**.
3. Choose **Multiple Entries** (or Single Entry if testing one at a time).
4. Select the 8 test case PDFs (or a subset).
5. Click **Process Entries**.
6. Wait for the email notification that processing is complete.
7. Open the **Needs Review** or **All Records** view.
8. **Verify tc01–tc05**: Each record should show the correct student name, school, and grade.
9. **Verify tc06–tc08**: Each should appear in **Needs Review** with the correct reason:
   - tc06: **Missing Grade**
   - tc07: **Missing Student Name**
   - tc08: **Missing School Name**

## Expected Extraction Values

| File | Student Name | School Name | Grade |
|------|--------------|-------------|-------|
| tc01 | Jordan Altman | Lincoln Park High School | 10 |
| tc02 | Maria Santos | Roosevelt Elementary | 6 |
| tc03 | Alex Chen | Whitney Young Magnet High School | 12 |
| tc04 | Sofia Williams | Oak Park Elementary | 3 |
| tc05 | Ethan Johnson | Early Learning Center | K |
| tc06 | Sam Rivera | Westside Middle School | *(empty)* |
| tc07 | *(empty)* | Northside Academy | 8 |
| tc08 | Jasmine Lee | *(empty)* | 7 |

## Regenerating Test PDFs (Optional)

If you need to recreate the test case PDFs (e.g., after updating the source form):

```bash
cd "IFI Essay tool"
python scripts/generate_typed_form_test_cases.py
```

Outputs are written to `docs/typed-form-submission/`.

## Running the Regression Harness (Optional)

For automated validation from the command line:

```bash
cd "IFI Essay tool"
python scripts/regression_check.py \
  --pdf-dir "docs/client_test_instructions/typed_form_8_test_cases" \
  --pdf-glob "tc*.pdf" \
  --output-dir artifacts/harness_runs/typed_form_test_cases
```

This processes all 8 PDFs and asserts that tc06–tc08 are flagged with the correct review reasons.
