# IFI Essay Gateway: AI-Assisted Document Processing

## Executive Summary

An automated pipeline that transforms handwritten student essays into structured, searchable data using OCR and LLM technologies. Built for the IFI Fatherhood Essay Contest to eliminate manual data entry and accelerate the review process.

---

## 1. Use Case

### The Organization
**Illinois Fatherhood Initiative (IFI)** runs an annual essay contest where students write handwritten essays about their fathers or father figures.

### The Problem
| Challenge | Impact |
|-----------|--------|
| **Manual data entry** | Staff spent hours transcribing handwritten essays |
| **Inconsistent formats** | Essays arrived as scanned PDFs with varying quality |
| **Missing information** | Contact details often illegible or incomplete |
| **Slow review cycle** | Bottleneck in processing hundreds of submissions |
| **No searchable archive** | Historical essays locked in paper/PDF format |

### Volume
- **Hundreds of essay submissions** per contest cycle
- Each submission contains:
  - Student name, school, grade
  - Parent/guardian contact (phone, email)
  - Father figure's name
  - Handwritten essay (1-3 pages)

---

## 2. Solution Architecture

### Pipeline Overview

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   INGEST    │───▶│     OCR     │───▶│   EXTRACT   │───▶│  VALIDATE   │
│  (PDF/Image)│    │(Google Vision)   │  (Groq LLM) │    │  (Rules)    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                                │
                                                                ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   EXPORT    │◀───│   REVIEW    │◀───│    STORE    │◀───│   SEGMENT   │
│    (CSV)    │    │  (Human QA) │    │  (Supabase) │    │(Contact/Essay)
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **OCR** | Google Cloud Vision API | Extract text from handwritten documents |
| **LLM** | Groq (Llama 3.3 70B) | Intelligent field extraction & OCR correction |
| **Backend** | Python/Flask | Web application & API |
| **Queue** | Redis + RQ | Background job processing |
| **Database** | Supabase (PostgreSQL) | Record storage & user auth |
| **Storage** | Supabase Storage | PDF artifact storage |
| **Deployment** | Render | Cloud hosting |
| **Local Dev** | Docker Compose | Containerized development |

### Key Components

#### 2.1 OCR Layer (Google Cloud Vision)
- `DOCUMENT_TEXT_DETECTION` for handwriting recognition
- Handles varied paper quality and handwriting styles
- Computes quality score based on text characteristics

#### 2.2 LLM Extraction (Groq)
- Two-phase extraction: classification then field extraction
- Corrects OCR errors using context
- Extracts structured fields:
  - Student name
  - School name
  - Grade level
  - Father figure name
  - Phone number
  - Email address
  - Full essay text

#### 2.3 Fallback Logic
- Rule-based extraction when LLM fails
- Pattern matching for phone numbers, emails
- Keyword detection for school names, grades

#### 2.4 Validation Engine
- Flags records with missing required fields
- Identifies low-confidence OCR results
- Assigns review reason codes:
  - `MISSING_STUDENT_NAME`
  - `MISSING_SCHOOL_NAME`
  - `MISSING_GRADE`
  - `EMPTY_ESSAY`
  - `LOW_CONFIDENCE`

#### 2.5 Review Workflow
- Three-state workflow: `needs_review` → `approved` / `rejected`
- Human reviewers verify and correct extracted data
- Inline editing for quick fixes
- Batch operations for efficiency

---

## 3. Features

### Upload & Processing
- ✅ Single file upload
- ✅ Bulk upload (multiple PDFs)
- ✅ Real-time processing status
- ✅ Background job queue (non-blocking)

### Data Extraction
- ✅ Handwriting OCR with quality scoring
- ✅ LLM-powered field extraction
- ✅ Automatic essay segmentation
- ✅ Contact information parsing

### Review Interface
- ✅ Filter by review status
- ✅ View original PDF alongside extracted data
- ✅ Edit fields inline
- ✅ Approve/reject with one click
- ✅ Batch grouping by school

### Export & Integration
- ✅ CSV export of approved records
- ✅ Full artifact storage (PDF, OCR, structured data)
- ✅ API endpoints for external integration

### Security
- ✅ Supabase authentication (magic links)
- ✅ User-scoped data access
- ✅ Secure credential management

---

## 4. Results

### Before vs After

| Metric | Before (Manual) | After (Automated) |
|--------|-----------------|-------------------|
| **Processing time per essay** | 10-15 minutes | 15-30 seconds |
| **Data entry errors** | Common | Rare (LLM correction) |
| **Searchability** | None (paper files) | Full-text search |
| **Staff hours per contest** | 40-60 hours | 5-10 hours |
| **Turnaround time** | Weeks | Days |

