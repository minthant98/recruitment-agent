"""
ui/routers/jobs.py
──────────────────
Jobs page routes — list all jobs, create a new job, view job detail.

Mount in ui/app.py:
    from ui.routers.jobs import router as jobs_router
    app.include_router(jobs_router)
"""

import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth.dependencies import CurrentUser, require_user
from db.client import get_db
from jd_ingestion.extractor import extract_jd_structure
from jd_ingestion.parser import extract_text_from_docx

router = APIRouter()
templates = Jinja2Templates(directory="ui/templates")


# ── Helpers ──────────────────────────────────────────────────────

def _get_jobs(org_id: str) -> list[dict]:
    """Fetch all open jobs for this org with CV counts."""
    db = get_db()

    jobs = db.table("job_descriptions").select(
        "id, role_title, status, employment_type, created_at, dept_id"
    ).eq("org_id", org_id).order("created_at", desc=True).execute().data

    # Fetch department names
    dept_ids = list({j["dept_id"] for j in jobs if j.get("dept_id")})
    dept_map = {}
    if dept_ids:
        depts = db.table("departments").select("id, name").in_("id", dept_ids).execute().data
        dept_map = {d["id"]: d["name"] for d in depts}

    # Fetch CV counts per job
    runs = db.table("pipeline_runs").select(
        "jd_id, status"
    ).eq("org_id", org_id).execute().data

    # Count by jd_id and status
    counts: dict[str, dict] = {}
    for r in runs:
        jid = r["jd_id"]
        if jid not in counts:
            counts[jid] = {"total": 0, "pending": 0}
        counts[jid]["total"] += 1
        if r["status"] in ("pending_review", "in_progress"):
            counts[jid]["pending"] += 1

    # Enrich jobs
    for j in jobs:
        j["dept_name"] = dept_map.get(j["dept_id"], "—")
        j["total_cvs"] = counts.get(j["id"], {}).get("total", 0)
        j["pending_cvs"] = counts.get(j["id"], {}).get("pending", 0)

    return jobs


def _get_departments(org_id: str) -> list[dict]:
    """Fetch all departments for this org."""
    db = get_db()
    return db.table("departments").select(
        "id, name"
    ).eq("org_id", org_id).order("name").execute().data


def _get_kanban_data(job_id: str, org_id: str) -> dict:
    """
    Fetch all pipeline runs for a job, grouped by status for kanban.
    Returns dict with keys: pending, shortlisted, on_hold, rejected, job
    """
    db = get_db()

    # Fetch job details
    job = db.table("job_descriptions").select(
        "id, role_title, status, dept_id"
    ).eq("id", job_id).eq("org_id", org_id).execute().data
    if not job:
        return {}
    job = job[0]

    if job.get("dept_id"):
        dept = db.table("departments").select("name").eq("id", job["dept_id"]).execute().data
        job["dept_name"] = dept[0]["name"] if dept else "—"
    else:
        job["dept_name"] = "—"

    # Fetch all runs for this job with candidate info and scores
    runs = db.table("pipeline_runs").select(
        "id, status, match_status, source, confidence_score, created_at, candidate_id"
    ).eq("jd_id", job_id).eq("org_id", org_id).order("created_at", desc=True).execute().data

    if not runs:
        return {
            "job": job,
            "pending": [], "shortlisted": [], "on_hold": [], "rejected": [],
            "awaiting_confirmation": [], "unmatched": [],
        }

    # Fetch candidate names
    candidate_ids = [r["candidate_id"] for r in runs]
    candidates = db.table("candidates").select(
        "id, name, email"
    ).in_("id", candidate_ids).execute().data
    candidate_map = {c["id"]: c for c in candidates}

    # Fetch composite scores from screening_results
    run_ids = [r["id"] for r in runs]
    scores = db.table("screening_results").select(
        "run_id, composite_score"
    ).in_("run_id", run_ids).execute().data
    score_map = {s["run_id"]: s["composite_score"] for s in scores}

    # Enrich runs
    # Enrich runs
    for r in runs:
        cand = candidate_map.get(r["candidate_id"], {})
        r["candidate_name"] = cand.get("name", "Unknown")
        r["candidate_email"] = cand.get("email", "")
        r["score"] = score_map.get(r["id"])
        r["source_label"] = "Email" if r.get("source") == "EMAIL" else "Upload"
        r["confidence_pct"] = (
            f'{int(r["confidence_score"] * 100)}%'
            if r.get("confidence_score") else "—"
        )

    # Map "done" runs to correct kanban column using HITL decision
    hitl_results = db.table("hitl_reviews").select(
        "run_id, final_decision"
    ).in_("run_id", run_ids).execute().data
    hitl_map = {h["run_id"]: h["final_decision"] for h in hitl_results}

    for r in runs:
        if r["status"] == "done" and r["id"] in hitl_map:
            decision = hitl_map[r["id"]]
            if decision == "SHORTLIST_INTERVIEW":
                r["status"] = "shortlisted"
            elif decision == "HOLD":
                r["status"] = "hold"
            elif decision == "REJECT":
                r["status"] = "rejected"

    # Group by status
    def _filter(status_vals):
        return [r for r in runs if r["status"] in status_vals]

    return {
        "job": job,
        "pending":                _filter(["pending_review", "in_progress"]),
        "shortlisted":            _filter(["shortlisted"]),
        "on_hold":                _filter(["hold"]),
        "rejected":               _filter(["rejected"]),
        "awaiting_confirmation":  _filter(["awaiting_confirmation"]),
        "unmatched":              _filter(["unmatched"]),
    }


