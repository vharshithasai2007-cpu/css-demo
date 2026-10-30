"""Authenticated portal request submission.

Mounted at /portal/requests by mock_css.main. Every request belongs to the
authenticated portal user; the portal never accepts an anonymous submission.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..categories import DEPARTMENT_BY_CATEGORY
from ..config import settings
from ..db import get_session
from ..dependencies import get_current_portal_user
from ..ids import ReferenceAllocationError, persist_with_reference
from ..models import (
    PORTAL_STATUSES,
    STATUS_SUBMITTED,
    PortalReply,
    PortalRequest,
    PortalStatusEvent,
    PortalUser,
    utcnow,
)

PortalCategoryValue = Literal[
    "FEE",
    "FACULTY",
    "INFRASTRUCTURE",
    "APPROVAL_VIOLATION",
    "ACADEMIC_ADMINISTRATION",
    "GOVERNANCE_MISCONDUCT",
    "RAGGING_DISCRIMINATION",
]

# C0 controls except TAB/LF/CR, plus DEL and C1 controls.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def clean_text(value: str) -> str:
    """Remove control characters and trim surrounding whitespace."""

    return _CONTROL_CHARACTERS.sub("", value).strip()


class RequestCreate(BaseModel):
    category: PortalCategoryValue
    subject: str = Field(min_length=5, max_length=150)
    description: str = Field(min_length=20, max_length=4000)
    institution_name: str = Field(min_length=3, max_length=200)
    state: str | None = Field(default=None, max_length=80)

    @field_validator(
        "subject",
        "description",
        "institution_name",
        "state",
        mode="before",
    )
    @classmethod
    def _strip_control_characters(cls, value):
        return clean_text(value) if isinstance(value, str) else value

    @field_validator("state", mode="after")
    @classmethod
    def _blank_state_to_none(cls, value: str | None) -> str | None:
        return value or None


class RequestCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference_id: str
    status: str
    category: str
    created_at: datetime


PortalStatusValue = Literal[
    "SUBMITTED",
    "UNDER_REVIEW",
    "REPLY_SENT",
    "RESOLVED",
]


class RequestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference_id: str
    created_at: datetime
    category: str
    subject: str
    department: str
    status: str
    updated_at: datetime


class RequestListResponse(BaseModel):
    items: list[RequestSummary]
    total: int
    counts: dict[str, int]
    page: int
    page_size: int


class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    remarks: str | None
    actor: str | None
    created_at: datetime


class ReplyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department: str
    message: str
    is_simulated: bool
    created_at: datetime


class RequestDetail(BaseModel):
    reference_id: str
    category: str
    subject: str
    description: str
    institution_name: str
    state: str | None
    status: str
    department: str
    created_at: datetime
    updated_at: datetime
    next_step_at: datetime | None
    status_events: list[StatusEventOut]
    replies: list[ReplyOut]


router = APIRouter(prefix="/portal/requests", tags=["portal-requests"])


@router.post(
    "",
    response_model=RequestCreated,
    status_code=status.HTTP_201_CREATED,
)
def submit_request(
    payload: RequestCreate,
    current_user: PortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_session),
) -> PortalRequest:
    now = utcnow()
    next_step_at = now + timedelta(seconds=settings.sim_step_seconds)
    department = DEPARTMENT_BY_CATEGORY[payload.category]
    user_id = current_user.id

    def build(reference_id: str) -> PortalRequest:
        request = PortalRequest(
            reference_id=reference_id,
            user_id=user_id,
            category=payload.category,
            subject=payload.subject,
            description=payload.description,
            institution_name=payload.institution_name,
            state=payload.state,
            status=STATUS_SUBMITTED,
            department=department,
            created_at=now,
            updated_at=now,
            next_step_at=next_step_at,
        )
        request.status_events.append(
            PortalStatusEvent(
                status=STATUS_SUBMITTED,
                remarks="Request registered (simulated)",
                actor="System (SIMULATED)",
                created_at=now,
            )
        )
        return request

    try:
        return persist_with_reference(db, build, year=now.year)
    except ReferenceAllocationError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not allocate a reference id",
        ) from None


@router.get("", response_model=RequestListResponse)
def list_requests(
    status_filter: PortalStatusValue | None = Query(default=None, alias="status"),
    category: PortalCategoryValue | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: PortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_session),
) -> RequestListResponse:
    """List only the authenticated user's requests, newest first."""

    # v1 predates stakeholder request types. It remains complaint-shaped and
    # therefore only lists rows that carry a technical subject category.
    conditions = [
        PortalRequest.user_id == current_user.id,
        PortalRequest.category.is_not(None),
    ]
    if status_filter is not None:
        conditions.append(PortalRequest.status == status_filter)
    if category is not None:
        conditions.append(PortalRequest.category == category)

    total = db.scalar(
        select(func.count()).select_from(PortalRequest).where(*conditions)
    )
    rows = db.scalars(
        select(PortalRequest)
        .where(*conditions)
        .order_by(PortalRequest.created_at.desc(), PortalRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    count_rows = db.execute(
        select(PortalRequest.status, func.count())
        .where(PortalRequest.user_id == current_user.id)
        .group_by(PortalRequest.status)
    ).all()
    counts = {value: 0 for value in PORTAL_STATUSES}
    for status_value, count in count_rows:
        counts[status_value] = int(count)

    return RequestListResponse(
        items=[RequestSummary.model_validate(row) for row in rows],
        total=int(total or 0),
        counts=counts,
        page=page,
        page_size=page_size,
    )


@router.get("/{reference_id}", response_model=RequestDetail)
def get_request(
    reference_id: str,
    current_user: PortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_session),
) -> RequestDetail:
    """Return one owned request with its status history and replies.

    A request owned by another user and an unknown reference ID deliberately
    produce the same 404 body.
    """

    request = db.scalar(
        select(PortalRequest).where(
            PortalRequest.reference_id == reference_id,
            PortalRequest.user_id == current_user.id,
            PortalRequest.category.is_not(None),
        )
    )
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    events = db.scalars(
        select(PortalStatusEvent)
        .where(PortalStatusEvent.request_id == request.id)
        .order_by(PortalStatusEvent.created_at.asc(), PortalStatusEvent.id.asc())
    ).all()
    replies = db.scalars(
        select(PortalReply)
        .where(PortalReply.request_id == request.id)
        .order_by(PortalReply.created_at.asc(), PortalReply.id.asc())
    ).all()

    return RequestDetail(
        reference_id=request.reference_id,
        category=request.category,
        subject=request.subject,
        description=request.description,
        institution_name=request.institution_name,
        state=request.state,
        status=request.status,
        department=request.department,
        created_at=request.created_at,
        updated_at=request.updated_at,
        next_step_at=request.next_step_at,
        status_events=[StatusEventOut.model_validate(event) for event in events],
        replies=[ReplyOut.model_validate(reply) for reply in replies],
    )
