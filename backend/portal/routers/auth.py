"""Portal authentication routes.

Mounted at /portal/auth by mock_css.main. This is deliberately separate from
the dashboard's officer authentication and uses only portal tables.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_session
from ..dependencies import get_current_portal_user
from ..models import PortalUser
from ..rate_limit import check_rate_limit
from ..security import create_access_token, hash_password, verify_password

PortalUserType = Literal[
    "STUDENT",
    "FACULTY",
    "INSTITUTION_ADMIN",
    "OTHER",
]

LOGIN_FAILURE_MESSAGE = "Incorrect email or password."


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)
    user_type: PortalUserType
    institution_name: str | None = Field(default=None, max_length=200)

    @field_validator("full_name", mode="before")
    @classmethod
    def _strip_full_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email", mode="before")
    @classmethod
    def _strip_email(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("user_type", mode="before")
    @classmethod
    def _normalize_user_type(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("institution_name", mode="before")
    @classmethod
    def _clean_institution_name(cls, value):
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @model_validator(mode="after")
    def _password_must_differ_from_email(self):
        if self.password.strip().lower() == str(self.email).strip().lower():
            raise ValueError("password must not equal email")
        return self


class LoginRequest(BaseModel):
    email: str
    password: str


class PortalProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    user_type: str
    institution_name: str | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


router = APIRouter(prefix="/portal/auth", tags=["portal-auth"])


@router.post(
    "/register",
    response_model=PortalProfile,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> PortalUser:
    email = str(payload.email).strip().lower()
    check_rate_limit(request, email, action="register")

    existing = db.scalar(select(PortalUser).where(PortalUser.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = PortalUser(
        full_name=payload.full_name,
        email=email,
        user_type=payload.user_type,
        institution_name=payload.institution_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None

    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_session),
) -> TokenResponse:
    email = payload.email.strip().lower()
    check_rate_limit(request, email, action="login")

    user = db.scalar(select(PortalUser).where(PortalUser.email == email))
    if (
        user is None
        or not verify_password(payload.password, user.password_hash)
        or not user.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=LOGIN_FAILURE_MESSAGE,
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        token_type="bearer",
    )


@router.get("/me", response_model=PortalProfile)
def me(current_user: PortalUser = Depends(get_current_portal_user)) -> PortalUser:
    return current_user
