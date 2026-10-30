"""Map portal requests to the dashboard's CSS ticket shape.

The dashboard's ``backend/config/css_mapping.yaml`` reads these keys:
``ticket_no``, ``institution_name``, ``grievance``, ``grievance_category``,
``received_date``, ``current_status``, ``bureau_code``, ``language`` and
``complainant_ref``. The feed adds ``state``, ``simulator`` and
``portal_submission`` so portal tickets remain distinguishable from the
simulator's own tickets.
"""

from __future__ import annotations

from typing import Any

from .categories import BUREAU_BY_CATEGORY
from .models import (
    STATUS_REPLY_SENT,
    STATUS_RESOLVED,
    STATUS_SUBMITTED,
    STATUS_UNDER_REVIEW,
    PortalRequest,
)
from .request_types import CATEGORY_REQUIRED_TYPES

STATUS_LABELS: dict[str, str] = {
    STATUS_SUBMITTED: "Pending",
    STATUS_UNDER_REVIEW: "Under Process",
    STATUS_REPLY_SENT: "Under Process",
    STATUS_RESOLVED: "Disposed",
}

TICKET_KEYS: tuple[str, ...] = (
    "ticket_no",
    "institution_name",
    "grievance",
    "grievance_category",
    "received_date",
    "current_status",
    "bureau_code",
    "language",
    "complainant_ref",
    "state",
    "simulator",
    "portal_submission",
)


def is_feed_eligible(request: PortalRequest) -> bool:
    """Return whether a request belongs in the complaint-shaped pull feed.

    Legacy rows (``request_type`` is ``NULL``) are included when they carry a
    category. New non-complaint request types have no category and stay
    portal-only.
    """

    if request.category is None:
        return False
    return (
        request.request_type is None
        or request.request_type in CATEGORY_REQUIRED_TYPES
    )


def feed_status(status: str) -> str:
    """Map an internal portal status to the dashboard's display label."""

    return STATUS_LABELS[status]


def request_to_ticket(request: PortalRequest) -> dict[str, Any]:
    """Build exactly one dashboard-shaped ticket for a portal request."""

    return {
        "ticket_no": request.reference_id,
        "institution_name": request.institution_name,
        "grievance": f"{request.subject}. {request.description}",
        "grievance_category": request.category,
        "received_date": request.created_at.strftime("%d/%m/%Y"),
        "current_status": feed_status(request.status),
        "bureau_code": BUREAU_BY_CATEGORY[request.category],
        "language": "en",
        "complainant_ref": request.user.public_ref if request.user else "",
        "state": request.state,
        "simulator": True,
        "portal_submission": True,
    }
