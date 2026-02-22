# Client Test Instructions

This folder contains test instructions for each **document type** supported by the IFI Essay tool. Use the subfolders below to run end-to-end tests via the web app or the regression harness.

| Doc Type | Folder | Description |
|----------|--------|-------------|
| **Typed form (8 test cases)** | [typed_form_8_test_cases](./typed_form_8_test_cases/) | Standard IFI typed forms (tc01–tc05 full, tc06–tc08 with one missing field each) |
| **Scanned multi-submission** | [scanned_multi_submission](./scanned_multi_submission/) | Single PDF with multiple scanned essay images; one record per submission |
| **Standard freeform essay** | [standard_freeform_essay](./standard_freeform_essay/) | Typed PDFs with text layer; no OCR; Groq normalization |

Each folder has a `TEST_INSTRUCTIONS.md` with:

- What you're testing
- Where the sample files live
- How to test via the **Web App** (upload → process → verify)
- How to run the **Regression Harness** (command-line validation) when available
