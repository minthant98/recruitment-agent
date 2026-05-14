# Recruitment Agent

An AI-powered recruitment screening platform built for SME businesses. Automates CV screening from receipt to HR review, with a full web UI, confidence-based job matching, and human-in-the-loop decision making.

---

## What it does

Recruitment Agent takes CVs from email or manual upload, screens them against your job descriptions using AI, and presents the results to your HR team through a clean web interface. Your team makes the final call — the AI just does the heavy lifting.

```
CV received (email or upload)
        ↓
AI matches CV to open role (confidence scoring)
        ↓
Groq screener evaluates candidate against criteria
        ↓
Judge agent critiques the screener for accuracy
        ↓
HR reviews on the web dashboard
        ↓
Shortlist / Hold / Reject
        ↓
Pipeline continues automatically
```

---

## Features

**CV Intake**
- Automatic email ingestion via Gmail API
- Manual drag-and-drop CV upload through the web UI
- PDF and Word (.docx) support

**AI Screening Pipeline**
- Confidence-based job matching — high confidence auto-assigns, medium asks for confirmation, low goes to unmatched queue
- Groq-powered CV structuring and candidate extraction
- Weighted scoring across four criteria: required skills (40%), experience (40%), preferred skills (10%), education (10%)
- Judge agent independently critiques the screener and flags conflicts

**HR Review Interface**
- Dashboard with three live queues: needs review, needs job confirmation, unmatched CVs
- Real-time notification badge — updates every 10 seconds without refreshing
- Review page with structured score bars, plain English AI narrative, and judge verdict
- Sticky decision bar with Shortlist / Hold / Reject — override reason required when HR disagrees with AI
- Activity timeline showing every pipeline step with timestamps

**Jobs Management**
- Create job roles and upload JDs via the web form — no CLI needed
- AI automatically extracts screening criteria from the uploaded JD
- Kanban board per job showing candidates by status
- Table view with sortable columns

**Audit Trail**
- Every pipeline step logged to Supabase
- Excel audit sheet generated automatically
- HR override tracking with reason capture

**Auth & Multi-tenancy**
- JWT-based authentication with secure cookie sessions
- Organisation-scoped data — each client's data is fully isolated
- Invite colleagues via email link
- Role-based access: recruiter and admin

---

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph 0.2+ with SqliteSaver checkpointing |
| LLM Screener | Groq llama-3.1-8b-instant |
| LLM Judge | Groq llama-3.3-70b-versatile |
| Database | Supabase (PostgreSQL) |
| Web UI | FastAPI + Jinja2 |
| Email | Gmail API (OAuth2) |
| CV Parsing | pdfplumber + python-docx |
| Validation | Pydantic v2 |
| Observability | LangSmith |
| Audit Export | openpyxl |

---

## Project structure

```
Recruitment Agent/
├── main.py                    # Entry point — Gmail poller + FastAPI + pipeline
├── graph.py                   # LangGraph graph definition
├── config.py                  # pydantic-settings, loads .env
├── requirements.txt
├── Dockerfile
├── render.yaml
├── state/
│   └── agent_state.py         # AgentState TypedDict
├── nodes/
│   ├── classifier.py          # CV detection + confidence-based JD matching
│   ├── ingest.py              # CV parsing + candidate extraction
│   ├── screening.py           # Groq screener agent
│   ├── judge.py               # Groq judge agent
│   ├── hitl.py                # Human-in-the-loop checkpoint
│   ├── audit.py               # Excel + Supabase audit writer
│   ├── routing.py             # Email profile to dept head
│   └── scheduling.py          # Interview invite to candidate
├── schemas/
│   ├── candidate.py
│   ├── screening.py
│   └── judge.py
├── prompts/
│   ├── screener.py
│   ├── judge.py
│   └── ingest.py
├── db/
│   ├── client.py              # Supabase client
│   ├── migrations.sql         # All 13 tables
│   └── queries.py             # Typed insert/select helpers
├── auth/
│   ├── security.py            # Password hashing + JWT
│   ├── dependencies.py        # FastAPI auth middleware
│   └── router.py              # Login, logout, invite routes
├── jd_ingestion/
│   ├── parser.py              # Word file extraction
│   ├── extractor.py           # Groq JD structurer
│   └── loader.py              # Supabase insert
├── tools/
│   ├── email.py               # Gmail sender
│   ├── gmail_poller.py        # Gmail inbox poller
│   └── excel.py               # openpyxl audit sheet
├── utils/
│   └── text.py                # Text cleaning + confidence-based JD matching
└── ui/
    ├── app.py                 # FastAPI routes
    ├── routers/
    │   ├── dashboard.py
    │   ├── jobs.py
    │   ├── queue.py
    │   └── upload.py
    └── templates/
        ├── base.html
        ├── dashboard.html
        ├── history.html
        ├── review.html
        ├── review_done.html
        ├── upload.html
        ├── auth/
        │   ├── login.html
        │   ├── accept_invite.html
        │   └── invite_invalid.html
        ├── jobs/
        │   ├── list.html
        │   ├── new.html
        │   └── detail.html
        └── queue/
            ├── confirm.html
            └── assign.html
```