### Quality Metrics
- **OCR Quality Score**: Average ~93% on handwritten essays
- **Field Extraction Rate**: 85-95% of fields auto-populated
- **Human Review**: Required only for edge cases (~15-20%)

### Artifacts Generated Per Submission
```
artifacts/{submission_id}/
├── original.pdf          # Source document
├── ocr.json              # Raw OCR output
├── raw_text.txt          # Extracted text
├── contact_block.txt     # Contact section
├── essay_block.txt       # Essay content
├── structured.json       # Extracted fields
├── validation.json       # Validation results
├── metadata.json         # Processing metadata
└── extraction_debug.json # Debug information
```

---

## 5. Deployment Architecture

### Production (Render)
```
┌─────────────────────────────────────────────┐
│              Render Web Service             │
│  ┌─────────────────────────────────────┐    │
│  │           Flask App                 │    │
│  │  ┌─────────────┐ ┌───────────────┐  │    │
│  │  │ Web Routes  │ │ Embedded      │  │    │
│  │  │ (Gunicorn)  │ │ Worker Thread │  │    │
│  │  └─────────────┘ └───────────────┘  │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│  Redis Cloud    │  │    Supabase     │
│  (Job Queue)    │  │  (DB + Storage) │
└─────────────────┘  └─────────────────┘
```

### Local Development (Docker)
```
┌─────────────────────────────────────────────┐
│           Docker Compose                    │
│  ┌───────────┐ ┌──────────┐ ┌───────────┐   │
│  │ Flask App │ │  Worker  │ │   Redis   │   │
│  │  :5000    │ │ (RQ)     │ │  :6379    │   │
│  └───────────┘ └──────────┘ └───────────┘   │
└─────────────────────────────────────────────┘
```

---

## 6. Key Design Decisions

### Why Google Cloud Vision over EasyOCR?
- Superior handwriting recognition
- More consistent results across varied document quality
- Better handling of cursive and mixed print/cursive

### Why Groq (Llama 3.3 70B)?
- Fast inference (sub-second responses)
- Strong context understanding for field extraction
- Cost-effective compared to OpenAI
- Effective OCR error correction

### Why Embedded Worker vs Separate Service?
- Cost savings (~$7/month)
- Simpler deployment (single service)
- Adequate for expected volume
- Uses `SimpleWorker` for thread compatibility

### Why Supabase?
- Built-in authentication (magic links)
- PostgreSQL for relational data
- Object storage for PDFs
- Row-level security for multi-tenant support

---

## 7. Lessons Learned

### Technical Challenges Solved

1. **Handwriting variability** → LLM-based extraction with fallback rules
2. **Signal handlers in threads** → Use `SimpleWorker` instead of `Worker`
3. **Session expiration** → Clear error messaging, easy re-login
4. **OCR confidence gaps** → Heuristic quality score as proxy

### Best Practices Implemented

- ✅ Human-in-the-loop for quality assurance
- ✅ Full artifact retention for auditability
- ✅ Graceful degradation (fallback extraction)
- ✅ Clear review reason codes
- ✅ Background processing for responsiveness

---

## 8. Future Enhancements

- [ ] WordPress/Ninja Forms integration (webhook trigger)
- [ ] Email notifications on processing completion
- [ ] Batch export scheduling
- [ ] Analytics dashboard
- [ ] Multi-language support (Spanish essays)
- [ ] Mobile-responsive review interface

---

## 9. Repository Structure

```
IFI Essay tool/
├── flask_app.py          # Main application
├── worker_rq.py          # Standalone worker
├── pipeline/
│   ├── ocr.py            # Google Vision integration
│   ├── extract_llm.py    # Groq LLM extraction
│   ├── extract_ifi.py    # IFI-specific extraction
│   ├── validate.py       # Validation rules
│   ├── segment.py        # Text segmentation
│   └── supabase_db.py    # Database operations
├── jobs/
│   ├── queue.py          # Queue abstraction
│   ├── redis_queue.py    # Redis implementation
│   └── process_submission.py
├── templates/            # HTML templates
├── static/               # CSS/JS assets
├── docs/                 # Documentation
└── artifacts/            # Generated artifacts (local)
```

---

## 10. Getting Started

### Local Development
```bash
cd "IFI Essay tool"
docker-compose up -d
# Access at http://localhost:5000
```

### Environment Variables
```
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_key
GOOGLE_CLOUD_VISION_CREDENTIALS_JSON={"type":"service_account",...}
GROQ_API_KEY=gsk_...
REDIS_URL=redis://...
FLASK_SECRET_KEY=your_secret
EMBEDDED_WORKER=true  # For Render deployment
```

---

*Built with ❤️ for Illinois Fatherhood Initiative*
