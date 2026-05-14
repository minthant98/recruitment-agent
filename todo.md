# Recruitment Agent — Task Tracker

## Step 1: Project Scaffold
| id  | description              | status |
|-----|--------------------------|--------|
| 1.1 | Folder structure         | DONE   |
| 1.2 | pyproject.toml           | DONE   |
| 1.3 | .env.example             | DONE   |
| 1.4 | CLAUDE.md in project     | DONE   |
| 1.5 | config.py                | DONE   |
| 1.6 | tasks/todo.md            | DONE   |

---

## Step 2: Supabase Migrations
| id  | description                        | status |
|-----|------------------------------------|--------|
| 2.1 | departments table                  | TODO   |
| 2.2 | job_descriptions table             | TODO   |
| 2.3 | screening_criteria table           | TODO   |
| 2.4 | candidates table                   | TODO   |
| 2.5 | pipeline_runs table                | TODO   |
| 2.6 | screening_results table            | TODO   |
| 2.7 | judge_verdicts table               | TODO   |
| 2.8 | hitl_reviews table                 | TODO   |
| 2.9 | audit_log table                    | TODO   |
| 2.10| db client + helper                 | TODO   |

---

## Step 3: JD Ingestion Script
| id  | description                        | status |
|-----|------------------------------------|--------|
| 3.1 | PDF/Word parser                    | TODO   |
| 3.2 | Groq JD structured extractor       | TODO   |
| 3.3 | Supabase insert                    | TODO   |
| 3.4 | CLI runner                         | TODO   |

---

## Step 4: LangGraph State + Graph Skeleton
| id  | description                        | status |
|-----|------------------------------------|--------|
| 4.1 | AgentState TypedDict               | TODO   |
| 4.2 | Graph definition + node stubs      | TODO   |
| 4.3 | Conditional edge logic             | TODO   |
| 4.4 | Graph compilation + entry point    | TODO   |

---

## Step 5: Classifier Node
| id  | description                        | status |
|-----|------------------------------------|--------|
| 5.1 | MIME type + attachment detection   | TODO   |
| 5.2 | CV file extractor                  | TODO   |
| 5.3 | JD fuzzy matcher                   | TODO   |
| 5.4 | Discard path                       | TODO   |

---

## Step 6: Ingest Node
| id  | description                        | status |
|-----|------------------------------------|--------|
| 6.1 | PDF/Word CV parser                 | TODO   |
| 6.2 | Groq structured CV extractor       | TODO   |
| 6.3 | Supabase candidate insert          | TODO   |

---

## Step 7: Screening Node
| id  | description                        | status |
|-----|------------------------------------|--------|
| 7.1 | ScreeningResult Pydantic schema    | TODO   |
| 7.2 | Screener prompt (system mode)      | TODO   |
| 7.3 | Groq call + structured output      | TODO   |
| 7.4 | Supabase screening_results insert  | TODO   |

---

## Step 8: Judge Node
| id  | description                        | status |
|-----|------------------------------------|--------|
| 8.1 | JudgeVerdict Pydantic schema       | TODO   |
| 8.2 | Judge prompt                       | TODO   |
| 8.3 | Groq call + conflict flag          | TODO   |
| 8.4 | Supabase judge_verdicts insert     | TODO   |

---

## Step 9: HITL Checkpoint
| id  | description                        | status |
|-----|------------------------------------|--------|
| 9.1 | LangGraph interrupt implementation | TODO   |
| 9.2 | CLI review interface               | TODO   |
| 9.3 | Resume + hitl_reviews insert       | TODO   |

---

## Step 10: Audit Node
| id  | description                        | status |
|-----|------------------------------------|--------|
| 10.1| Excel column mapping from schema   | TODO   |
| 10.2| openpyxl row append logic          | TODO   |
| 10.3| Auto-pass + HITL path handling     | TODO   |

---

## Step 11: Routing + Scheduling Nodes
| id  | description                        | status |
|-----|------------------------------------|--------|
| 11.1| Dept head lookup from Supabase     | TODO   |
| 11.2| Profile forwarding email           | TODO   |
| 11.3| Calendar API integration           | TODO   |

---

## Lessons Learned
_Updated after each bug fix or correction._


---

## UI/UX Requirements (Build After Core Nodes)

### Notification Email (HTML)
- Candidate name, role, composite score
- Screener recommendation + judge opinion
- Conflict badge if agents disagree
- One "Review Now" button linking to web UI review page

### Web UI — View 1: Active Review
- Triggered by notification email link (unique URL per candidate)
- Left side: candidate summary (experience, skills, education)
- Right side: screener scores with visual bar per component + judge verdict
- Conflict banner at top if agents disagree
- Strengths and weaknesses section
- Three decision buttons: Shortlist (green) · Hold (amber) · Reject (red)
- Override reason text box — appears when HR picks different decision than agents
- Confirm button — submits decision and resumes pipeline
- After submit: success screen

### Web UI — View 2: History
- Always accessible at /history
- Table of all reviewed candidates
- Columns: name, role, date, composite score, screener rec, judge rec, HR final decision, overridden
- Sortable and filterable by role / decision / date
- Click a row to expand full candidate screening detail

### Tech Stack
- FastAPI backend
- Single HTML file per view (no frontend framework)
- Supabase as data source (reads from screening_results, judge_verdicts, hitl_reviews)
- Unique review URL per candidate: /review/{run_id}
- History at: /history

### Known Gaps (Fix Before Production)
- [ ] Authentication — add simple password or token-based auth
- [ ] Rate limiting on decision submission endpoint
- [ ] HTTPS / secure deployment

### Folder Structure
- ui/app.py          — FastAPI app
- ui/templates/review.html   — active review page
- ui/templates/history.html  — history page
- ui/__init__.py