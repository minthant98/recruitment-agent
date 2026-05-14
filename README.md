# Recruitment Agent

An end-to-end AI-powered recruitment pipeline built for the Talent Acquisition Team. Automates the full CV screening workflow — from receiving applications via email to forwarding shortlisted candidates to department heads — with a Human-in-the-Loop review step and a full HR audit trail.

Built with LangGraph, Groq LLM, Supabase, FastAPI, and Gmail API.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Pipeline Flow](#pipeline-flow)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Gmail OAuth Setup](#gmail-oauth-setup)
- [Database Setup](#database-setup)
- [JD Ingestion](#jd-ingestion)
- [Running the Pipeline](#running-the-pipeline)
- [Web UI](#web-ui)
- [Screening Agent](#screening-agent)
- [Judge Agent](#judge-agent)
- [HITL Review](#hitl-review)
- [HR Audit Excel](#hr-audit-excel)
- [Supabase Schema](#supabase-schema)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## Overview

The Recruitment Agent automates the entry-level and mid-level recruitment pipeline. When a candidate sends their CV to the recruitment email inbox, the system:

1. Detects and downloads the CV attachment
2. Matches the application to the correct Job Description
3. Scores the candidate using an LLM screener agent
4. Runs a second LLM judge agent to critique the screener's reasoning
5. Pauses for an HR officer to review and confirm the decision via a web UI
6. Logs the full decision to an Excel audit sheet and Supabase
7. Forwards shortlisted candidates to the relevant Department Head
8. Sends an interview invitation to the candidate

The system is designed to be **explainable** — every decision includes reasoning, scores, and a full audit trail. This is critical for compliance in a banking environment.

---

## Architecture

```
Gmail Inbox
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                  LangGraph Pipeline                  │
│                                                     │
│  Classifier → Ingest → Screening → Judge → HITL    │
│      │                                    │         │
│   Discard                              Audit        │
│                                           │         │
│                              Routing → Scheduling   │
└─────────────────────────────────────────────────────┘
    │                    │                    │
    ▼                    ▼                    ▼
Supabase DB         HR Web UI          Gmail (send)
(audit trail)    (FastAPI + HTML)   (notifications,
                                   profiles, invites)
```

### Agent Design

The pipeline uses two LLM agents in sequence:

**Screener Agent** (`llama-3.1-8b-instant` via Groq)
- Fast, deterministic (temperature=0)
- Scores candidate against 4 weighted criteria
- Returns structured JSON validated by Pydantic

**Judge Agent** (`llama-3.3-70b-versatile` via Groq)
- Stronger model, slight variability (temperature=0.3)
- Critiques screener's reasoning field by field
- Sets a conflict flag if it disagrees with the screener
- Conflict is surfaced to HR as a warning in the review UI

Both agents' outputs are stored separately in Supabase and shown side by side in the HR review interface.

---

## Pipeline Flow

```
Email received
    │
    ├─ No CV attachment → Discard (log + skip)
    │
    └─ CV found
           │
           ▼
       Classifier
       - Detect CV file (PDF or DOCX)
       - Fuzzy match email to correct JD
           │
           ▼
       Ingest Node
       - Extract text from CV
       - Parse into structured CandidateData (Groq)
       - Insert candidate into Supabase
       - Create pipeline_run record
           │
           ▼
       Screening Node
       - Pull JD + criteria from Supabase
       - Build dynamic prompt
       - Score candidate (Groq, temp=0)
       - Validate with Pydantic ScreeningResult
       - Save to screening_results table
           │
           ▼
       Judge Node
       - Critique screener's 4 score components
       - Set conflict_flag if disagreement
       - Save to judge_verdicts table
           │
           ▼
       HITL (always triggered)
       - Pipeline pauses
       - Notification email sent to HR officer
       - HR reviews at http://localhost:8000/review/{run_id}
       - HR clicks Shortlist / Hold / Reject
       - Pipeline resumes
           │
           ▼
       Audit Node
       - Append row to Excel HR audit sheet
       - Update pipeline_run status to done
           │
           ├─ HOLD / REJECT → End
           │
           └─ SHORTLIST
                  │
                  ▼
              Routing Node
              - Send candidate profile + CV to dept head
                  │
                  ▼
              Scheduling Node
              - Send interview invitation to candidate
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Pipeline orchestration | LangGraph 0.2+ |
| LLM (screener) | Groq — llama-3.1-8b-instant |
| LLM (judge) | Groq — llama-3.3-70b-versatile |
| Database | Supabase (PostgreSQL) |
| CV parsing | pdfplumber, python-docx |
| Email (send/receive) | Gmail API (OAuth2) |
| Web UI | FastAPI + Jinja2 |
| Excel audit | openpyxl |
| Schema validation | Pydantic v2 |
| Config management | pydantic-settings |
| Observability | LangSmith |
| Language | Python 3.11+ |

---

## Project Structure

```
recruitment_agent/
├── main.py                    # Entry point — starts pipeline + web UI
├── graph.py                   # LangGraph graph definition
├── config.py                  # Settings via pydantic-settings
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Build config
├── CLAUDE.md                  # Agent operating standard
├── .env                       # Environment variables (never commit)
├── .env.example               # Template for .env
├── .gitignore
│
├── state/
│   └── agent_state.py         # AgentState TypedDict (shared pipeline state)
│
├── nodes/                     # One file per LangGraph node
│   ├── classifier.py          # CV detection + JD matching
│   ├── ingest.py              # CV parsing + candidate creation
│   ├── screening.py           # Groq screener agent
│   ├── judge.py               # Groq judge agent
│   ├── hitl.py                # Human-in-the-loop checkpoint
│   ├── audit.py               # Excel + Supabase audit writer
│   ├── routing.py             # Forward profile to dept head
│   └── scheduling.py          # Send interview invite
│
├── schemas/                   # Pydantic models
│   ├── candidate.py           # CandidateData
│   ├── screening.py           # ScreeningResult, SkillsAnalysis, ExperienceAnalysis
│   └── judge.py               # JudgeVerdict, CriterionVerdict
│
├── prompts/                   # LLM prompt strings
│   ├── screener.py            # Screener system prompt + user prompt builder
│   ├── judge.py               # Judge system prompt + user prompt builder
│   └── ingest.py              # CV extraction prompt
│
├── db/
│   ├── client.py              # Supabase client singleton
│   ├── migrations.sql         # All 9 table CREATE statements
│   └── queries.py             # Typed insert/select helpers
│
├── jd_ingestion/              # One-time JD loading script
│   ├── parser.py              # Extract text from Word JD files
│   ├── extractor.py           # Groq structures raw JD text
│   ├── loader.py              # Insert into Supabase
│   └── run.py                 # CLI entry point
│
├── tools/
│   ├── email.py               # Gmail sender (notifications, profiles, invites)
│   ├── gmail_poller.py        # Gmail inbox poller
│   └── excel.py               # openpyxl audit sheet writer
│
├── ui/
│   ├── app.py                 # FastAPI app
│   └── templates/
│       ├── review.html        # HR candidate review page
│       └── history.html       # All past candidates + history
│
├── utils/
│   ├── text.py                # Text cleaning + JD fuzzy matching
│   └── logger.py              # Structured logging
│
├── tasks/
│   ├── todo.md                # Step-by-step task tracker
│   └── lessons.md             # Mistakes and prevention rules
│
├── jds/                       # Your JD Word files (gitignored)
├── attachments/               # Downloaded CV files (gitignored)
├── outputs/                   # Generated Excel files (gitignored)
└── credentials/               # Gmail OAuth credentials (gitignored)
    ├── gmail_credentials.json
    └── gmail_token.json
```

---

## Prerequisites

- Python 3.11+
- A Gmail account dedicated to recruitment (e.g. `recruitment@yourcompany.com`)
- A Groq API account (free tier) — [console.groq.com](https://console.groq.com)
- A Supabase project (free tier) — [supabase.com](https://supabase.com)
- A LangSmith account (free tier) — [smith.langchain.com](https://smith.langchain.com)
- A Google Cloud project with Gmail API enabled

---

## Installation

```bash
# Clone the repository
git clone https://github.com/yourorg/recruitment-agent.git
cd recruitment-agent

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Configuration

Copy `.env.example` to `.env` and fill in all values:

```bash
cp .env.example .env
```

```dotenv
# ── LLM ──────────────────────────────────────────────
GROQ_API_KEY=your_groq_api_key
GROQ_SCREENER_MODEL=llama-3.1-8b-instant
GROQ_JUDGE_MODEL=llama-3.3-70b-versatile
GROQ_SCREENER_TEMPERATURE=0.0
GROQ_JUDGE_TEMPERATURE=0.3

# ── Supabase ──────────────────────────────────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key

# ── Gmail ─────────────────────────────────────────────
GMAIL_CREDENTIALS_PATH=credentials/gmail_credentials.json
GMAIL_TOKEN_PATH=credentials/gmail_token.json
RECRUITMENT_EMAIL_LABEL=recruitment

# ── HR Notification ───────────────────────────────────
HR_NOTIFICATION_EMAIL=hr@yourcompany.com

# ── Pipeline Thresholds ───────────────────────────────
AUTO_PASS_THRESHOLD=70.0
AUTO_REJECT_THRESHOLD=40.0

# ── Audit ─────────────────────────────────────────────
AUDIT_EXCEL_PATH=outputs/hr_audit.xlsx

# ── LangSmith Tracing ─────────────────────────────────
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=Recruitment Agent

# ── Logging ───────────────────────────────────────────
LOG_LEVEL=INFO
```

---

## Gmail OAuth Setup

The pipeline uses Gmail API to poll the inbox and send emails. You need to set up OAuth2 credentials once.

### Step 1 — Create Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project — name it `Recruitment Agent`
3. Go to **APIs & Services** → **Enable APIs**
4. Search for and enable **Gmail API**

### Step 2 — OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External**
3. Fill in app name: `Recruitment Agent`
4. Add your Gmail address as a test user
5. Save

### Step 3 — Create Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Download the JSON file
5. Rename it to `gmail_credentials.json`
6. Place it in the `credentials/` folder

### Step 4 — Authorise

Run this once to generate the token:

```bash
python -c "from tools.email import get_gmail_service; get_gmail_service()"
```

A browser window opens. Sign in with the recruitment Gmail account and click Allow. A `gmail_token.json` is saved to `credentials/`. All future runs are silent.

> **Note:** The token expires every 7 days in Testing mode. Re-run the command above to refresh it.

---

## Database Setup

### Step 1 — Create Supabase Project

1. Go to [supabase.com](https://supabase.com) → New Project
2. Copy the **Project URL** and **service_role** key from Settings → API
3. Paste into your `.env`

### Step 2 — Run Migrations

1. Open Supabase Dashboard → SQL Editor
2. Paste the full contents of `db/migrations.sql`
3. Click **Run**

This creates all 9 tables:

| Table | Purpose |
|-------|---------|
| `departments` | Department names and head contacts |
| `job_descriptions` | One row per JD file |
| `screening_criteria` | 4 weighted criteria per JD |
| `candidates` | One row per applicant |
| `pipeline_runs` | One row per candidate-JD evaluation |
| `screening_results` | Screener agent output |
| `judge_verdicts` | Judge agent output |
| `hitl_reviews` | HR officer decisions |
| `audit_log` | Full node-by-node audit trail |

---

## JD Ingestion

Before running the pipeline you must load your Job Descriptions into Supabase. This is a one-time setup step per JD.

### Step 1 — Place JD files

Put your Word `.docx` JD files in the `jds/` folder:

```
jds/
├── Senior Data Analyst (JD).docx
├── Network Engineer (Supervisor).docx
└── Junior Network Engineer.docx
```

### Step 2 — Configure departments

Open `jd_ingestion/run.py` and fill in department head details:

```python
JDS = [
    {
        "file": "jds/Senior Data Analyst (JD).docx",
        "dept_name": "Finance",
        "dept_head_name": "U Kyaw Zin",
        "dept_head_email": "kyawzin@gmail.com",
    },
    {
        "file": "jds/Network Engineer (Supervisor).docx",
        "dept_name": "TODC",
        "dept_head_name": "Daw Aye Aye",
        "dept_head_email": "ayeaye@gmail.com",
    },
    ...
]
```

### Step 3 — Run ingestion

```bash
python -m jd_ingestion.run
```

Expected output:
```
Processing: jds/Senior Data Analyst (JD).docx
  Extracted 2341 characters from Word file
  Groq extracted: Senior Data Analyst
  Created department: Finance
  Inserted JD: Senior Data Analyst (id: abc-123...)
  Inserted 4 screening criteria
  ✅ Done
```

### Updating department heads

You can update head name/email anytime via Supabase SQL:

```sql
UPDATE departments
SET head_name = 'New Name', head_email = 'new@gmail.com'
WHERE name = 'Finance';
```

---

## Running the Pipeline

### Create output folder

```bash
mkdir -p outputs attachments
```

### Start the agent

```bash
python main.py
```

This starts two things simultaneously:
- **Gmail poller** — checks inbox every 60 seconds for new CV emails
- **Web UI** — FastAPI server at `http://localhost:8000`

```
========================================================
  Recruitment Agent — Started
  Web UI running at: http://localhost:8000
  History:           http://localhost:8000/history
  Poll interval: 60s
========================================================
[22:30:00] Polling Gmail...
  No new CV emails
```

### Sending a test application

Send an email to the recruitment Gmail account with:
- Subject containing: `cv`, `resume`, `application`, or `apply`
- A CV attached as `.pdf` or `.docx`

Within 60 seconds the pipeline triggers automatically.

### One-shot mode (for testing)

Process one batch and exit without looping:

```bash
python main.py --once
```

### Resetting for a clean test

Clear Supabase data (keep JDs):

```sql
DELETE FROM audit_log;
DELETE FROM hitl_reviews;
DELETE FROM judge_verdicts;
DELETE FROM screening_results;
DELETE FROM pipeline_runs;
DELETE FROM candidates;
```

Reset Excel:

```bash
rm -f outputs/hr_audit.xlsx
```

---

## Web UI

The web UI runs automatically alongside the pipeline at `http://localhost:8000`.

### Review Page — `/review/{run_id}`

Opened via the link in the HR notification email. Shows:

- Candidate summary (name, experience, education, previous roles)
- Composite score with visual breakdown (4 score bars)
- Screener recommendation vs Judge recommendation side by side
- Conflict banner if agents disagree
- Judge's criterion-by-criterion critique
- Strengths and weaknesses
- Three decision buttons: **Shortlist** (green) · **Hold** (amber) · **Reject** (red)
- Override reason field (required if HR overrides both agents)
- Confirm button — resumes the pipeline

### History Page — `/history`

Always accessible at `http://localhost:8000/history`. Shows:

- Summary stats: Total reviewed, Shortlisted, Hold, Rejected, Overrides
- Sortable table of all reviewed candidates
- Filters by name, decision, role, and conflict flag
- Click any row to open that candidate's full review
- Auto-refreshes every 30 seconds

---

## Screening Agent

The screener evaluates candidates against 4 weighted criteria pulled from Supabase at runtime:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Required Skills Match | 40% | Core technical and domain skills |
| Experience Alignment | 40% | Years, role similarity, scope |
| Preferred Skills | 10% | Nice-to-have skills |
| Education & Domain Fit | 10% | Degree level and field relevance |

**Composite Score** = (required_skills × 0.4) + (experience × 0.4) + (preferred × 0.1) + (education × 0.1)

**Recommendation thresholds:**

| Score | Recommendation |
|-------|---------------|
| ≥ 70 | SHORTLIST_INTERVIEW |
| 50–69 | HOLD |
| < 50 | REJECT |

The screener runs at temperature=0 for deterministic, reproducible scoring.

---

## Judge Agent

The judge receives the screener's full output and critiques it independently:

- Reviews each of the 4 scoring components
- Checks if scores are justified by the CV evidence
- Flags inflation or deflation of any score > 15 points
- Sets `conflict_flag = True` if its recommendation differs from the screener

The judge uses a stronger model (`llama-3.3-70b-versatile`) at temperature=0.3 to ensure it genuinely challenges the screener rather than agreeing automatically.

**Conflict conditions (any one triggers HITL warning):**
- Recommended decision differs from screener
- Any individual score differs by more than 15 points
- Critical missing skill was ignored by screener
- Composite score doesn't match weighted calculation

---

## HITL Review

Every candidate goes through HR review — not just conflicts. The HITL node always triggers, giving HR full control over every hiring decision.

**What HR sees:**
- Full candidate summary
- Screener score + Judge opinion side by side
- Red conflict banner if agents disagree
- Criterion-by-criterion judge verdicts
- Strengths and weaknesses
- Decision buttons with confirmation

**Override logic:**
- If HR selects a decision that differs from both agents, an override reason field appears and is required
- Override reason is stored in `hitl_reviews.override_reason`
- `was_overridden` flag is set for audit and analytics

**Resume flow:**
1. Pipeline pauses before HITL node
2. Notification email sent to `HR_NOTIFICATION_EMAIL`
3. HR clicks "Review Now" link in email
4. HR reviews the candidate card in the web UI
5. HR clicks a decision and confirms
6. Pipeline resumes from the HITL checkpoint
7. Remaining nodes (audit, routing, scheduling) execute

---

## HR Audit Excel

Every reviewed candidate is appended as a row to `outputs/hr_audit.xlsx`. The file is created automatically on first run.

**Column groups:**

| Group | Columns |
|-------|---------|
| Pipeline metadata | run_id, reviewed_at |
| Candidate info | name, email, experience, roles, education |
| JD info | role title, department |
| Screening scores | 4 component scores, composite, experience rating |
| Screener output | matched/missing skills, strengths, weaknesses, recommendation, justification |
| Judge output | overall agrees, suggested recommendation, conflict flag, reason, confidence |
| HR decision | final decision, reviewed by, override reason, was overridden |
| Pipeline path | hitl reviewed, pipeline status |

**Colour coding:**
- 🟢 Green rows — SHORTLIST_INTERVIEW
- 🟡 Amber rows — HOLD
- 🔴 Red rows — REJECT

---

## Supabase Schema

### Entity Relationships

```
departments
    └── job_descriptions
            └── screening_criteria
            └── pipeline_runs
                    └── candidates
                    └── screening_results
                    └── judge_verdicts
                    └── hitl_reviews
                    └── audit_log
```

### Key design decisions

**JSONB columns** (`skills_analysis`, `experience_analysis`, `criterion_verdicts`) store nested LLM output that varies per role. They're queryable in Postgres but flexible enough to evolve as prompts change.

**Flat score columns** (`required_skills_score`, `experience_score` etc.) are stored as individual `FLOAT` columns in `screening_results` for direct Excel mapping and SQL aggregation without JSON parsing.

**`pipeline_runs.status`** tracks pipeline state:
- `in_progress` — actively processing
- `pending_review` — paused at HITL
- `done` — fully complete

**`audit_log`** captures every node transition with its payload — not just the final decision. This gives a complete timeline of what happened, when, and what each node produced.

---

## Known Limitations

| Limitation | Notes |
|------------|-------|
| No authentication on web UI | Add token-based auth before production |
| MemorySaver is in-memory | Restarts lose pending HITL state — use SqliteSaver or PostgresSaver for production |
| Gmail polling every 60s | Not real-time — consider Gmail Push Notifications (Pub/Sub) for production |
| No Google Calendar integration | Scheduling node sends email only — calendar booking is a future enhancement |
| Single CV per email | Only first CV attachment is processed if multiple are attached |
| English/Burmese only | Screener prompt supports both languages but pipeline metadata is English only |

---

## Roadmap

### Near term
- [ ] Web UI authentication (token-based)
- [ ] Persistent checkpointing (PostgresSaver) — survive restarts
- [ ] Gmail Push Notifications — real-time instead of polling
- [ ] Google Calendar integration for scheduling node
- [ ] Unit tests for each node

### Medium term
- [ ] Multi-CV batch processing (one email, multiple CVs)
- [ ] Candidate comparison mode (rank multiple applicants for one JD)
- [ ] Department head portal — view assigned candidates
- [ ] Analytics dashboard — screening trends, override rates, time-to-shortlist

### Production readiness
- [ ] Docker deployment
- [ ] Environment-specific configs (dev / staging / prod)
- [ ] Rate limiting on web UI endpoints
- [ ] Supabase Row Level Security (RLS)
- [ ] HTTPS with SSL certificate
- [ ] Monitoring and alerting

---

## Built With

This project was built as an internal AI portfolio project for Talent Acquisition team, demonstrating production-grade agentic AI system design using modern Python tooling.

**Core design principles:**
- Every LLM decision is explainable and logged
- Human always has final authority (HITL)
- Schema-first development (Pydantic validates every LLM output)
- Separation of concerns (one file per node, one file per concern)
- Fail loudly (validation errors surface immediately, never silently pass bad data downstream)