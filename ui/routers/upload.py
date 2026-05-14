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
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
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


# ── Routes ───────────────────────────────────────────────────────

@router.get("/upload", response_class=HTMLResponse)
async def upload_page(
    request: Request,
    job_id: str = None,
    user: CurrentUser = Depends(require_user),
):
    """
    Show the upload form.
    Optional ?job_id= pre-selects a job — used from the job detail page.
    """
    db = get_db()
    jobs = db.table("job_descriptions").select(
        "id, role_title"
    ).eq("org_id", user.org_id).eq("status", "OPEN").order("role_title").execute().data

    return templates.TemplateResponse(request, "upload.html", {
        "jobs": jobs,
        "preselected_job_id": job_id or "",
        "user": user,
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

    Key difference from email intake:
    - No classifier run
    - No confidence scoring
    - match_status = MANUALLY_ASSIGNED immediately
    - source = MANUAL_UPLOAD
    - Recruiter already chose the job — go straight to ingest
    """
    # Validate file type
    filename = cv_file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".docx", ".doc"):
        jobs = get_db().table("job_descriptions").select(
            "id, role_title"
        ).eq("org_id", user.org_id).eq("status", "OPEN").execute().data

        return templates.TemplateResponse(
            request, "upload.html",
            {
                "jobs": jobs,
                "preselected_job_id": job_id,
                "user": user,
                "error": "Only PDF or Word (.docx) files are supported.",
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
    db = get_db()
    job = db.table("job_descriptions").select(
        "role_title"
    ).eq("id", job_id).execute().data
    job_title = job[0]["role_title"] if job else "Unknown"

    cv_file_type = suffix.lstrip(".")  # pdf | docx | doc

    # Build initial state — same shape as email pipeline
    # but with manual upload fields set directly
    initial_state = {
        # Email fields — not applicable for manual upload
        "email_id":             f"manual_{os.path.basename(tmp_path)}",
        "email_subject":        f"Manual upload — {job_title}",
        "email_sender":         user.email,
        "email_body":           "",

        # CV fields — set directly, classifier skipped
        "attachment_path":      tmp_path,
        "cv_file_type":         cv_file_type,
        "has_cv":               True,
        "matched_jd_id":        job_id,
        "matched_jd_title":     job_title,

        # Confidence — not applicable, recruiter chose the job
        "confidence_score":     1.0,
        "match_status":         "MANUALLY_ASSIGNED",
        "top_jd_matches":       [],
        "source":               "MANUAL_UPLOAD",

        # Pipeline state — reset
        "discard_reason":       None,
        "candidate_id":         "",
        "run_id":               "",
        "raw_cv_text":          "",
        "candidate_name":       "",
        "candidate_email":      "",
        "current_node":         "ingest",   # start at ingest, skip classifier
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

    import threading

# Run pipeline in background thread — returns immediately
# Dashboard live badge updates when screening completes
    if _trigger_callback:
        thread = threading.Thread(
            target=_trigger_callback,
            args=(initial_state,),
            daemon=True,
        )
        thread.start()
        print(f"[Upload] Pipeline started in background thread")
    else:
        print("[Upload] Warning: no pipeline trigger callback set")

    return RedirectResponse(url="/dashboard", status_code=302)

