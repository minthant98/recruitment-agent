"""
app.py — FastAPI web UI for HR review.
Runs standalone on Render (no main.py needed).
Gmail polling and pipeline resume handled separately when running locally.
"""
import os
import threading
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

_UI_DIR       = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE_DIR = os.path.join(_UI_DIR, "templates")
templates     = Jinja2Templates(directory=_TEMPLATE_DIR)

from db.queries import (
    get_pipeline_run,
    get_screening_result,
    get_judge_verdict,
    get_candidate_by_id,
    get_jd_by_id,
    get_audit_trail,
)
from db.client import get_db
from auth.dependencies import require_user, CurrentUser

app = FastAPI(title="Recruitment — HR Platform")

# ── Routers ───────────────────────────────────────────────────────
from auth.router import router as auth_router
app.include_router(auth_router, prefix="/auth")

from ui.routers.jobs import router as jobs_router
app.include_router(jobs_router)

from ui.routers.queue import router as queue_router
app.include_router(queue_router)

from ui.routers.dashboard import router as dashboard_router
app.include_router(dashboard_router)

from ui.routers.upload import router as upload_router
app.include_router(upload_router)

# ── Resume callback ───────────────────────────────────────────────
# Set by main.py when running locally with Gmail polling.
# Not set on Render — HITL decisions are recorded but pipeline
# resume must be triggered manually or via local run.
_resume_callback = None


def set_resume_callback(fn):
    global _resume_callback
    _resume_callback = fn


# ── Root redirect ─────────────────────────────────────────────────
@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard", status_code=302)


# ── Helpers ───────────────────────────────────────────────────────

def _derive_confidence(judge: dict) -> str:
    if not judge:
        return "UNKNOWN"
    score = judge.get("confidence", 0) or 0
    if score >= 80:
        return "HIGH"
    elif score >= 60:
        return "MEDIUM"
    return "LOW"


def _derive_risk(screening: dict, judge: dict) -> str:
    if not screening:
        return "UNKNOWN"
    score    = screening.get("composite_score", 0) or 0
    conflict = judge.get("conflict_flag", False) if judge else False
    missing  = len((screening.get("skills_analysis") or {}).get("missing_required", []))
    if conflict and score < 60:
        return "HIGH"
    elif conflict or score < 70 or missing >= 3:
        return "MEDIUM"
    return "LOW"


def _derive_status(run: dict, screening: dict) -> str:
    status = run.get("status", "")
    node   = run.get("current_node", "")
    rec    = (screening or {}).get("recommendation", "")
    if status == "pending_review" or node == "hitl_pending":
        return "Awaiting HR Review"
    if status == "done":
        if rec == "REJECT":
            return "Rejected"
        if rec == "HOLD":
            return "On Hold"
        if rec == "SHORTLIST_INTERVIEW":
            return "Interview Invited" if node == "scheduling" else "Interview Scheduled"
    if node in ("screening", "judge"):
        return "AI Screening"
    if node == "ingest":
        return "CV Parsing"
    return "In Progress"


def _get_review_data(run_id: str) -> dict | None:
    run = get_pipeline_run(run_id)
    if not run:
        return None

    candidate = get_candidate_by_id(run["candidate_id"]) or {}
    screening = get_screening_result(run_id) or {}
    judge     = get_judge_verdict(run_id) or {}
    jd        = get_jd_by_id(run["jd_id"]) or {}
    audit     = get_audit_trail(run_id) or []

    screening["skills_analysis"]     = screening.get("skills_analysis") or {}
    screening["experience_analysis"] = screening.get("experience_analysis") or {}
    judge["criterion_verdicts"]      = judge.get("criterion_verdicts") or []

    return {
        "run":        run,
        "candidate":  candidate,
        "screening":  screening,
        "judge":      judge,
        "jd":         jd,
        "audit":      audit,
        "confidence": _derive_confidence(judge),
        "risk":       _derive_risk(screening, judge),
        "status":     _derive_status(run, screening),
    }


# ── Review routes ─────────────────────────────────────────────────

@app.get("/review/{run_id}", response_class=HTMLResponse)
async def review_page(
    request: Request,
    run_id: str,
    user: CurrentUser = Depends(require_user),
):
    data = _get_review_data(run_id)
    if not data:
        return HTMLResponse("<h2>Review not found</h2>", status_code=404)
    return templates.TemplateResponse(request, "review.html", {
        "run_id": run_id,
        "user":   user,
        **data,
    })


