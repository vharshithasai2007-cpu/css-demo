"""Portal-only password hashing and JWT helpers.

This module is intentionally separate from the dashboard's security code. It
uses the same bcrypt scheme but its own secret, audience and issuer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

PORTAL_JWT_ALGORITHM = "HS256"
PORTAL_JWT_AUDIENCE = "css-portal-demo"
PORTAL_JWT_ISSUER = "css-portal-demo"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a portal password with bcrypt (dashboard-compatible scheme)."""

    return pwd_context.hash(password)


# Alias matching the dashboard's helper name, kept local to the portal.
get_password_hash = hash_password


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a password, treating malformed hashes as a failed match."""

    try:
        return pwd_context.verify(plain_password, password_hash)
    except (TypeError, ValueError):
        return False


def create_access_token(
    user_id: int,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a portal JWT for a user ID."""

    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.token_minutes))
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "aud": PORTAL_JWT_AUDIENCE,
        "iss": PORTAL_JWT_ISSUER,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=PORTAL_JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a portal JWT, requiring audience and issuer."""

    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[PORTAL_JWT_ALGORITHM],
        audience=PORTAL_JWT_AUDIENCE,
        issuer=PORTAL_JWT_ISSUER,
    )


# Common aliases for callers that prefer shorter names.
decode_token = decode_access_token
