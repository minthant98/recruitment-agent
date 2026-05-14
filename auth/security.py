"""
auth/security.py
────────────────
Password hashing and JWT token creation/verification.
Nothing web-framework-specific here — pure crypto utilities.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import get_settings

settings = get_settings()

# ── Password hashing ─────────────────────────────────────────────
# bcrypt is the gold standard — slow by design, resists brute force
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
    bcrypt__ident="2b",
)


def hash_password(plain: str) -> str:
    """Hash a plain-text password. Store the result, never the plain text."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored hash."""
    return pwd_context.verify(plain, hashed)


# ── JWT ──────────────────────────────────────────────────────────
# The token payload (claims) we embed in every JWT.
# org_id is critical — it scopes every DB query to the right tenant.

def create_access_token(
    user_id: str,
    org_id: str,
    email: str,
    role: str,
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Create a signed JWT containing user identity + org scope.

    The token is signed with SECRET_KEY — tamper-evident.
    Expiry defaults to ACCESS_TOKEN_EXPIRE_MINUTES from config.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,          # subject — user's UUID
        "org_id": org_id,        # tenant scope — ALL queries filter by this
        "email": email,
        "role": role,            # recruiter | admin
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT. Returns the payload dict or None if invalid/expired.
    Never raises — always returns None on failure so middleware can handle cleanly.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        return None


def create_invite_token() -> str:
    """
    Generate a secure random token for colleague invites.
    This is NOT a JWT — just a random string stored in the DB.
    """
    import secrets
    return secrets.token_urlsafe(32)