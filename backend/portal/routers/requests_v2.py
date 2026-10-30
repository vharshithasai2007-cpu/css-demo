"""Additive v2 portal request API with stakeholder request types.

The v1 endpoints in :mod:`portal.routers.requests` remain complaint-shaped and
unchanged. These v2 endpoints expose both the stakeholder request type and the
optional technical subject category:

* ``COMPLAINT`` and ``GRIEVANCE`` require one of the seven categories and keep
  the existing department routing and dashboard feed behaviour.
* Every other request type must not carry a category and is routed to the
  documented generic simulated desk.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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
from ..request_types import CATEGORY_REQUIRED_TYPES, GENERIC_DESK
from .requests import (
    PortalCategoryValue,
    PortalStatusValue,
    ReplyOut,
    StatusEventOut,
    clean_text,
)

PortalRequestTypeValue = Literal[
    "SUGGESTION",
    "ENQUIRY",
    "GRIEVANCE",
    "COMPLAINT",
    "APPRECIATION",
    "REQUIRED_SUPPORT",
    "WILLING_TO_SUPPORT",
]


class RequestCreateV2(BaseModel):
    request_type: PortalRequestTypeValue
    category: PortalCategoryValue | None = None
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

    @model_validator(mode="after")
    def _check_category_for_request_type(self) -> "RequestCreateV2":
        requires_category = self.request_type in CATEGORY_REQUIRED_TYPES
        if requires_category and self.category is None:
            raise ValueError(
                "category is required for COMPLAINT and GRIEVANCE requests"
            )
        if not requires_category and self.category is not None:
            raise ValueError(
                "category is not applicable to this request type"
            )
        return self


class RequestCreatedV2(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference_id: str
    request_type: str | None
    category: str | None
    department: str
    status: str
    created_at: datetime


class RequestSummaryV2(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference_id: str
    request_type: str | None
    category: str | None
    subject: str
    department: str
    status: str
    created_at: datetime
    updated_at: datetime


class RequestListResponseV2(BaseModel):
    items: list[RequestSummaryV2]
    total: int
    counts: dict[str, int]
    page: int
    page_size: int


class RequestDetailV2(BaseModel):
    reference_id: str
    request_type: str | None
    category: str | None
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


router = APIRouter(prefix="/portal/v2/requests", tags=["portal-requests-v2"])


@router.post(
    "",
    response_model=RequestCreatedV2,
    status_code=status.HTTP_201_CREATED,
)
def submit_request_v2(
    payload: RequestCreateV2,
    current_user: PortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_session),
) -> PortalRequest:
    now = utcnow()
    next_step_at = now + timedelta(seconds=settings.sim_step_seconds)
    department = (
        DEPARTMENT_BY_CATEGORY[payload.category]
        if payload.category is not None
        else GENERIC_DESK
    )
    user_id = current_user.id

    def build(reference_id: str) -> PortalRequest:
        request = PortalRequest(
            reference_id=reference_id,
            user_id=user_id,
            request_type=payload.request_type,
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


@router.get("", response_model=RequestListResponseV2)
def list_requests_v2(
    status_filter: PortalStatusValue | None = Query(default=None, alias="status"),
    category: PortalCategoryValue | None = Query(default=None),
    request_type: PortalRequestTypeValue | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: PortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_session),
) -> RequestListResponseV2:
    """List only the authenticated user's requests, newest first."""

    conditions = [PortalRequest.user_id == current_user.id]
    if status_filter is not None:
        conditions.append(PortalRequest.status == status_filter)
    if category is not None:
        conditions.append(PortalRequest.category == category)
    if request_type is not None:
        conditions.append(PortalRequest.request_type == request_type)

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

    return RequestListResponseV2(
        items=[RequestSummaryV2.model_validate(row) for row in rows],
        total=int(total or 0),
        counts=counts,
        page=page,
        page_size=page_size,
    )


@router.get("/{reference_id}", response_model=RequestDetailV2)
def get_request_v2(
    reference_id: str,
    current_user: PortalUser = Depends(get_current_portal_user),
    db: Session = Depends(get_session),
) -> RequestDetailV2:
    """Return one owned request with its status history and replies."""

    request = db.scalar(
        select(PortalRequest).where(
            PortalRequest.reference_id == reference_id,
            PortalRequest.user_id == current_user.id,
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

    return RequestDetailV2(
        reference_id=request.reference_id,
        request_type=request.request_type,
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
