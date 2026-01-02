# Technical Appendix: AI Quality Metrics
**One-Page Summary for Funders, Board Members, and Non-Technical Stakeholders**

---

## Executive Summary

The IFI Essay Gateway uses AI to assist in processing handwritten essay submissions. **This document explains our quality assurance measures in plain language.**

**Key Message:** AI assists human reviewers—it never makes final decisions. Every submission is reviewed by a person before approval.

---

## How Quality is Measured

### OCR Quality Score (0.0 to 1.0)

**What it measures:** Text cleanliness and readability (how clear the extracted text is)

**What it means:**
- **0.9-1.0**: Very clean text, minimal OCR errors
- **0.7-0.9**: Good quality, minor errors
- **0.5-0.7**: Fair quality (normal for handwriting)
- **Below 0.5**: Poor quality, needs careful review

**How it's calculated:** Based on the proportion of readable letters vs. symbols/errors in the extracted text

**Critical point:** This is a **quality estimate**, not a probability of correctness. A high score doesn't guarantee the information is correct—it just means the text looks clean.

---

## What Happens to Each Submission

1. **OCR Processing** (Google Cloud Vision)
   - Converts handwritten form to digital text
   - Calculates quality score (triage only)

2. **Field Extraction** (Groq AI - Llama 3.3 70B)
   - Extracts structured information (name, school, grade, etc.)
   - Corrects OCR errors using AI context understanding

3. **Validation** (Automated Checks)
   - Flags missing required fields
   - Identifies potential errors
   - Categorizes records needing review

4. **Human Review** (Required)
   - **Every submission is reviewed by a human volunteer**
   - Quality score guides attention but doesn't replace review
   - Original document accessible for verification
   - All fields can be manually corrected

5. **Approval** (Human Decision)
   - Only approved after human reviewer confirms accuracy
   - No automatic approval based on AI scores

---

## Governance & Safeguards

### ✅ Human Control
- All submissions require human approval
- AI scores guide workflow, not decisions
- Manual override available for all operations

### ✅ Transparency
- Complete audit trail for every submission
- Original documents preserved
- All extraction attempts logged
- Quality metrics documented

### ✅ Fairness
- Equal treatment regardless of handwriting quality
- No student disadvantaged by poor handwriting
- All records receive same review process

### ✅ Accuracy
- Multiple validation layers
- Human verification required
- Error correction mechanisms in place
- Original documents always accessible

---

## Technology Stack

- **OCR (Text Extraction):** Google Cloud Vision API
- **AI (Field Extraction):** Groq API with Llama 3.3 70B model
- **Quality Scoring:** Deterministic heuristic (not AI-generated)
- **Human Review:** Required for all submissions

---

## Business-Safe Statement

*"The system computes an OCR quality score that estimates the cleanliness and readability of extracted text. For Google Vision OCR, this score is a deterministic heuristic based on letter density and symbol noise, not a statistical confidence value. The score is used exclusively for triage and review prioritization. All submissions undergo human review regardless of score. Structured field extraction and validation are handled separately using an LLM and rule-based checks, ensuring that no record is finalized automatically."*

---

## Key Metrics for Reporting

- **Processing Speed:** ~3-7 seconds per submission
- **Extraction Accuracy:** ~90% for student names, ~65% for school/grade (with fallbacks)
- **Human Review Rate:** 100% (all submissions reviewed)
- **Automatic Approval Rate:** 0% (none—all require human approval)

---

## For Funders & Grant Applications

**Governance Statement:**
- AI is used for assistance, not decision-making
- Complete human oversight of all critical operations
- Full transparency and auditability
- Student fairness and equity prioritized
- Compliance-ready documentation

**Risk Mitigation:**
- No automatic approvals prevent errors
- Human review ensures accuracy
- Audit trail supports accountability
- Original documents preserved for verification

---

**Document Version:** 1.0  
**Last Updated:** December 2024  
**Audience:** Non-technical stakeholders, funders, board members  
**Related:** See `CONFIDENCE_SCORE_EXPLANATION.md` for technical details

