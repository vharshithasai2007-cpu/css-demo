"""Simulated department lifecycle for portal requests.

The lifecycle is forward-only::

    SUBMITTED -> UNDER_REVIEW -> REPLY_SENT -> RESOLVED

``RESOLVED`` is terminal. Every transition writes a status event, and entering
``REPLY_SENT`` writes exactly one simulated department reply.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .categories import CATEGORY_VALUES
from .config import settings
from .models import (
    STATUS_REPLY_SENT,
    STATUS_RESOLVED,
    STATUS_SUBMITTED,
    STATUS_UNDER_REVIEW,
    PortalReply,
    PortalRequest,
    PortalStatusEvent,
)
from .request_types import CATEGORY_REQUIRED_TYPES, REQUEST_TYPE_VALUES

ACTOR = "Department (SIMULATED)"

NEXT_STATUS: dict[str, str | None] = {
    STATUS_SUBMITTED: STATUS_UNDER_REVIEW,
    STATUS_UNDER_REVIEW: STATUS_REPLY_SENT,
    STATUS_REPLY_SENT: STATUS_RESOLVED,
    STATUS_RESOLVED: None,
}

STEP_REMARKS: dict[str, str] = {
    STATUS_UNDER_REVIEW: "Request taken up for review (simulated).",
    STATUS_REPLY_SENT: "Simulated department reply issued.",
    STATUS_RESOLVED: "Request marked resolved after the simulated reply.",
}

# Three formal, plain-language templates per category. Every template names the
# department through the {department} placeholder.
REPLY_TEMPLATES: dict[str, tuple[str, ...]] = {
    "FEE": (
        "The {department} has reviewed the fee complaint and asked the institution to confirm its approved fee structure for the current academic year.",
        "The {department} has requested the institution's fee records and demand notices for verification against the approved structure.",
        "The {department} has directed the institution to correct any fee collection above the approved structure and to report the action taken.",
    ),
    "FACULTY": (
        "The {department} has asked the institution to provide the current faculty list and workload for the affected department.",
        "The {department} has requested the institution's faculty recruitment and qualification records for review.",
        "The {department} has directed the institution to address the reported faculty shortage and confirm the teaching arrangements.",
    ),
    "INFRASTRUCTURE": (
        "The {department} has asked the institution to inspect the reported facility and submit a status report.",
        "The {department} has requested the institution's laboratory, classroom and hostel records for verification.",
        "The {department} has directed the institution to complete the required repairs and confirm them to the Cell.",
    ),
    "APPROVAL_VIOLATION": (
        "The {department} has asked the institution to explain the reported deviation from its approved intake and approval conditions.",
        "The {department} has requested the institution's approval records and admission data for verification.",
        "The {department} has directed the institution to stop the reported violation and submit a compliance report.",
    ),
    "ACADEMIC_ADMINISTRATION": (
        "The {department} has asked the institution to review the reported examination or record issue and respond with the facts.",
        "The {department} has requested the relevant academic records and timetable from the institution.",
        "The {department} has directed the institution to correct the reported academic process issue and confirm the action taken.",
    ),
    "GOVERNANCE_MISCONDUCT": (
        "The {department} has asked the institution to provide its record of the reported governance or staff conduct matter.",
        "The {department} has requested the institution's internal inquiry notes and the action taken on the complaint.",
        "The {department} has directed the institution to complete the required inquiry and report the outcome.",
    ),
    "RAGGING_DISCRIMINATION": (
        "The {department} has asked the institution to confirm the action taken on the reported ragging or discrimination incident.",
        "The {department} has requested the institution's committee report and the support provided to the complainant.",
        "The {department} has directed the institution to complete its inquiry and report the outcome without delay.",
    ),
}

if set(REPLY_TEMPLATES) != set(CATEGORY_VALUES):
    raise RuntimeError("Reply templates must cover every portal category")

# Non-complaint request types have no subject category. Their simulated
# replies are selected by request type and handled by the generic desk.
GENERIC_REPLY_TEMPLATES: dict[str, tuple[str, ...]] = {
    "SUGGESTION": (
        "The {department} has recorded the suggestion and forwarded it to the concerned desk for consideration.",
        "The {department} has reviewed the suggestion and asked the concerned section to assess whether it can be adopted.",
        "The {department} has noted the suggestion and will include it in the next simulated service review.",
    ),
    "ENQUIRY": (
        "The {department} has received the enquiry and will provide the available information after review.",
        "The {department} has checked the enquiry and asked the concerned section to confirm the relevant details.",
        "The {department} has recorded the enquiry and prepared a simulated response for the requester.",
    ),
    "APPRECIATION": (
        "The {department} has acknowledged the appreciation and recorded it for the concerned team.",
        "The {department} has noted the appreciation and shared it with the staff mentioned in the message.",
        "The {department} has recorded the appreciation in the simulated service record.",
    ),
    "REQUIRED_SUPPORT": (
        "The {department} has reviewed the support request and identified the assistance available in this demonstration.",
        "The {department} has asked the concerned section to confirm what support can be provided.",
        "The {department} has recorded the support request and prepared a simulated response.",
    ),
    "WILLING_TO_SUPPORT": (
        "The {department} has recorded the offer of support and will contact the volunteer through the simulated process.",
        "The {department} has noted the offer and asked the concerned section to review how the support can be used.",
        "The {department} has recorded the willingness to support in the simulated service register.",
    ),
}

NON_COMPLAINT_TYPES = tuple(
    value for value in REQUEST_TYPE_VALUES if value not in CATEGORY_REQUIRED_TYPES
)
if set(GENERIC_REPLY_TEMPLATES) != set(NON_COMPLAINT_TYPES):
    raise RuntimeError("Generic reply templates must cover every non-complaint type")


def _select_template(
    reference_id: str,
    templates: tuple[str, ...],
) -> str:
    digest = hashlib.sha256(reference_id.encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big") % len(templates)
    return templates[index]


def select_reply_template(reference_id: str, category: str) -> str:
    """Pick a category reply template deterministically from the reference ID."""

    return _select_template(reference_id, REPLY_TEMPLATES[category])


def select_generic_reply_template(reference_id: str, request_type: str) -> str:
    """Pick a request-type reply template deterministically from the ID."""

    return _select_template(reference_id, GENERIC_REPLY_TEMPLATES[request_type])


def advance_request(
    session: Session,
    request: PortalRequest,
    now: datetime,
) -> bool:
    """Move one request one step forward.

    The conditional ``UPDATE`` re-checks the current status in the database, so
    two callers racing on the same request cannot both advance it. Returns
    ``True`` when a step was taken and ``False`` for a terminal or stale
    request. The caller owns the commit.
    """

    next_status = NEXT_STATUS.get(request.status)
    if next_status is None:
        return False

    next_step_at = now + timedelta(seconds=settings.sim_step_seconds)
    result = session.execute(
        update(PortalRequest)
        .where(
            PortalRequest.id == request.id,
            PortalRequest.status == request.status,
        )
        .values(
            status=next_status,
            updated_at=now,
            next_step_at=next_step_at,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        return False

    request.status = next_status
    request.updated_at = now
    request.next_step_at = next_step_at

    session.add(
        PortalStatusEvent(
            request_id=request.id,
            status=next_status,
            remarks=STEP_REMARKS[next_status],
            actor=ACTOR,
            created_at=now,
        )
    )

    if next_status == STATUS_REPLY_SENT:
        if request.request_type in CATEGORY_REQUIRED_TYPES or request.request_type is None:
            template = select_reply_template(request.reference_id, request.category)
        else:
            template = select_generic_reply_template(
                request.reference_id,
                request.request_type,
            )
        session.add(
            PortalReply(
                request_id=request.id,
                department=request.department,
                message=template.format(department=request.department),
                is_simulated=True,
                created_at=now,
            )
        )

    session.flush()
    return True


def _advance_ids(session: Session, request_ids: list[int], now: datetime, *, due_only: bool) -> int:
    advanced = 0
    for request_id in request_ids:
        # Start each request in its own short transaction and re-check its
        # current state before advancing.
        session.rollback()
        request = session.get(PortalRequest, request_id)
        if request is None or request.status == STATUS_RESOLVED:
            continue
        if due_only:
            if request.next_step_at is None or request.next_step_at > now:
                continue
        if advance_request(session, request, now):
            session.commit()
            advanced += 1
        else:
            session.rollback()
    return advanced


def run_due_requests(session: Session, now: datetime) -> int:
    """Advance every non-terminal request whose next step is due.

    Each request moves at most one step per call. Calling this twice with the
    same ``now`` therefore adds no extra events.
    """

    request_ids = list(
        session.scalars(
            select(PortalRequest.id).where(
                PortalRequest.status != STATUS_RESOLVED,
                PortalRequest.next_step_at.is_not(None),
                PortalRequest.next_step_at <= now,
            )
        ).all()
    )
    return _advance_ids(session, request_ids, now, due_only=True)


def advance_all_requests(session: Session, now: datetime) -> int:
    """Advance every non-terminal request one step, ignoring the due time."""

    request_ids = list(
        session.scalars(
            select(PortalRequest.id).where(PortalRequest.status != STATUS_RESOLVED)
        ).all()
    )
    return _advance_ids(session, request_ids, now, due_only=False)
