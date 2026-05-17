"""
ui/routers/upload.py
─────────────────────
Manual CV upload — Workflow B.

Recruiter uploads a CV file and selects a job.
Bypasses classifier entirely — goes straight to ingest node.

Mount in ui/app.py:
    from ui.routers.upload import router as upload_router
    app.include_router(upload_router)
"""

import os
import uuid
import threading
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth.dependencies import CurrentUser, require_user
from db.client import get_db

router = APIRouter()
templates = Jinja2Templates(directory="ui/templates")

# Pipeline trigger — injected by main.py
_trigger_callback = None


def set_upload_trigger_callback(fn):
    global _trigger_callback
    _trigger_callback = fn


# ── Upload form ───────────────────────────────────────────────────

@router.get("/upload", response_class=HTMLResponse)
async def upload_page(
    request: Request,
    job_id: str = None,
    user: CurrentUser = Depends(require_user),
):
    """Show the upload form. Optional ?job_id= pre-selects a job."""
    db = get_db()
    jobs = db.table("job_descriptions").select(
        "id, role_title"
    ).eq("org_id", user.org_id).eq("status", "OPEN").order("role_title").execute().data

    return templates.TemplateResponse(request, "upload.html", {
        "jobs":               jobs,
        "preselected_job_id": job_id or "",
        "user":               user,
    })


@router.post("/upload")
async def upload_cv(
    request: Request,
    job_id: str = Form(...),
    cv_file: UploadFile = File(...),
    user: CurrentUser = Depends(require_user),
):
    """
    Receive uploaded CV, save to temp file, trigger pipeline.
    Redirects to processing page so recruiter sees live progress.
    """
    db = get_db()

    # Validate file type
    filename = cv_file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".doc"):
        jobs = db.table("job_descriptions").select(
            "id, role_title"
        ).eq("org_id", user.org_id).eq("status", "OPEN").execute().data
        return templates.TemplateResponse(
            request, "upload.html",
            {
                "jobs":               jobs,
                "preselected_job_id": job_id,
                "user":               user,
                "error":              "Only PDF or Word (.docx) files are supported.",
            },
            status_code=400,
        )

    # Save to temp file — pipeline reads from disk
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
        prefix="manual_upload_",
        dir="attachments",
    ) as tmp:
        content = await cv_file.read()
        tmp.write(content)
        tmp_path = tmp.name

    # Fetch job title for state
    job = db.table("job_descriptions").select(
        "role_title"
    ).eq("id", job_id).execute().data
    job_title = job[0]["role_title"] if job else "Unknown"

    cv_file_type = suffix.lstrip(".")  # pdf | docx | doc

    # Unique thread ID for this upload
    thread_id = f"manual_{uuid.uuid4().hex}"

    # Build initial state
    initial_state = {
        "email_id":             thread_id,
        "email_subject":        f"Manual upload — {job_title}",
        "email_sender":         user.email,
        "email_body":           "",
        "attachment_path":      tmp_path,
        "cv_file_type":         cv_file_type,
        "has_cv":               True,
        "matched_jd_id":        job_id,
        "matched_jd_title":     job_title,
        "confidence_score":     1.0,
        "match_status":         "MANUALLY_ASSIGNED",
        "top_jd_matches":       [],
        "source":               "MANUAL_UPLOAD",
        "discard_reason":       None,
        "candidate_id":         "",
        "run_id":               "",
        "raw_cv_text":          "",
        "candidate_name":       "",
        "candidate_email":      "",
        "current_node":         "ingest",
        "screening_result":     None,
        "composite_score":      None,
        "recommendation":       None,
        "judge_verdict":        None,
        "conflict_flag":        None,
        "conflict_reason":      None,
        "hitl_reviewed":        False,
        "hitl_final_decision":  None,
        "hitl_override_reason": None,
        "reviewed_by":          None,
        "final_decision":       "",
        "error":                None,
        "error_node":           None,
        "org_id":               user.org_id,
    }

    # Run pipeline in background thread — returns immediately
    if _trigger_callback:
        t = threading.Thread(
            target=_trigger_callback,
            args=(initial_state,),
            daemon=True,
        )
        t.start()
        print(f"[Upload] Pipeline started in background thread")
    else:
        print("[Upload] Warning: no pipeline trigger callback set")

    # Redirect to processing page
    return RedirectResponse(url=f"/processing?thread={thread_id}", status_code=302)


# ── Processing page ───────────────────────────────────────────────

@router.get("/processing", response_class=HTMLResponse)
async def processing_page(
    request: Request,
    thread: str,
    user: CurrentUser = Depends(require_user),
):
    """Live progress page shown while pipeline runs in background."""
    return templates.TemplateResponse(request, "processing.html", {
        "user":      user,
        "thread_id": thread,
    })


@router.get("/api/processing-status")
async def processing_status(
    thread: str,
    user: CurrentUser = Depends(require_user),
):
    """
    Polled every 2 seconds by processing.html.
    Returns current pipeline stage and whether it is ready for HR review.
    """
    db = get_db()

    # Find candidate by source_email_id (set to thread_id on upload)
    candidates = db.table("candidates").select(
        "id, source_email_id"
    ).eq("org_id", user.org_id).execute().data

    run = None
    for c in candidates:
        if c.get("source_email_id") == thread:
            runs = db.table("pipeline_runs").select(
                "id, current_node, status"
            ).eq("candidate_id", c["id"]).eq("org_id", user.org_id).execute().data
            if runs:
                run = runs[0]
                break

    if not run:
        return JSONResponse({"stage": "parsing", "done": False, "run_id": None})

    node   = run["current_node"]
    status = run["status"]

    stage_map = {
        "classifier":    "parsing",
        "ingest":        "parsing",
        "screening":     "screening",
        "judge":         "reviewing",
        "hitl_pending":  "done",
        "hitl_reviewed": "done",
    }
    stage = stage_map.get(node, "parsing")

    return JSONResponse({
        "stage":  stage,
        "done":   status == "pending_review",
        "run_id": run["id"] if status == "pending_review" else None,
    })