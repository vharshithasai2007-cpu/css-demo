"""Stakeholder request types for the CSS educational portal.

These values describe *why* a stakeholder is contacting the Centralized Support
System. They are deliberately separate from :mod:`portal.categories`, which
classifies the subject matter of complaint and grievance cases.

Only ``COMPLAINT`` and ``GRIEVANCE`` require a technical subject category.
The remaining types are recorded without a category and are handled by the
generic simulated desk. No mapping between the two concepts is implied.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortalRequestType:
    value: str
    label: str
    description: str
    requires_category: bool


REQUEST_TYPES: tuple[PortalRequestType, ...] = (
    PortalRequestType(
        value="SUGGESTION",
        label="Suggestion",
        description="A proposal to improve a service, process or facility.",
        requires_category=False,
    ),
    PortalRequestType(
        value="ENQUIRY",
        label="Enquiry",
        description="A request for information or clarification.",
        requires_category=False,
    ),
    PortalRequestType(
        value="GRIEVANCE",
        label="Grievance",
        description=(
            "A formal complaint about a service deficiency that requires "
            "redress."
        ),
        requires_category=True,
    ),
    PortalRequestType(
        value="COMPLAINT",
        label="Complaint",
        description=(
            "A report of a specific violation or misconduct requiring action."
        ),
        requires_category=True,
    ),
    PortalRequestType(
        value="APPRECIATION",
        label="Appreciation",
        description="A note of thanks or recognition for a service or person.",
        requires_category=False,
    ),
    PortalRequestType(
        value="REQUIRED_SUPPORT",
        label="Required Support",
        description="A request for assistance or support from the system.",
        requires_category=False,
    ),
    PortalRequestType(
        value="WILLING_TO_SUPPORT",
        label="Willing to Support",
        description=(
            "An offer to contribute time, expertise or resources to the "
            "system."
        ),
        requires_category=False,
    ),
)

REQUEST_TYPE_BY_VALUE: dict[str, PortalRequestType] = {
    request_type.value: request_type for request_type in REQUEST_TYPES
}
REQUEST_TYPE_VALUES: tuple[str, ...] = tuple(
    request_type.value for request_type in REQUEST_TYPES
)
REQUEST_TYPE_METADATA: tuple[dict[str, object], ...] = tuple(
    {
        "value": request_type.value,
        "label": request_type.label,
        "description": request_type.description,
        "requires_category": request_type.requires_category,
    }
    for request_type in REQUEST_TYPES
)

# These two stakeholder types are complaint cases and must carry one of the
# seven technical subject categories. Every other type must not carry one.
CATEGORY_REQUIRED_TYPES: frozenset[str] = frozenset({"COMPLAINT", "GRIEVANCE"})

# Handling desk for request types that do not have a subject category.
GENERIC_DESK = "Centralized Support System Desk (SIMULATED)"

# Display label for rows created before request types were recorded.
LEGACY_REQUEST_TYPE_LABEL = "Not recorded (legacy)"


def get_request_type(value: str) -> PortalRequestType:
    """Return the request-type metadata or raise a helpful ``KeyError``."""

    try:
        return REQUEST_TYPE_BY_VALUE[value]
    except KeyError as exc:
        raise KeyError(f"Unknown portal request type: {value}") from exc
