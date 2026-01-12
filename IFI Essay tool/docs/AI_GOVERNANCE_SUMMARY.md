# AI Governance & Quality Assurance Summary
**Technical Appendix for Non-Technical Stakeholders**

---

## System Overview

The IFI Essay Gateway uses AI technology (OCR and LLM) to extract information from handwritten essay submissions. This document explains how quality is measured, how decisions are made, and how human oversight ensures fairness and accuracy.

---

## Quality Assurance Framework

### Three-Layer Quality Control

1. **OCR Quality Score** (Text Extraction)
   - Measures text cleanliness/readability
   - Used for triage only (prioritizing which records need attention)
   - **Not used for approval decisions**

2. **LLM Field Extraction** (Information Extraction)
   - Uses Groq AI (Llama 3.3 70B model)
   - Extracts structured fields (name, school, grade, etc.)
   - Corrects OCR errors through context understanding

3. **Human Review** (Final Decision)
   - **All submissions reviewed by human volunteers**
   - Quality scores guide attention but do not replace review
   - No records are automatically approved

---

## Key Safeguards

### ✅ Human Control Maintained
- **No automatic approval** - Every submission requires human verification
- Quality scores guide reviewer attention, not decisions
- All records are manually checked before finalization

### ✅ Transparency & Auditability
- Complete audit trail for every submission
- Original documents preserved
- All extraction attempts logged
- Review decisions tracked

### ✅ Fairness & Equity
- Same review process for all submissions
- No bias based on handwriting quality
- Low-quality OCR does not disadvantage students
- Manual override available for all fields

### ✅ Error Handling
- Missing information flagged for manual entry
- Low-quality OCR triggers priority review
- Multiple validation checks prevent incorrect data entry
- Original documents accessible for verification

---

## Quality Score Explanation

### What It Is
- A **heuristic estimate** of text cleanliness (0.0 to 1.0)
- Based on letter density and symbol noise
- **Not a probability of correctness**
- **Not a statistical confidence measure**

### What It's Used For
- **Triage**: Identifying which records need immediate attention
- **Prioritization**: Helping reviewers focus on problematic submissions first
- **Flagging**: Alerting reviewers to potential quality issues

### What It's NOT Used For
- ❌ Automatic approval of submissions
- ❌ Determining if information is correct
- ❌ Replacing human judgment
- ❌ Statistical accuracy claims

---

## Technical Details

**OCR Provider:** Google Cloud Vision API  
**LLM Provider:** Groq API (Llama 3.3 70B)  
**Quality Score Method:** Deterministic heuristic (letter density + symbol noise)

**Important Note:** The quality score is a practical tool for workflow management. It is not a guarantee of accuracy or correctness. All submissions undergo human review regardless of score.

---

## Governance Principles

1. **Human-in-the-Loop**: AI assists, humans decide
2. **Transparency**: All processes are documented and auditable
3. **Fairness**: Equal treatment regardless of handwriting quality
4. **Accountability**: Complete audit trail for all decisions
5. **Quality Control**: Multiple validation layers ensure accuracy

---

## Compliance & Ethics

- **Student Data Protection**: Original documents securely stored, access controlled
- **Fair Processing**: No student disadvantaged by handwriting quality
- **Review Rights**: All data can be manually corrected by reviewers
- **Audit Ready**: Full documentation available for compliance reviews
- **Transparent Operations**: This document explains all quality measures

---

## For Reviewers

**Your Role:**
- Review all submissions, regardless of quality score
- Use quality score as a guide, not a rule
- Verify all critical information (name, school, grade)
- Correct any errors found
- Approve only when satisfied with accuracy

**Quality Score Guidelines:**
- **High Score (0.7+)**: Still requires review, but likely fewer issues
- **Medium Score (0.5-0.7)**: Normal for handwriting, check carefully
- **Low Score (<0.5)**: Priority review, verify all fields against original

---

**Document Version:** 1.0  
**Last Updated:** December 2024  
**For Questions:** Contact technical administrator  
**Related Documents:** `CONFIDENCE_SCORE_EXPLANATION.md` (technical details)



