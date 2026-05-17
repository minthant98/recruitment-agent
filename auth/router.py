"""
auth/router.py
──────────────
Auth routes: login, logout, invite a colleague, accept invite.

Mount this in main.py:
    from auth.router import router as auth_router
    app.include_router(auth_router, prefix="/auth")
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from auth.dependencies import CurrentUser, require_admin, require_user
from auth.security import (
    create_access_token,
    create_invite_token,
    hash_password,
    verify_password,
)
from config import get_settings
from db.client import get_db

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="ui/templates")


# ── Login ────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login form."""
    return templates.TemplateResponse(request, "auth/login.html", {})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    """
    Verify credentials, issue JWT cookie, redirect to dashboard.
    Generic error message — never reveal whether email exists.
    """
    db = get_db()

    # Look up user by email
    result = db.table("users").select("*").eq("email", email.lower().strip()).execute()
    user = result.data[0] if result.data else None

    # Constant-time check — verify_password runs even if user not found
    # to prevent timing attacks that reveal whether an email is registered
    dummy_hash = "$2b$12$dummy.hash.to.prevent.timing.attacks.padding.here"
    stored_hash = user["hashed_password"] if user else dummy_hash
    password_ok = verify_password(password, stored_hash)

    if not user or not password_ok:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Invalid email or password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # Issue JWT
    token = create_access_token(
        user_id=user["id"],
        org_id=user["org_id"],
        email=user["email"],
        role=user["role"],
    )

    # Set cookie and redirect to dashboard
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,       # not accessible from JS — XSS protection
        secure=False,        # set True in production (HTTPS only)
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response


# ── Logout ───────────────────────────────────────────────────────

@router.post("/logout")
async def logout():
    """Clear the auth cookie and redirect to login."""
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    return response


# ── Invite a colleague ───────────────────────────────────────────

@router.post("/invite")
async def invite_colleague(
    email: str = Form(...),
    role: str = Form(default="recruiter"),
    user: CurrentUser = Depends(require_admin),
):
    """
    Admin sends an invite link to a colleague.
    Creates an invite_token row and emails the signup link.
    Only admins can invite.
    """
    db = get_db()

    # Check not already a user
    existing = db.table("users").select("id").eq("email", email.lower()).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="User already exists")

    token = create_invite_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

    db.table("invite_tokens").insert({
        "org_id": user.org_id,
        "email": email.lower().strip(),
        "token": token,
        "invited_by": user.user_id,
        "expires_at": expires_at.isoformat(),
    }).execute()

    # TODO: send invite email via tools/email.py
    # For now returns the link — wire up email in Phase 8
    invite_link = f"{settings.APP_BASE_URL}/auth/accept-invite?token={token}"

    return {"message": "Invite created", "invite_link": invite_link}


# ── Accept invite ────────────────────────────────────────────────

@router.get("/accept-invite", response_class=HTMLResponse)
async def accept_invite_page(request: Request, token: str):
    """Show the set-password form for an invited user."""
    db = get_db()

    result = db.table("invite_tokens").select("*").eq("token", token).execute()
    invite = result.data[0] if result.data else None

    if not invite or invite["used"]:
        return templates.TemplateResponse(
            request, "auth/invite_invalid.html", {}
        )

    expires_at = datetime.fromisoformat(invite["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        return templates.TemplateResponse(
            request, "auth/invite_invalid.html", {"reason": "expired"}
        )

    return templates.TemplateResponse(
        request, "auth/accept_invite.html", {"token": token, "email": invite["email"]}
    )


@router.post("/accept-invite")
async def accept_invite(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
):
    """Create the user account from an invite token."""
    db = get_db()

    result = db.table("invite_tokens").select("*").eq("token", token).execute()
    invite = result.data[0] if result.data else None

    if not invite or invite["used"]:
        raise HTTPException(status_code=400, detail="Invalid or used invite token")

    # Create user
    db.table("users").insert({
        "org_id": invite["org_id"],
        "email": invite["email"],
        "hashed_password": hash_password(password),
        "role": "recruiter",
        "invited_by": invite["invited_by"],
    }).execute()

    # Mark token as used
    db.table("invite_tokens").update({"used": True}).eq("token", token).execute()

    # Redirect to login
    response = RedirectResponse(
        url="/auth/login?welcome=1", status_code=status.HTTP_302_FOUND
    )
    return response

@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """Show the signup form."""
    return templates.TemplateResponse(request, "auth/signup.html", {})
 
 
@router.post("/signup")
async def signup(
    request: Request,
    company_name: str = Form(...),
    email:        str = Form(...),
    password:     str = Form(...),
):
    """
    Create a new organisation and admin user in one step.
    Auto logs the user in and redirects to onboarding.
    """
    db = get_db()
 
    # Check email not already taken
    existing = db.table("users").select("id").eq(
        "email", email.lower().strip()
    ).execute()
    if existing.data:
        return templates.TemplateResponse(
            request, "auth/signup.html",
            {"error": "An account with this email already exists."},
            status_code=400,
        )
 
    # Create organisation
    org_result = db.table("organizations").insert({
        "name":               company_name.strip(),
        "onboarding_complete": False,
    }).execute()
    org_id = org_result.data[0]["id"]
 
    # Create admin user
    user_result = db.table("users").insert({
        "org_id":          org_id,
        "email":           email.lower().strip(),
        "hashed_password": hash_password(password),
        "role":            "admin",
    }).execute()
    user = user_result.data[0]
 
    # Issue JWT and log straight in
    token = create_access_token(
        user_id=user["id"],
        org_id=org_id,
        email=user["email"],
        role=user["role"],
    )
 
    # Redirect to onboarding
    org = db.table("organizations").select(
        "onboarding_complete"
    ).eq("id", user["org_id"]).execute()
    onboarding_done = org.data[0].get("onboarding_complete") if org.data else True

    redirect_url = "/dashboard" if onboarding_done else "/onboarding"
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,   # set True in production
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response