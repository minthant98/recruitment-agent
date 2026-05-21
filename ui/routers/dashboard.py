"""
ui/routers/dashboard.py
────────────────────────
Dashboard route — the recruiter's morning view.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth.dependencies import CurrentUser, require_user
from db.client import get_db
from db.queries import log_audit

router = APIRouter()
templates = Jinja2Templates(directory="ui/templates")


def _resolve_status(run: dict, hitl_map: dict) -> str:
    """
    Resolve the real status of a pipeline run.
    'done' runs need to be mapped via hitl_reviews.
    """
    status = run["status"]
    if status == "done" and run["id"] in hitl_map:
        decision = hitl_map[run["id"]]
        if decision == "SHORTLIST_INTERVIEW":
            return "shortlisted"
        elif decision == "HOLD":
            return "hold"
        elif decision == "REJECT":
            return "rejected"
    return status


def _get_dashboard_data(org_id: str) -> dict:
    db = get_db()

    runs = db.table("pipeline_runs").select(
        "id, status, match_status, confidence_score, created_at, "
        "updated_at, candidate_id, jd_id"
    ).eq("org_id", org_id).order("created_at", desc=True).execute().data

    if not runs:
        return {
            "needs_review": [],
            "shortlisted":  [],
            "needs_confirmation": [],
            "unmatched": [],
            "stats": {"total": 0, "shortlisted": 0, "rejected": 0, "on_hold": 0},
        }

    # ── Fetch HITL decisions to resolve 'done' statuses ──────────
    run_ids = [r["id"] for r in runs]
    hitl_rows = db.table("hitl_reviews").select(
        "run_id, final_decision"
    ).in_("run_id", run_ids).execute().data
    hitl_map = {h["run_id"]: h["final_decision"] for h in hitl_rows}

    # ── Resolve real status for every run ─────────────────────────
    for r in runs:
        r["resolved_status"] = _resolve_status(r, hitl_map)

    # ── Fetch supporting data ─────────────────────────────────────
    candidate_ids = list({r["candidate_id"] for r in runs})
    candidates = db.table("candidates").select(
        "id, name, email"
    ).in_("id", candidate_ids).execute().data
    candidate_map = {c["id"]: c for c in candidates}

    jd_ids = list({r["jd_id"] for r in runs if r.get("jd_id")})
    jd_map = {}
    if jd_ids:
        jds = db.table("job_descriptions").select(
            "id, role_title"
        ).in_("id", jd_ids).execute().data
        jd_map = {j["id"]: j["role_title"] for j in jds}

    scores = db.table("screening_results").select(
        "run_id, composite_score"
    ).in_("run_id", run_ids).execute().data
    score_map = {s["run_id"]: s["composite_score"] for s in scores}

    # Check which shortlisted candidates already have an interview launched
    shortlisted_ids = [r["id"] for r in runs if r["resolved_status"] == "shortlisted"]
    interview_launched_set = set()
    if shortlisted_ids:
        try:
            audit_rows = db.table("audit_log").select("run_id").eq(
                "node_name", "interview_launch"
            ).in_("run_id", shortlisted_ids).execute().data
            interview_launched_set = {a["run_id"] for a in audit_rows}
        except Exception:
            pass

    # ── Enrich runs ───────────────────────────────────────────────
    for r in runs:
        cand = candidate_map.get(r["candidate_id"], {})
        r["candidate_name"]     = cand.get("name", "Unknown")
        r["candidate_email"]    = cand.get("email", "")
        r["role_title"]         = jd_map.get(r.get("jd_id"), "—")
        r["score"]              = score_map.get(r["id"])
        r["interview_launched"] = r["id"] in interview_launched_set
        r["confidence_pct"] = (
            f'{int(r["confidence_score"] * 100)}%'
            if r.get("confidence_score") else "—"
        )
        try:
            created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            delta   = datetime.now(timezone.utc) - created
            hours   = int(delta.total_seconds() // 3600)
            if hours < 1:
                r["age"] = "Just now"
            elif hours < 24:
                r["age"] = f"{hours}h ago"
            else:
                r["age"] = f"{delta.days}d ago"
        except Exception:
            r["age"] = "—"

    # ── Build queues using resolved_status ────────────────────────
    needs_review = [r for r in runs if r["resolved_status"] == "pending_review"]
    shortlisted  = [r for r in runs if r["resolved_status"] == "shortlisted"]
    needs_confirmation = [
        r for r in runs
        if r.get("match_status") == "AWAITING_CONFIRMATION"
        and r["resolved_status"] not in ("shortlisted", "rejected", "hold")
    ]
    unmatched = [
        r for r in runs
        if r.get("match_status") == "UNMATCHED"
        and r["resolved_status"] not in ("shortlisted", "rejected", "hold")
    ]

    # ── Month stats ───────────────────────────────────────────────
    now         = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_runs  = [
        r for r in runs
        if datetime.fromisoformat(
            r["created_at"].replace("Z", "+00:00")
        ) >= month_start
    ]

    stats = {
        "total":       len(month_runs),
        "shortlisted": sum(1 for r in month_runs if r["resolved_status"] == "shortlisted"),
        "rejected":    sum(1 for r in month_runs if r["resolved_status"] == "rejected"),
        "on_hold":     sum(1 for r in month_runs if r["resolved_status"] == "hold"),
    }

    return {
        "needs_review":       needs_review,
        "shortlisted":        shortlisted,
        "needs_confirmation": needs_confirmation,
        "unmatched":          unmatched,
        "stats":              stats,
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: CurrentUser = Depends(require_user),
):
    data = _get_dashboard_data(user.org_id)
    return templates.TemplateResponse(request, "dashboard.html", {
        **data,
        "user": user,
    })


@router.post("/launch-interview/{run_id}")
async def launch_interview(
    run_id: str,
    user: CurrentUser = Depends(require_user),
):
    """
    HR launches an AI interview for a shortlisted candidate.
    """
    from tools.interview_client import launch_interview as _launch, get_hr_dashboard_url

    db = get_db()

    run_rows = db.table("pipeline_runs").select("*") \
        .eq("id", run_id).eq("org_id", user.org_id).execute().data
    if not run_rows:
        return JSONResponse({"error": "Pipeline run not found."}, status_code=404)
    run = run_rows[0]

    cand_rows = db.table("candidates").select("id, name, email, raw_cv_text") \
        .eq("id", run["candidate_id"]).execute().data
    if not cand_rows:
        return JSONResponse({"error": "Candidate not found."}, status_code=404)
    candidate = cand_rows[0]

    job_rows = db.table("job_descriptions").select("id, role_title, raw_text") \
        .eq("id", run["jd_id"]).execute().data
    if not job_rows:
        return JSONResponse({"error": "Job not found."}, status_code=404)
    job = job_rows[0]

    screening_gaps = []
    screening_rows = db.table("screening_results").select("weaknesses") \
        .eq("run_id", run_id).execute().data
    if screening_rows and screening_rows[0].get("weaknesses"):
        raw = screening_rows[0]["weaknesses"]
        if isinstance(raw, list):
            for w in raw:
                if isinstance(w, str):
                    screening_gaps.append({"skill": w, "description": w})
                elif isinstance(w, dict):
                    screening_gaps.append(w)

    org_rows = db.table("organizations").select("name") \
        .eq("id", user.org_id).execute().data
    company_name = org_rows[0]["name"] if org_rows else "Our Company"

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
        return JSONResponse({"error": str(e)}, status_code=409)
    except Exception as e:
        return JSONResponse({"error": f"Failed to launch: {str(e)}"}, status_code=500)

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

    # Return JSON so the JS can redirect — fetch() follows 302 automatically
    # which causes it to fetch the dashboard URL instead of handling the response
    return JSONResponse({
        "success":      True,
        "redirect_url": get_hr_dashboard_url(),
        "session_id":   result.get("session_id"),
    })


@router.get("/api/pending-counts")
async def pending_counts(user: CurrentUser = Depends(require_user)):
    db = get_db()
    runs = db.table("pipeline_runs").select(
        "id, status, match_status"
    ).eq("org_id", user.org_id).execute().data

    run_ids = [r["id"] for r in runs]
    hitl_rows = db.table("hitl_reviews").select(
        "run_id, final_decision"
    ).in_("run_id", run_ids).execute().data
    hitl_map = {h["run_id"]: h["final_decision"] for h in hitl_rows}

    for r in runs:
        r["resolved_status"] = _resolve_status(r, hitl_map)

    needs_review = sum(1 for r in runs if r["resolved_status"] == "pending_review")
    needs_confirmation = sum(
        1 for r in runs
        if r.get("match_status") == "AWAITING_CONFIRMATION"
        and r["resolved_status"] not in ("shortlisted", "rejected", "hold")
    )
    unmatched = sum(
        1 for r in runs
        if r.get("match_status") == "UNMATCHED"
        and r["resolved_status"] not in ("shortlisted", "rejected", "hold")
    )

    return JSONResponse({
        "total":               needs_review + needs_confirmation + unmatched,
        "needs_review":        needs_review,
        "needs_confirmation":  needs_confirmation,
        "unmatched":           unmatched,
    })