---

## Setup

### Prerequisites

- Python 3.12
- A Supabase project
- A Groq API key (free tier works)
- Gmail API credentials (for email intake)

### Installation

```bash
git clone https://github.com/yourusername/recruitment-agent.git
cd recruitment-agent

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in the project root:

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key

# Groq
GROQ_API_KEY=your_groq_api_key
GROQ_SCREENER_MODEL=llama-3.1-8b-instant
GROQ_JUDGE_MODEL=llama-3.3-70b-versatile

# Auth
SECRET_KEY=your_generated_secret_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
APP_BASE_URL=http://localhost:8000

# Notifications
HR_NOTIFICATION_EMAIL=hr@yourcompany.com

# LangSmith (optional)
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_PROJECT=recruitment-agent
```

Generate a secure `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Database setup

Run the migrations in Supabase SQL Editor in order:

1. `db/migrations.sql` — creates all 13 tables
2. `db/phase1_migration.sql` — adds multi-tenancy fields

### Create your first admin user

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from auth.security import hash_password
from db.client import get_db
db = get_db()
db.table('users').insert({
    'org_id': '00000000-0000-0000-0000-000000000001',
    'email': 'your@email.com',
    'hashed_password': hash_password('yourpassword'),
    'role': 'admin'
}).execute()
print('Admin user created')
"
```

### Run

```bash
python main.py
```

The web UI will be available at `http://localhost:8000`.

For web UI only (no Gmail polling):
```bash
uvicorn ui.app:app --reload
```

---

## Scoring model

| Criterion | Weight | Description |
|---|---|---|
| Required Skills Match | 40% | Candidate must demonstrate proficiency in required technical skills |
| Experience Alignment | 40% | Years and role similarity must meet the minimum threshold |
| Preferred Skills | 10% | Additional nice-to-have skills beyond the minimum |
| Education & Domain | 10% | Education level and field of study alignment |

**Decision thresholds:**
- Score ≥ 70 → SHORTLIST
- Score 50–69 → HOLD
- Score < 50 → REJECT

---

## Confidence tiers

When a CV comes in via email, the classifier scores how well it matches each open role:

| Tier | Confidence | Action |
|---|---|---|
| HIGH | ≥ 80% | Auto-assigned → screening runs immediately |
| MEDIUM | 50–79% | Paused → recruiter confirms the job match |
| LOW | < 50% | Unmatched queue → recruiter assigns manually |

---

## Deployment

The project includes a `Dockerfile` for container-based deployment.

```bash
docker build -t recruitment-agent .
docker run -p 8000:8000 --env-file .env recruitment-agent
```

For cloud deployment, push to GitHub and connect to your hosting provider. The `render.yaml` config is included for Render.

---

## Roadmap

- Google Calendar integration for interview scheduling
- Microsoft Outlook / Graph API support
- Cloud deployment with always-on hosting
- Multi-user invite and team management
- Analytics dashboard
- ATS integration

---

## License

MIT