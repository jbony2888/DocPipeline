# Cost Estimate: Processing 1,000 Essays (Groq + Google Cloud Vision)

This document estimates the cost of processing **1,000 IFI Fatherhood Essay submissions** using the current pipeline with **Groq** (LLM extraction) and **Google Cloud Vision** (OCR).

---

## Pipeline Usage Summary

| Service | Where used | Per-essay usage |
|--------|------------|------------------|
| **Google Cloud Vision** | `pipeline/ocr.py` → `GoogleVisionOcrProvider.process_image()` | **1 API call per PDF page** (`document_text_detection`). PDFs are rendered page-by-page (300 DPI PNG), then each image is sent to Vision. |
| **Groq** | `pipeline/extract_ifi.py` → `extract_ifi_submission()` | **1 LLM call per essay**. Model: `llama-3.3-70b-versatile`. Full OCR text + classification/extraction prompt; JSON response. |

There is **no** separate contact-block LLM call in the main path: the runner uses `extract_fields_ifi()` only, which calls `extract_ifi_submission()` once per essay.

---

## Assumptions for 1,000 Essays

- **Pages per essay:** IFI forms are typically 1–2 pages. Assumed **1.5 pages per essay** on average.
- **Vision images:** 1,000 essays × 1.5 pages ≈ **1,500 images**.
- **Groq:** 1,000 essays → **1,000 LLM requests**.
- **Input tokens per essay:** System message (~50) + user prompt template (~2,000) + OCR text (1–2 pages ≈ 2,000–5,500 tokens) → **~6,000 input tokens** per essay (conservative).
- **Output tokens per essay:** Structured JSON (classification + fields + essay text) → **~500 output tokens** per essay.

---

## Pricing (as of 2024–2025)

### Groq (Llama 3.3 70B Versatile)

