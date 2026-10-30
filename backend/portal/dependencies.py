"""FastAPI dependencies for the CSS educational portal."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from .db import get_session
from .models import PortalUser
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_portal_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_session),
) -> PortalUser:
    """Resolve the active portal user from a valid portal bearer token.

    Missing, malformed, expired, wrongly signed, wrong-audience and inactive
    user tokens all produce the same 401 response.
    """

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        payload = decode_access_token(credentials.credentials)
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject.isdigit():
            raise ValueError("invalid subject")
        user_id = int(subject)
    except (JWTError, TypeError, ValueError):
        raise _unauthorized()

    user = db.get(PortalUser, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user
