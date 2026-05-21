"""
ui/routers/queue.py
────────────────────
Routes for the confirmation queue and unmatched queue.

Confirmation queue: recruiter sees top JD matches and picks one.
Unmatched queue:    recruiter manually assigns a job.

Both resume the LangGraph pipeline after the recruiter acts.

Mount in ui/app.py:
    from ui.routers.queue import router as queue_router
    app.include_router(queue_router)
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from auth.dependencies import CurrentUser, require_user
from db.client import get_db
from db.queries import update_pipeline_run, log_audit

router = APIRouter()
templates = Jinja2Templates(directory="ui/templates")

# Resume callback — injected by main.py (same pattern as HITL)
_resume_callback = None

def set_queue_resume_callback(fn):
    global _resume_callback
    _resume_callback = fn


# ── Confirmation queue ────────────────────────────────────────────

@router.get("/confirm/{run_id}", response_class=HTMLResponse)
async def confirm_page(
    request: Request,
    run_id: str,
    user: CurrentUser = Depends(require_user),
):
    """
    Show the recruiter the top JD matches for a MEDIUM confidence CV.
    They pick one and click Confirm — pipeline resumes at ingest.
    """
    db = get_db()

    # Fetch pipeline run
    run = db.table("pipeline_runs").select("*").eq(
        "id", run_id
    ).eq("org_id", user.org_id).execute().data
    if not run:
        return HTMLResponse("Not found", status_code=404)
    run = run[0]

    # Fetch candidate name
    candidate = db.table("candidates").select("name, email").eq(
        "id", run["candidate_id"]
    ).execute().data
    candidate = candidate[0] if candidate else {}

    # Fetch all open jobs for this org (for the dropdown)
    jobs = db.table("job_descriptions").select(
        "id, role_title"
    ).eq("org_id", user.org_id).eq("status", "OPEN").execute().data

    return templates.TemplateResponse(request, "queue/confirm.html", {
        "run": run,
        "candidate": candidate,
        "jobs": jobs,
        "user": user,
    })


@router.post("/confirm/{run_id}")
async def confirm_job(
    run_id: str,
    job_id: str = Form(...),
    user: CurrentUser = Depends(require_user),
):
    """
    Recruiter confirmed the job match. Update state and resume pipeline.
    """
    db = get_db()

    # Fetch job title for state update
    job = db.table("job_descriptions").select(
        "role_title"
    ).eq("id", job_id).execute().data
    job_title = job[0]["role_title"] if job else "Unknown"

    # Update pipeline run
    update_pipeline_run(
        run_id=run_id,
        current_node="confirmation_pause",
        status="in_progress",
    )
    db.table("pipeline_runs").update({
        "jd_id":        job_id,
        "match_status": "MANUALLY_ASSIGNED",
    }).eq("id", run_id).execute()

    log_audit(
        run_id=run_id,
        node_name="confirmation_pause",
        action="confirmed",
        payload={
            "confirmed_jd_id":    job_id,
            "confirmed_jd_title": job_title,
            "confirmed_by":       user.email,
        },
    )

    # Resume pipeline — inject confirmed jd into state
    if _resume_callback:
        _resume_callback(run_id, {
            "matched_jd_id":    job_id,
            "matched_jd_title": job_title,
            "match_status":     "MANUALLY_ASSIGNED",
        })

    return RedirectResponse(url="/dashboard", status_code=302)


# ── Unmatched queue ───────────────────────────────────────────────

@router.get("/assign/{run_id}", response_class=HTMLResponse)
async def assign_page(
    request: Request,
    run_id: str,
    user: CurrentUser = Depends(require_user),
):
    """
    Show the recruiter an unmatched CV so they can assign it to a job manually.
    """
    db = get_db()

    run = db.table("pipeline_runs").select("*").eq(
        "id", run_id
    ).eq("org_id", user.org_id).execute().data
    if not run:
        return HTMLResponse("Not found", status_code=404)
    run = run[0]

    candidate = db.table("candidates").select("name, email").eq(
        "id", run["candidate_id"]
    ).execute().data
    candidate = candidate[0] if candidate else {}

    jobs = db.table("job_descriptions").select(
        "id, role_title"
    ).eq("org_id", user.org_id).eq("status", "OPEN").execute().data

    return templates.TemplateResponse(request, "queue/assign.html", {
        "run": run,
        "candidate": candidate,
        "jobs": jobs,
        "user": user,
    })


@router.post("/assign/{run_id}")
async def assign_job(
    run_id: str,
    job_id: str = Form(...),
    user: CurrentUser = Depends(require_user),
):
    """
    Recruiter manually assigned a job. Update state and resume pipeline.
    """
    db = get_db()

    job = db.table("job_descriptions").select(
        "role_title"
    ).eq("id", job_id).execute().data
    job_title = job[0]["role_title"] if job else "Unknown"

    update_pipeline_run(
        run_id=run_id,
        current_node="unmatched_queue",
        status="in_progress",
    )
    db.table("pipeline_runs").update({
        "jd_id":        job_id,
        "match_status": "MANUALLY_ASSIGNED",
    }).eq("id", run_id).execute()

    log_audit(
        run_id=run_id,
        node_name="unmatched_queue",
        action="manually_assigned",
        payload={
            "assigned_jd_id":    job_id,
            "assigned_jd_title": job_title,
            "assigned_by":       user.email,
        },
    )

    if _resume_callback:
        _resume_callback(run_id, {
            "matched_jd_id":    job_id,
            "matched_jd_title": job_title,
            "match_status":     "MANUALLY_ASSIGNED",
        })

    return RedirectResponse(url="/dashboard", status_code=302)


# ── Interview launch ──────────────────────────────────────────────

@router.post("/launch-interview/{run_id}")
async def launch_interview(
    run_id: str,
    user: CurrentUser = Depends(require_user),
):
    """
    HR launches an AI interview for a shortlisted candidate.
    Called from the HITL review screen after a candidate is shortlisted.
    Calls the Interview Agent API, then redirects HR to the dashboard.
    """
    import os
    from tools.interview_client import launch_interview as _launch, get_hr_dashboard_url

    db = get_db()

    # ── Load pipeline run ─────────────────────────────────────────
    run_rows = db.table("pipeline_runs") \
        .select("*") \
        .eq("id", run_id) \
        .eq("org_id", user.org_id) \
        .execute().data

    if not run_rows:
        return JSONResponse({"error": "Pipeline run not found."}, status_code=404)
    run = run_rows[0]

    # ── Load candidate ────────────────────────────────────────────
    cand_rows = db.table("candidates") \
        .select("id, name, email, raw_cv_text") \
        .eq("id", run["candidate_id"]) \
        .execute().data

    if not cand_rows:
        return JSONResponse({"error": "Candidate not found."}, status_code=404)
    candidate = cand_rows[0]

    # ── Load job description ──────────────────────────────────────
    job_rows = db.table("job_descriptions") \
        .select("id, role_title, raw_text") \
        .eq("id", run["jd_id"]) \
        .execute().data

    if not job_rows:
        return JSONResponse({"error": "Job not found."}, status_code=404)
    job = job_rows[0]

    # ── Load screening gaps from screening_results ────────────────
    screening_rows = db.table("screening_results") \
        .select("weaknesses") \
        .eq("run_id", run_id) \
        .execute().data

    screening_gaps = []
    if screening_rows and screening_rows[0].get("weaknesses"):
        raw_weaknesses = screening_rows[0]["weaknesses"]
        # weaknesses is stored as JSONB list of strings or dicts
        if isinstance(raw_weaknesses, list):
            for w in raw_weaknesses:
                if isinstance(w, str):
                    screening_gaps.append({"skill": w, "description": w})
                elif isinstance(w, dict):
                    screening_gaps.append(w)

    # ── Load org name ─────────────────────────────────────────────
    org_rows = db.table("organizations") \
        .select("name") \
        .eq("id", user.org_id) \
        .execute().data
    company_name = org_rows[0]["name"] if org_rows else "Our Company"

    # ── Call Interview Agent ──────────────────────────────────────
    try:
        result = await _launch(
            candidate_id=candidate["id"],
            job_id=job["id"],
            org_id=user.org_id,
            candidate_name=candidate["name"],
            candidate_email=candidate.get("email", ""),
            job_title=job["role_title"],
            cv_text=candidate.get("raw_cv_text", ""),
            jd_text=job.get("raw_text", ""),
            screening_gaps=screening_gaps,
            recruiter_name=user.email,
            company_name=company_name,
            questions_target=5,
        )
    except ValueError as e:
        # Active session already exists
        return JSONResponse({"error": str(e)}, status_code=409)
    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to launch interview: {str(e)}"},
            status_code=500
        )

    # ── Log audit ─────────────────────────────────────────────────
    log_audit(
        run_id=run_id,
        node_name="interview_launch",
        action="interview_launched",
        payload={
            "session_id":    result.get("session_id"),
            "interview_url": result.get("interview_url"),
            "launched_by":   user.email,
        },
    )

    # ── Redirect HR to dashboard ──────────────────────────────────
    dashboard_url = get_hr_dashboard_url()
    return RedirectResponse(url=dashboard_url, status_code=302)