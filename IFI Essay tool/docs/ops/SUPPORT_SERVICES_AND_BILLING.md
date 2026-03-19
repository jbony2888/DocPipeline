# Support Services — Scope & Billing (Template)

**Purpose:** Define what you charge for so clients understand value and you can **invoice with confidence**.  
**Customize:** Replace all `[BRACKETS]` with your business name, rates, and policies. This is not legal advice—have counsel review contracts.

---

## 1. Why this system needs paid support

The IFI Essay / DocPipeline stack is **not “set and forget”**:

| Area | Reality |
|------|--------|
| **Third-party APIs** | Google Cloud Vision, Groq, Supabase, hosting (e.g. Render)—keys, quotas, billing alerts, and outages need someone who knows the codebase. |
| **Data integrity** | Submissions can show **multiple rows per file**, review flags, and extraction errors; **official counts** require agreed rules and sometimes SQL—not just the admin UI. |
| **Security** | Service role keys, admin access, RLS, and env vars are **high impact** if mishandled. |
| **Incidents** | Workers, Redis, queue backlogs, failed jobs, and storage path issues need **debugging time**. |

**Paid support** = reserved capacity + expertise to keep the contest pipeline running, explain data, and fix production issues.

---

## 2. What you can sell (package ideas)

Pick what fits your practice; adjust names and prices.

### Option A — **Incident / time & materials**
- **Rate:** $[___] / hour (or $[___] / 15-minute increment), minimum [__] hours per ticket.
- **Billing:** Monthly invoice from timesheets or ticket log.
- **Good for:** Occasional questions, small fixes, ad-hoc analysis.

### Option B — **Monthly retainer**
- **Fee:** $[___] / month for up to **[__] hours** included.
- **Overage:** $[___] / hour after included hours.
- **Rollover:** [Yes, up to __ hours / No].
- **Good for:** Active contest season, predictable budget for the org.

### Option C — **Contest season bundle**
- **Flat fee:** $[___] for **[start date] – [end date]** including:
  - [__] hours/month proactive monitoring (define what that means)
  - [__] business-hour response for **Severity 1** (define below)
  - Deployment assistance for agreed releases
- **Good for:** Fixed-price buyers; cap your hours in writing.

### Option D — **Critical incident only**
- **Retainer:** $[___] / month **retainer** to guarantee **response within [__] hours** + $[___] / hour while working.
- **Good for:** “We only call you when it’s on fire”—still get paid for being on call.

---

## 3. Suggested severity levels (for SLAs)

| Severity | Definition | Example target (you set) |
|----------|------------|---------------------------|
| **1 – Critical** | Contest intake down, no uploads, or data loss risk | First response: [__] hours |
| **2 – Major** | Degraded performance, many failed jobs, wrong data visible | First response: [__] business hours |
| **3 – Minor** | Single user issue, cosmetic bug, how-to question | Best effort / next business day |

**Out of hours:** Define if **evenings/weekends** are 1.5× or 2× rate, or **not included** unless retainer says otherwise.

---

## 4. In scope vs out of scope (protect your time)

### Typically **in scope** (support)
- Troubleshooting production errors (app, worker, Supabase, Storage).
- Explaining **submissions vs rows**, `processing_metrics`, Storage artifacts (with their access).
- Coordinating **credential rotation** and env updates on their host.
- **Small config changes** (env vars, feature flags) agreed in writing.
- **Guidance** on Supabase RLS, backups, and billing alerts (they click; you advise).

### Typically **out of scope** (bill as project or separate SOW)
- **New features** (new reports, deduplication logic, contest rule engines).
- **Major pipeline changes** (new OCR provider, new form types).
- **Data migration** or bulk cleanup scripts without a signed scope.
- **Training large groups** beyond [__] hours unless purchased.
- Issues caused by **unauthorized changes** they made without asking.

Put this list in your **MSA or SOW** so “just a small change” doesn’t eat your month.

---

## 5. What to attach when proposing support

1. **This template** (customized) + **`OPERATIONS_RISK_AND_BUSINESS_DEPENDENCY_REPORT.md`** — shows **complexity and risk** you’re managing.  
2. **`cost-estimate-1000-essays.md`** — shows **API cost literacy** (optional for technical buyers).  
3. Your **contact channel** (email, ticketing, Slack—define boundaries).

---

## 6. Invoicing checklist

- [ ] Signed agreement or PO referencing **rate + retainer + SLA**.  
- [ ] Time log: date, duration, severity, **what you did** (one line per entry).  
- [ ] Separate line items: **Retainer** vs **Overage** vs **Project** (if any).  
- [ ] Payment terms: Net [15/30], late fee if you use one.

---

## 7. One-line pitch (for email)

> *“This pipeline ties together hosted app, databases, file storage, OCR, and AI extraction. Paid support covers production incidents, data questions, and safe changes—so contest operations aren’t dependent on volunteer debugging.”*

---

**File:** `docs/ops/SUPPORT_SERVICES_AND_BILLING.md` — duplicate and rename for each client if you want client-specific PDFs.
