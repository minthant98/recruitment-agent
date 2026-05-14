"""
ui/routers/dashboard.py
────────────────────────
Dashboard route — the recruiter's morning view.

Shows three attention queues:
  1. Needs review          — screened, awaiting HR decision
  2. Needs confirmation    — MEDIUM confidence, awaiting job match confirm
  3. Unmatched CVs         — LOW confidence, awaiting manual assignment

Plus month stats: total CVs, shortlisted, rejected, on hold.

Mount in ui/app.py:
    from ui.routers.dashboard import router as dashboard_router
    app.include_router(dashboard_router)
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth.dependencies import CurrentUser, require_user
from db.client import get_db

router = APIRouter()
templates = Jinja2Templates(directory="ui/templates")


def _get_dashboard_data(org_id: str) -> dict:
    """
    Fetch all data needed for the dashboard in as few queries as possible.
    Returns queues + stats ready for the template.
    """
    db = get_db()

    # ── Fetch all pipeline runs for this org ─────────────────────
    runs = db.table("pipeline_runs").select(
        "id, status, match_status, confidence_score, created_at, "
        "updated_at, candidate_id, jd_id"
    ).eq("org_id", org_id).order("created_at", desc=True).execute().data

    if not runs:
        return {
            "needs_review": [],
            "needs_confirmation": [],
            "unmatched": [],
            "stats": {"total": 0, "shortlisted": 0, "rejected": 0, "on_hold": 0},
        }

    # ── Fetch candidate names ────────────────────────────────────
    candidate_ids = list({r["candidate_id"] for r in runs})
    candidates = db.table("candidates").select(
        "id, name, email"
    ).in_("id", candidate_ids).execute().data
    candidate_map = {c["id"]: c for c in candidates}

    # ── Fetch job titles ─────────────────────────────────────────
    jd_ids = list({r["jd_id"] for r in runs if r.get("jd_id")})
    jd_map = {}
    if jd_ids:
        jds = db.table("job_descriptions").select(
            "id, role_title"
        ).in_("id", jd_ids).execute().data
        jd_map = {j["id"]: j["role_title"] for j in jds}

    # ── Fetch composite scores ───────────────────────────────────
    run_ids = [r["id"] for r in runs]
    scores = db.table("screening_results").select(
        "run_id, composite_score"
    ).in_("run_id", run_ids).execute().data
    score_map = {s["run_id"]: s["composite_score"] for s in scores}

    # ── Enrich runs ──────────────────────────────────────────────
    for r in runs:
        cand = candidate_map.get(r["candidate_id"], {})
        r["candidate_name"]  = cand.get("name", "Unknown")
        r["candidate_email"] = cand.get("email", "")
        r["role_title"]      = jd_map.get(r.get("jd_id"), "—")
        r["score"]           = score_map.get(r["id"])
        r["confidence_pct"]  = (
            f'{int(r["confidence_score"] * 100)}%'
            if r.get("confidence_score") else "—"
        )
        # Human-readable age
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

    # ── Build queues ─────────────────────────────────────────────
    needs_review = [
        r for r in runs
        if r["status"] in ("pending_review",)
    ]

    needs_confirmation = [
        r for r in runs
        if r.get("match_status") == "AWAITING_CONFIRMATION"
        and r["status"] not in ("shortlisted", "rejected", "hold")
    ]

    unmatched = [
        r for r in runs
        if r.get("match_status") == "UNMATCHED"
        and r["status"] not in ("shortlisted", "rejected", "hold")
    ]

    # ── Month stats ──────────────────────────────────────────────
    now   = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    month_runs = [
        r for r in runs
        if datetime.fromisoformat(
            r["created_at"].replace("Z", "+00:00")
        ) >= month_start
    ]

    stats = {
        "total":       len(month_runs),
        "shortlisted": sum(1 for r in month_runs if r["status"] == "shortlisted"),
        "rejected":    sum(1 for r in month_runs if r["status"] == "rejected"),
        "on_hold":     sum(1 for r in month_runs if r["status"] == "hold"),
    }

    return {
        "needs_review":        needs_review,
        "needs_confirmation":  needs_confirmation,
        "unmatched":           unmatched,
        "stats":               stats,
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
    

from fastapi.responses import JSONResponse

@router.get("/api/pending-counts")
async def pending_counts(user: CurrentUser = Depends(require_user)):
    """
    Lightweight endpoint — returns pending queue counts only.
    Called every 10 seconds by the nav badge JS.
    No heavy joins — just status counts.
    """
    db = get_db()

    runs = db.table("pipeline_runs").select(
        "status, match_status"
    ).eq("org_id", user.org_id).execute().data

    needs_review = sum(
        1 for r in runs if r["status"] == "pending_review"
    )
    needs_confirmation = sum(
        1 for r in runs
        if r.get("match_status") == "AWAITING_CONFIRMATION"
        and r["status"] not in ("shortlisted", "rejected", "hold")
    )
    unmatched = sum(
        1 for r in runs
        if r.get("match_status") == "UNMATCHED"
        and r["status"] not in ("shortlisted", "rejected", "hold")
    )

    total = needs_review + needs_confirmation + unmatched

    return JSONResponse({
        "total":               total,
        "needs_review":        needs_review,
        "needs_confirmation":  needs_confirmation,
        "unmatched":           unmatched,
    })