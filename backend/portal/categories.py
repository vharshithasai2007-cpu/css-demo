"""Portal categories, department routing and user types.

Bureau routing follows the dashboard convention:
    RB   -> FEE, FACULTY, INFRASTRUCTURE, APPROVAL_VIOLATION
    PGRC -> ACADEMIC_ADMINISTRATION, GOVERNANCE_MISCONDUCT,
            RAGGING_DISCRIMINATION
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortalCategory:
    value: str
    label: str
    description: str
    department: str
    bureau_code: str

    @property
    def simulated_department(self) -> str:
        """Alias used by callers that describe the routing target explicitly."""

        return self.department


CATEGORIES: tuple[PortalCategory, ...] = (
    PortalCategory(
        value="FEE",
        label="Fee",
        description="Excess or irregular fee collection outside the approved structure.",
        department="Fee Regulation Cell",
        bureau_code="RB",
    ),
    PortalCategory(
        value="FACULTY",
        label="Faculty",
        description="Faculty shortage, qualification or teaching-quality concerns.",
        department="Faculty Affairs Cell",
        bureau_code="RB",
    ),
    PortalCategory(
        value="INFRASTRUCTURE",
        label="Infrastructure",
        description="Inadequate laboratories, classrooms, hostel or campus facilities.",
        department="Infrastructure and Facilities Cell",
        bureau_code="RB",
    ),
    PortalCategory(
        value="APPROVAL_VIOLATION",
        label="Approval Violation",
        description="Intake or operations that breach AICTE approval conditions.",
        department="Approval and Compliance Cell",
        bureau_code="RB",
    ),
    PortalCategory(
        value="ACADEMIC_ADMINISTRATION",
        label="Academic Administration",
        description="Examination, records, timetable or academic-process grievances.",
        department="Academic Administration Cell",
        bureau_code="PGRC",
    ),
    PortalCategory(
        value="GOVERNANCE_MISCONDUCT",
        label="Governance and Misconduct",
        description="Institutional governance failures or staff misconduct allegations.",
        department="Governance and Misconduct Cell",
        bureau_code="PGRC",
    ),
    PortalCategory(
        value="RAGGING_DISCRIMINATION",
        label="Ragging and Discrimination",
        description="Ragging, harassment or discrimination complaints requiring urgent action.",
        department="Anti-Ragging and Equal Opportunity Cell",
        bureau_code="PGRC",
    ),
)

CATEGORY_BY_VALUE: dict[str, PortalCategory] = {
    category.value: category for category in CATEGORIES
}
# Alias with a more explicit name for callers that prefer it.
CATEGORIES_BY_VALUE = CATEGORY_BY_VALUE
CATEGORY_VALUES: tuple[str, ...] = tuple(category.value for category in CATEGORIES)
CATEGORY_METADATA: tuple[dict[str, str], ...] = tuple(
    {
        "value": category.value,
        "label": category.label,
        "description": category.description,
        "department": category.department,
        "bureau_code": category.bureau_code,
    }
    for category in CATEGORIES
)
BUREAU_BY_CATEGORY: dict[str, str] = {
    category.value: category.bureau_code for category in CATEGORIES
}
DEPARTMENT_BY_CATEGORY: dict[str, str] = {
    category.value: category.department for category in CATEGORIES
}


def get_category(value: str) -> PortalCategory:
    """Return the category metadata or raise a helpful KeyError."""

    try:
        return CATEGORY_BY_VALUE[value]
    except KeyError as exc:
        raise KeyError(f"Unknown portal category: {value}") from exc


USER_TYPES: tuple[str, ...] = (
    "STUDENT",
    "FACULTY",
    "INSTITUTION_ADMIN",
    "OTHER",
)
USER_TYPE_VALUES = USER_TYPES
