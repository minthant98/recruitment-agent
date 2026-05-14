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
from fastapi.responses import HTMLResponse, RedirectResponse
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