- **Paid (on-demand):** Input $0.59 per 1M tokens, Output $0.79 per 1M tokens. [Groq Pricing](https://groq.com/pricing)
- **Free tier rate limits** (organization-level; you hit whichever limit first). [Groq Rate Limits](https://console.groq.com/docs/rate-limits):

| Limit | Free tier (llama-3.3-70b-versatile) |
|-------|-------------------------------------|
| RPM   | 30 requests per minute              |
| RPD   | 1,000 requests per day              |
| TPM   | 12,000 tokens per minute            |
| **TPD** | **100,000 tokens per day**        |

- **Effective free-tier capacity for this pipeline:** ~**6,500 tokens per essay** (input + output) → **100,000 ÷ 6,500 ≈ 15 essays per day**. TPD is the bottleneck (RPD would allow 1,000/day).
- **Time to process 1,000 essays on Groq free tier only:** 1,000 ÷ 15 ≈ **67 days** (if you max out TPD every day).

### Google Cloud Vision (Document Text Detection)

- **First 1,000 units/month:** Free  
- **1,001–5,000,000 units/month:** $1.50 per 1,000 units  
- Each image (including each PDF page) = 1 unit  
- Source: [Cloud Vision API Pricing](https://cloud.google.com/vision/pricing)

---

## Cost Calculation for 1,000 Essays

### Groq

| Item | Calculation | Cost |
|------|-------------|------|
| Input tokens | 1,000 × 6,000 = 6M tokens → 6 × $0.59 | **$3.54** |
| Output tokens | 1,000 × 500 = 0.5M tokens → 0.5 × $0.79 | **$0.40** |
| **Groq total** | | **~$3.94** |

### Google Cloud Vision

| Item | Calculation | Cost |
|------|-------------|------|
| Images (pages) | 1,500 images | |
| Free tier | First 1,000 units free | $0 |
| Billable | 500 units × ($1.50 / 1,000) | **$0.75** |
| **Vision total** | | **~$0.75** |

---

## Total Estimated Cost

| Service | Cost |
|---------|------|
| Groq | ~$3.94 |
| Google Cloud Vision | ~$0.75 |
| **Total** | **~$4.70** |

So processing **1,000 essays** with Groq + Google Cloud Vision is approximately **$4.50–5.00**, depending on pages per essay and token usage.

---

## Groq Free Tier (no payment)

On the **free tier**, Groq limits **llama-3.3-70b-versatile** to **100K tokens per day (TPD)** (plus 30 RPM, 1K RPD, 12K TPM). Our pipeline uses ~6,500 tokens per essay, so:

| Metric | Value |
|--------|--------|
| Essays per day (free tier, max) | **~15** (limited by 100K TPD) |
| Days to process 1,000 essays (free tier only) | **~67 days** |
| Cost | **$0** (within free limits) |

Google Vision’s free tier (first 1,000 units/month) covers about **667 essays/month** at 1.5 pages/essay (1,000 images). So for 1,000 essays in a month, Vision would use 500 billable units ≈ **$0.75** unless you spread the work over multiple months to stay within 1,000 free images.

**Summary (free tier only):** ~**15 essays/day** on Groq; 1,000 essays takes ~**67 days** and costs **~$0** on Groq and **~$0.75** on Vision (if done in one month). To go faster or process more per day, use a paid Groq plan or credits.

---

## Using $300 Credits (Google + Groq)

If you have **$300 in credits from Google Cloud** and **$300 in credits from Groq** (paid/Developer plan or sign-up credits—*not* the free-tier rate limits):

| Provider | Cost per 1,000 essays | $300 credit covers |
|---------|------------------------|--------------------|
| Groq | ~$3.94 | **~76,000 essays** |
| Google Vision | ~$0.75 | **~400,000 essays** |

**Limiting factor:** Groq. Your **$300 Groq credit** runs out first.

- **Rough capacity:** **~76,000 essays** before Groq credits are used up.
- Over that run, Google Vision would use about **$57** of the $300 Google credit (76 × $0.75), so most of the Google credit remains.

**Summary:** With $300 from each provider (and paid Groq usage, not free tier), you can process on the order of **76,000 essays** at no out-of-pocket cost; Groq is the bottleneck.

---

## Variability and Edge Cases

1. **Pages per essay:** If most submissions are 2-page forms, Vision cost rises (e.g. 2,000 images → 1,000 billable → **$1.50**). If most are 1 page, Vision cost drops (1,000 images → **$0** within free tier).
2. **Token usage:** Longer OCR text or longer essay text in the JSON increases Groq input/output; shorter forms reduce it. The estimate uses ~6K input / ~500 output per essay as a middle ground.
3. **Chunked PDFs:** When the pipeline processes chunked PDFs, it may call `ocr_pdf_pages()` in addition to `process_image()`, effectively **doubling Vision API calls** for that submission. If a large share of the 1,000 essays are chunked, Vision cost could be roughly twice the above.
4. **Free tiers:** Vision’s first 1,000 units/month are free. Groq free tier for **llama-3.3-70b-versatile** is **100K TPD** → ~15 essays/day (see “Groq Free Tier” above). Check [Groq Rate Limits](https://console.groq.com/docs/rate-limits) and [limits page](https://console.groq.com/settings/limits) for your org.

---

## Quick Reference

| Scenario | Groq | Vision | Notes |
|----------|------|--------|------|
| **Paid (per 1,000 essays)** | ~\$3.94 | ~\$0.75 | **~\$4.70 total** |
| **Groq free tier only** | \$0 | ~\$0.75 (if &gt;1K images/mo) | **~15 essays/day** (100K TPD); 1,000 essays ≈ 67 days |
| **\$300 credit each** | ~76K essays | ~\$57 used of \$300 | **~76,000 essays** (Groq-limited) |

- **Per essay (paid, average):** ~\$0.0047 total (~\$0.004 Groq + ~\$0.00075 Vision).

Pricing and free-tier limits can change; verify the links below when budgeting.

---

## References

| Source | URL |
|--------|-----|
| **Groq – Pricing** | https://groq.com/pricing |
| **Groq – Rate Limits (docs)** | https://console.groq.com/docs/rate-limits |
| **Groq – Organization limits (console)** | https://console.groq.com/settings/limits |
| **Groq – Billing / plans** | https://console.groq.com/settings/billing/plans |
| **Groq – Llama 3.3 70B Versatile (model)** | https://console.groq.com/docs/model/llama-3.3-70b-versatile |
| **Google Cloud – Vision API Pricing** | https://cloud.google.com/vision/pricing |
| **Google Cloud – Vision API quotas** | https://cloud.google.com/vision/quotas |
