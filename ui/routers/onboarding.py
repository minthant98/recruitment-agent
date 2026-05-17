"""
ui/routers/onboarding.py
─────────────────────────
Onboarding page — shown after signup until all 3 steps are complete.

Steps:
  1. Add first job        → checks job_descriptions table
  2. Upload first CV      → checks pipeline_runs table
  3. Review first candidate → checks hitl_reviews table

Auto-completes steps based on real data.
When all steps done → marks org as onboarding_complete and redirects to dashboard.

Mount in ui/app.py:
    from ui.routers.onboarding import router as onboarding_router
    app.include_router(onboarding_router)
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth.dependencies import CurrentUser, require_user
from db.client import get_db

router = APIRouter()
templates = Jinja2Templates(directory="ui/templates")


def _get_onboarding_status(org_id: str) -> dict:
    """
    Check which onboarding steps are complete for this org.
    Returns dict with step completion booleans and overall progress.
    """
    db = get_db()

    # Step 1 — has at least one job
    jobs = db.table("job_descriptions").select(
        "id"
    ).eq("org_id", org_id).limit(1).execute()
    has_job = len(jobs.data) > 0

    # Step 2 — has at least one CV processed
    runs = db.table("pipeline_runs").select(
        "id"
    ).eq("org_id", org_id).limit(1).execute()
    has_cv = len(runs.data) > 0

    # Step 3 — has at least one HR review decision
    if runs.data:
        run_ids = [r["id"] for r in db.table("pipeline_runs").select(
            "id"
        ).eq("org_id", org_id).execute().data]
        if run_ids:
            reviews = db.table("hitl_reviews").select(
                "id"
            ).in_("run_id", run_ids).limit(1).execute()
            has_review = len(reviews.data) > 0
        else:
            has_review = False
    else:
        has_review = False

    steps = [has_job, has_cv, has_review]
    completed = sum(steps)

    return {
        "has_job":    has_job,
        "has_cv":     has_cv,
        "has_review": has_review,
        "completed":  completed,
        "total":      3,
        "all_done":   all(steps),
        "pct":        int(completed / 3 * 100),
    }


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(
    request: Request,
    user: CurrentUser = Depends(require_user),
):
    db = get_db()

    # Check if onboarding already complete
    org = db.table("organizations").select(
        "onboarding_complete, name"
    ).eq("id", user.org_id).execute()
    org = org.data[0] if org.data else {}

    if org.get("onboarding_complete"):
        return RedirectResponse(url="/dashboard", status_code=302)

    status = _get_onboarding_status(user.org_id)

    # If all steps done — mark complete and redirect
    if status["all_done"]:
        db.table("organizations").update({
            "onboarding_complete": True
        }).eq("id", user.org_id).execute()
        return RedirectResponse(url="/dashboard", status_code=302)

    return templates.TemplateResponse(request, "onboarding.html", {
        "user":        user,
        "org_name":    org.get("name", "Your company"),
        **status,
    })