# ── Routes ───────────────────────────────────────────────────────

@router.get("/jobs", response_class=HTMLResponse)
async def jobs_list(
    request: Request,
    user: CurrentUser = Depends(require_user),
):
    """Jobs list page — all open roles for this org."""
    jobs = _get_jobs(user.org_id)
    return templates.TemplateResponse(request, "jobs/list.html", {
        "jobs": jobs,
        "user": user,
    })


@router.get("/jobs/new", response_class=HTMLResponse)
async def new_job_page(
    request: Request,
    user: CurrentUser = Depends(require_user),
):
    """Show the create job form."""
    departments = _get_departments(user.org_id)
    return templates.TemplateResponse(request, "jobs/new.html", {
        "departments": departments,
        "user": user,
    })


@router.post("/jobs/new")
async def create_job(
    request: Request,
    role_title: str = Form(...),
    dept_id: str = Form(default=""),
    employment_type: str = Form(default="Full-time"),
    jd_file: UploadFile = File(...),
    user: CurrentUser = Depends(require_user),
):
    """
    Create a new job from the web form.
    Replaces the CLI jd_ingestion/run.py flow entirely.

    Steps:
    1. Save uploaded file to temp location
    2. Extract raw text (reuses jd_ingestion/parser.py)
    3. Call Groq to structure the JD (reuses jd_ingestion/extractor.py)
    4. Insert job_description + screening_criteria into Supabase
    5. Redirect to the new job's kanban page
    """
    db = get_db()

    # Save upload to temp file
    suffix = ".docx" if "docx" in jd_file.content_type or jd_file.filename.endswith(".docx") else ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await jd_file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Extract raw text
        raw_text = extract_text_from_docx(tmp_path)

        # Groq extraction — reuses existing extractor
        structured = extract_jd_structure(raw_text)

        # Insert job_description
        jd_result = db.table("job_descriptions").insert({
            "org_id":           user.org_id,
            "dept_id":          dept_id if dept_id else None,
            "role_title":       structured.get("role_title", role_title),
            "seniority_level":  structured.get("seniority_level"),
            "required_years":   structured.get("required_years"),
            "raw_text":         raw_text,
            "source_file":      jd_file.filename,
            "employment_type":  employment_type,
            "status":           "OPEN",
            "created_by":       user.user_id,
        }).execute()

        jd_id = jd_result.data[0]["id"]

        # Insert screening criteria (always 4)
        criteria = structured.get("screening_criteria", [])
        for c in criteria:
            db.table("screening_criteria").insert({
                "org_id":         user.org_id,
                "jd_id":          jd_id,
                "criterion_name": c["criterion_name"],
                "weight":         c["weight"],
                "description":    c["description"],
            }).execute()

    finally:
        os.unlink(tmp_path)

    return RedirectResponse(url=f"/jobs/{jd_id}", status_code=302)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(
    request: Request,
    job_id: str,
    view: str = "kanban",
    user: CurrentUser = Depends(require_user),
):
    """
    Job detail page — kanban (default) or table view.
    ?view=kanban or ?view=table
    """
    data = _get_kanban_data(job_id, user.org_id)
    if not data:
        return HTMLResponse("Job not found", status_code=404)

    # For table view — flatten and sort by score
    all_runs = (
        data["pending"] + data["shortlisted"] +
        data["on_hold"] + data["rejected"] +
        data["awaiting_confirmation"] + data["unmatched"]
    )
    table_rows = sorted(
        [r for r in all_runs if r.get("score") is not None],
        key=lambda r: r["score"],
        reverse=True,
    )

    return templates.TemplateResponse(request, "jobs/detail.html", {
        **data,
        "table_rows": table_rows,
        "view": view,
        "user": user,
    })