@app.post("/review/{run_id}")
async def submit_review(
    request: Request,
    run_id: str,
    final_decision:  str = Form(...),
    override_reason: str = Form(""),
    reviewed_by:     str = Form("HR Officer"),
    user: CurrentUser = Depends(require_user),
):
    hr_decision = {
        "hitl_final_decision":  final_decision,
        "hitl_override_reason": override_reason,
        "reviewed_by":          reviewed_by,
    }

    if _resume_callback:
        # Running locally with Gmail polling — resume pipeline in background
        thread = threading.Thread(
            target=_resume_callback,
            args=(run_id, hr_decision),
            daemon=True,
        )
        thread.start()
    else:
        # Running on Render — record the decision in Supabase directly
        # Pipeline resume will happen when local polling picks it up
        from db.queries import update_pipeline_run, log_audit
        from db.client import get_db as _get_db

        db = _get_db()

        # Save HITL review to Supabase
        screener_rec = (_get_review_data(run_id) or {}).get(
            "screening", {}
        ).get("recommendation", "")
        was_overridden = final_decision != screener_rec and bool(screener_rec)

        db.table("hitl_reviews").insert({
            "run_id":         run_id,
            "reviewed_by":    reviewed_by,
            "final_decision": final_decision,
            "override_reason": override_reason or None,
            "was_overridden": was_overridden,
        }).execute()

        update_pipeline_run(
            run_id=run_id,
            current_node="hitl_reviewed",
            status=final_decision.lower().replace("shortlist_interview", "shortlisted"),
        )

        log_audit(
            run_id=run_id,
            node_name="hitl",
            action="reviewed_via_web",
            payload={
                "final_decision":  final_decision,
                "reviewed_by":     reviewed_by,
                "was_overridden":  was_overridden,
                "override_reason": override_reason,
            },
        )

    return RedirectResponse(url=f"/review/{run_id}/done", status_code=303)


@app.get("/review/{run_id}/done", response_class=HTMLResponse)
async def review_done(
    request: Request,
    run_id: str,
    user: CurrentUser = Depends(require_user),
):
    data = _get_review_data(run_id)
    name = (data or {}).get("candidate", {}).get("name", "Candidate")
    return templates.TemplateResponse(request, "review_done.html", {
        "name":   name,
        "run_id": run_id,
        "user":   user,
    })


# ── History routes ────────────────────────────────────────────────

@app.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    user: CurrentUser = Depends(require_user),
):
    return templates.TemplateResponse(request, "history.html", {
        "user": user,
    })


@app.get("/api/pending")
async def api_pending(user: CurrentUser = Depends(require_user)):
    db     = get_db()
    result = db.table("pipeline_runs").select(
        "*, candidates(name, email), job_descriptions(role_title)"
    ).eq("status", "pending_review").eq(
        "org_id", user.org_id
    ).order("created_at", desc=True).execute()
    return result.data


@app.get("/api/history")
async def api_history(user: CurrentUser = Depends(require_user)):
    db     = get_db()
    result = db.table("pipeline_runs").select(
        "*, candidates(name, email), job_descriptions(role_title, departments(name))"
    ).eq("org_id", user.org_id).order("updated_at", desc=True).execute()

    enriched = []
    for run in result.data:
        screening = get_screening_result(run["id"]) or {}
        judge     = get_judge_verdict(run["id"]) or {}
        hitl_res  = db.table("hitl_reviews").select("*").eq("run_id", run["id"]).execute()
        hitl      = hitl_res.data[0] if hitl_res.data else {}

        enriched.append({
            "run_id":            run["id"],
            "candidate_name":    (run.get("candidates") or {}).get("name", ""),
            "candidate_email":   (run.get("candidates") or {}).get("email", ""),
            "role_title":        (run.get("job_descriptions") or {}).get("role_title", ""),
            "department":        ((run.get("job_descriptions") or {}).get("departments") or {}).get("name", ""),
            "composite_score":   screening.get("composite_score", ""),
            "screener_rec":      screening.get("recommendation", ""),
            "judge_rec":         judge.get("suggested_recommendation", ""),
            "conflict_flag":     judge.get("conflict_flag", False) if judge else False,
            "hr_final_decision": hitl.get("final_decision", ""),
            "reviewed_by":       hitl.get("reviewed_by", ""),
            "was_overridden":    hitl.get("was_overridden", False),
            "override_reason":   hitl.get("override_reason", ""),
            "reviewed_at":       hitl.get("reviewed_at", ""),
            "updated_at":        run.get("updated_at", ""),
            "pipeline_status":   run.get("status", ""),
            "confidence":        _derive_confidence(judge),
            "risk":              _derive_risk(screening, judge),
            "status":            _derive_status(run, screening),
            "strengths":         screening.get("strengths", []) or [],
            "weaknesses":        screening.get("weaknesses", []) or [],
        })

    return enriched