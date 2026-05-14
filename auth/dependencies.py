"""
auth/dependencies.py
─────────────────────
FastAPI dependency functions injected into route handlers.

Usage in any route:
    from auth.dependencies import require_user, require_admin

    @router.get("/jobs")
    async def list_jobs(user: CurrentUser = Depends(require_user)):
        # user.org_id is guaranteed here — use it in every DB query
        ...
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status

from auth.security import decode_access_token
from fastapi import Cookie, Depends, HTTPException, Request, status

# ── CurrentUser dataclass ────────────────────────────────────────
# This is what gets injected into every protected route.
# Carries everything the route needs — no extra DB lookup required.

@dataclass
class CurrentUser:
    user_id: str
    org_id: str       # ← scope ALL your DB queries with this
    email: str
    role: str         # recruiter | admin


# ── Core dependency ──────────────────────────────────────────────

from fastapi.responses import RedirectResponse

def _get_current_user(
    request: Request,
    access_token: Optional[str] = Cookie(default=None),
) -> CurrentUser:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/auth/login"},
        )

    payload = decode_access_token(access_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/auth/login"},
        )

    return CurrentUser(
        user_id=payload["sub"],
        org_id=payload["org_id"],
        email=payload["email"],
        role=payload["role"],
    )

# ── Public dependency aliases ────────────────────────────────────
# Import these in your routes — not _get_current_user directly.

def require_user(user: CurrentUser = Depends(_get_current_user)) -> CurrentUser:
    """Any logged-in user (recruiter or admin)."""
    return user


def require_admin(user: CurrentUser = Depends(_get_current_user)) -> CurrentUser:
    """Admin-only routes — raises 403 for recruiters."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# ── Type alias for cleaner route signatures ──────────────────────
# Use this in your route type hints:
#   async def my_route(user: CurrentUser = Depends(require_user)):
#
# It's just a readability shortcut — same thing as the Depends above.