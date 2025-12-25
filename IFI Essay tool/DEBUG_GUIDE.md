# 🔎 Debug Inspector Guide

## ✅ **What's New**

You now have complete visibility into the extraction pipeline! Every submission creates a debug report showing exactly what happened at each stage.

---

## 🎯 **How to Use the Debug Inspector**

### **In Streamlit:**

After processing a submission, click the **"🔎 Debug: Raw OCR Payload & Artifacts"** expander to see:

1. **ocr.json** - Full OCR output with confidence scores
2. **raw_text.txt** - Complete OCR text (what the AI saw)
3. **contact_block.txt** - Text sent to extraction (after segmentation)
4. **essay_block.txt** - Essay text (after segmentation)
5. **extraction_debug.json** - Shows which labels matched and why

---

## 📊 **What to Look For in Raw Payload**

### **1. OCR Quality Issues**

**Check `raw_text.txt` for:**
- Typos: "AIvarez" instead of "Alvarez"
- Character substitutions: "0" instead of "O", "1" instead of "l"
- Missing spaces: "EdvarcP" instead of "Edvarcll"
- Extra characters: "Ede; #llqez" instead of "Eder Alvarez"

**Example from your IFI form:**
```
Line 1:  Andres AIvarez 0 H9uxh   ← OCR errors: AI, 0, H9uxh
Line 10: Andv-es                  ← Hyphen instead of "r"
Line 14: Ede; #llqez               ← Noise characters
Line 15: EdvarcP                   ← Missing letters
```

### **2. Bilingual Labels**

**Check for both English and Spanish:**
```
Grade / Grado                    ← Both languages present
Student's Name
Nombre del Estudiante            ← Spanish label
School
Escuela                          ← Spanish label
Teléfono                         ← Accented Spanish
Phone
```

**Red flag:** If you only see English labels but the form is bilingual, segmentation might be cutting off too early.

### **3. Values in Unexpected Places**

**Common patterns:**
```
Value BEFORE label:
  EdvarcP          ← School name (VALUE)
  School           ← Label
  Escuela

Value AFTER label:
  Grade / Grado    ← Label
  (empty line or other text)
  8                ← Grade value (far away)
```

### **4. Header/Footer Noise**

**Words that aren't fields:**
```
Illinois                         ← State, not a field
Fatherhood Initiative           ← Contest name
Deadline: March 19              ← Form metadata
3000 Character Maximum          ← Instructions
```

These get mistaken for field values!

---

## 🧠 **Understanding extraction_debug.json**

### **Structure:**

```json
{
  "extraction_method": "rule-based" or "llm",
  "total_lines": 48,
  "contact_block_preview": ["line1", "line2", ...],
  "matches": {
    "student_name": {
      "aliases_searched": ["name", "nombre del estudiante", ...],
      "value_found": "Andv-es",
      "matched": true
    },
    "school_name": {
      "aliases_searched": ["school", "escuela"],
      "value_found": "EdvarcP",
      "matched": true
    },
    "grade": {
      "aliases_searched": ["grade", "grado"],
      "grade_text_found": null,
      "parsed_grade": 8,
      "matched": true,
      "method": "fallback_scan"  ← Found via fallback, not near label!
    }
  },
  "summary": {
    "fields_extracted": 5,
    "required_fields_found": {
      "student_name": true,
      "school_name": true,
      "grade": true
    }
  }
}
```

### **Key Questions to Answer:**

**Q: Why did it extract "Illinois" as father_figure_name?**
```json
"father_figure_name": {
  "aliases_searched": ["father", "padre", "figura paterna"],
  "value_found": "Illinois",
  "matched": true
}
```
**A:** "Illinois" appears near "Fatherhood Initiative" text, so the extraction matched the word "father" in "Fatherhood" and grabbed "Illinois" as the next line.

**Q: Why did it miss the school name?**
```json
"school_name": {
  "aliases_searched": ["school", "escuela"],
  "value_found": null,
  "matched": false
}
```
**A:** Look at `contact_block_preview` - maybe segmentation cut off before the "School" label appeared, or the value was on the line BEFORE the label (not handled by extraction).

**Q: Why is the grade wrong?**
```json
"grade": {
  "method": "fallback_scan",
  "parsed_grade": 4,  ← Wrong! Should be 8
}
```
**A:** Fallback found a "4" somewhere in the text (maybe from a phone number "773 4/9 7126") before finding the actual grade "8".

---

## 🚨 **Common Issues and Fixes**

### **Issue 1: Wrong Field Value Extracted**

**Symptom:**
```json
"father_figure_name": "Fatherhood"  ← Contest name, not a name!
```

**Debug:**
1. Check `contact_block.txt` - is "Fatherhood Initiative" included?
2. Check `extraction_debug.json` - which line matched?

**Fix:**
- Improve segmentation to exclude header text
- Add "Fatherhood Initiative" to label skip list
- Use LLM extraction (better context understanding)

### **Issue 2: Field Not Found**

**Symptom:**
```json
"school_name": null
```

**Debug:**
1. Check `raw_text.txt` - is the school name in the OCR output?
2. Check `contact_block.txt` - was it included in segmentation?
3. Check `extraction_debug.json` - were the right aliases searched?

**Fix:**
- If missing from OCR: OCR quality issue, try different provider
- If not in contact_block: Segmentation issue, adjust split point
- If in contact_block but not extracted: Add more aliases or use LLM

### **Issue 3: OCR Errors Not Corrected**

**Symptom:**
```json
"student_name": "Ede; #llqez"  ← Should be "Eder Alvarez"
```

**Debug:**
Check `ocr.json` confidence:
```json
"confidence_avg": 0.67  ← 67% confidence, decent but not perfect
```

**Fix:**
- **Use LLM extraction** - GPT/Llama can infer "Ede; #llqez" → "Eder Alvarez"
- Or accept imperfect OCR (manual review will catch it)

### **Issue 4: Bilingual Form Confusion**

**Symptom:**
```json
"student_name": null  ← Extraction failed
```

**Debug:**
`contact_block.txt` shows:
```
Student's Name
Nombre del Estudiante
Andres Alvarez
```

Rule-based extraction looked for value AFTER "Student's Name" but found "Nombre del Estudiante" (another label), so it gave up.

**Fix:**
- LLM extraction handles this naturally
- Or improve rule-based to skip label-like next lines

---

## 🎯 **Debugging Workflow**

### **When extraction fails:**

**Step 1: Check OCR Quality**
```bash
# Look at artifacts/[id]/raw_text.txt
# Ask: Is the student name visible in the text?
```

**Step 2: Check Segmentation**
```bash
# Look at artifacts/[id]/contact_block.txt
# Ask: Were the form fields included?
# Ask: Was header/footer noise excluded?
```

**Step 3: Check Extraction Logic**
```bash
# Look at artifacts/[id]/extraction_debug.json
# Ask: Which aliases were searched?
# Ask: What lines were considered?
# Ask: Why was this candidate chosen?
```

**Step 4: Check LLM vs Rule-Based**
```json
{
  "extraction_method": "rule-based",
  "fallback_reason": "LLM found only 1/3 required fields"
}
```
If falling back to rules often, check Groq API key.

---

## 💡 **Pro Tips**

### **Tip 1: Compare Raw vs Contact Block**

If a field is in `raw_text.txt` but not in `contact_block.txt`, that's a **segmentation issue**.

### **Tip 2: Look for Patterns**

If extraction fails on multiple submissions:
- Same form layout? → Update extraction rules for that form
- Different OCR providers? → One might be better than others
- Always missing grade? → Grade might be in unexpected location

### **Tip 3: Use LLM for Complex Forms**

If you see:
- Bilingual labels
- Values far from labels
- OCR errors
- Complex layouts

→ **Use Groq LLM extraction!** (Set `GROQ_API_KEY`)

### **Tip 4: Export Debug Reports**

Save `extraction_debug.json` from failed submissions to build a test suite:
```bash
# Collect failed cases
cp artifacts/abc123/extraction_debug.json tests/fixtures/failed_cases/
```

Then test improvements against these real-world failures.

---

## 📋 **Checklist: "What Am I Working With?"**

When you open the debug inspector, check:

- [ ] **OCR Quality:** Are there obvious typos/errors in `raw_text.txt`?
- [ ] **Bilingual Labels:** Do I see both English and Spanish?
- [ ] **Value Positions:** Are values on same line as labels, before, or after?
- [ ] **Header Noise:** Do I see contest names, deadlines, instructions in contact block?
- [ ] **Segmentation:** Did contact block include all the form fields?
- [ ] **Extraction Method:** Did it use LLM or fall back to rules?
- [ ] **Match Success:** Which required fields (name, school, grade) were found?
- [ ] **Confidence:** Is OCR confidence above 60%?

---

## 🚀 **Quick Actions**

### **If you see low OCR quality (<60% confidence):**
```bash
# Try Spanish language support (already added)
# Or try Google Vision provider instead of EasyOCR
```

### **If you see segmentation issues:**
```python
# Check pipeline/segment.py
# Adjust contact_end_idx or essay_start_markers
```

### **If you see extraction mismatches:**
```python
# Check pipeline/extract.py
# Add more aliases or improve candidate validation
# OR just use Groq LLM (set GROQ_API_KEY)
```

### **If everything looks right but still fails:**
```bash
# Use LLM extraction (highly recommended!)
export GROQ_API_KEY="your-key-here"
./run.sh
```

---

## 🎓 **Learn from Real Examples**

Your IFI form showed:
1. ✅ **Good:** OCR captured all text (67% confidence)
2. ⚠️ **Issue:** Values appeared BEFORE labels ("EdvarcP" before "School")
3. ⚠️ **Issue:** Grade "8" far from "Grade / Grado" label
4. ⚠️ **Issue:** Header noise ("Illinois", "Fatherhood") mixed with fields
5. ✅ **Fixed:** Improved rule-based extraction + LLM fallback

**Result:** Went from 0/3 fields → 3/3 required fields extracted!

---

## 📚 **Summary**

**The debug inspector shows you:**
- What the OCR saw (raw payload)
- What the segmentation sent to extraction
- Which labels were searched
- What candidates were considered
- Why each field was extracted (or not)

**Use it to:**
- Understand why extraction failed
- Improve rules for specific form layouts
- Decide whether to use LLM extraction
- Build test cases from real failures

---

**Refresh your app and check out the debug inspector now!** 🔎

You can see exactly what's happening with your IFI form extraction.


