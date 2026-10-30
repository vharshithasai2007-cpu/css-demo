"""SQLAlchemy models for the CSS educational portal data layer."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, validates

from .categories import CATEGORY_VALUES, DEPARTMENT_BY_CATEGORY, USER_TYPES
from .db import Base
from .request_types import (
    CATEGORY_REQUIRED_TYPES,
    GENERIC_DESK,
    REQUEST_TYPE_VALUES,
)

STATUS_SUBMITTED = "SUBMITTED"
STATUS_UNDER_REVIEW = "UNDER_REVIEW"
STATUS_REPLY_SENT = "REPLY_SENT"
STATUS_RESOLVED = "RESOLVED"
PORTAL_STATUSES: tuple[str, ...] = (
    STATUS_SUBMITTED,
    STATUS_UNDER_REVIEW,
    STATUS_REPLY_SENT,
    STATUS_RESOLVED,
)

REFERENCE_PREFIX = "CSSD"
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def utcnow() -> datetime:
    """Naive UTC timestamp, matching the rest of the demo services."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_public_ref() -> str:
    """Opaque, URL-safe public identifier for a portal user."""

    return secrets.token_urlsafe(18)


def generate_reference_id(year: int | None = None) -> str:
    """Generate a random CSSD-YYYY-XXXXXX reference ID.

    Sequential IDs can be allocated with :func:`next_reference_id`; this
    default keeps direct model creation convenient and collision-resistant.
    """

    target_year = year or datetime.now(timezone.utc).year
    suffix = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(6))
    return f"{REFERENCE_PREFIX}-{target_year}-{suffix}"


def _default_reference_id() -> str:
    """Zero-argument wrapper used as the SQLAlchemy column default."""

    return generate_reference_id()


_CATEGORY_SQL = ", ".join(f"'{value}'" for value in CATEGORY_VALUES)
_STATUS_SQL = ", ".join(f"'{value}'" for value in PORTAL_STATUSES)
_USER_TYPE_SQL = ", ".join(f"'{value}'" for value in USER_TYPES)
_REQUEST_TYPE_SQL = ", ".join(f"'{value}'" for value in REQUEST_TYPE_VALUES)


class PortalUser(Base):
    __tablename__ = "portal_users"
    __table_args__ = (
        CheckConstraint(f"user_type IN ({_USER_TYPE_SQL})", name="ck_portal_users_user_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    user_type: Mapped[str] = mapped_column(String(32), nullable=False, default="STUDENT")
    institution_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    public_ref: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        default=generate_public_ref,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    requests: Mapped[list["PortalRequest"]] = relationship(back_populates="user")

    @validates("email")
    def _normalize_email(self, _key: str, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else value

    @validates("user_type")
    def _normalize_user_type(self, _key: str, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in USER_TYPES:
            raise ValueError(f"user_type must be one of {USER_TYPES}")
        return normalized


class PortalRequest(Base):
    __tablename__ = "portal_requests"
    __table_args__ = (
        UniqueConstraint("reference_id", name="uq_portal_requests_reference_id"),
        CheckConstraint(
            f"category IS NULL OR category IN ({_CATEGORY_SQL})",
            name="ck_portal_requests_category",
        ),
        CheckConstraint(
            f"request_type IS NULL OR request_type IN ({_REQUEST_TYPE_SQL})",
            name="ck_portal_requests_request_type",
        ),
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="ck_portal_requests_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        default=_default_reference_id,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(48), nullable=True)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    institution_name: Mapped[str] = mapped_column(String(240), nullable=False)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=STATUS_SUBMITTED)
    department: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    next_step_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[PortalUser | None] = relationship(back_populates="requests")
    status_events: Mapped[list["PortalStatusEvent"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="PortalStatusEvent.created_at",
    )
    replies: Mapped[list["PortalReply"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="PortalReply.created_at",
    )

    @validates("request_type")
    def _validate_request_type(self, _key: str, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in REQUEST_TYPE_VALUES:
            raise ValueError(f"request_type must be one of {REQUEST_TYPE_VALUES}")
        return normalized

    @validates("category")
    def _validate_category(self, _key: str, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in CATEGORY_VALUES:
            raise ValueError(f"category must be one of {CATEGORY_VALUES}")
        return normalized

    @validates("status")
    def _validate_status(self, _key: str, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in PORTAL_STATUSES:
            raise ValueError(f"status must be one of {PORTAL_STATUSES}")
        return normalized


@event.listens_for(PortalRequest, "before_insert")
def _default_department(_mapper, _connection, target: PortalRequest) -> None:
    """Route a request to its simulated department when none was supplied."""

    if target.request_type is not None:
        requires_category = target.request_type in CATEGORY_REQUIRED_TYPES
        if requires_category and target.category is None:
            raise ValueError(
                f"{target.request_type} requests require a subject category"
            )
        if not requires_category and target.category is not None:
            raise ValueError(
                f"{target.request_type} requests must not have a subject category"
            )

    if not target.department:
        if target.category is None:
            target.department = GENERIC_DESK
        else:
            target.department = DEPARTMENT_BY_CATEGORY.get(
                target.category,
                "Unassigned",
            )


class PortalStatusEvent(Base):
    __tablename__ = "portal_status_events"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="ck_portal_status_events_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("portal_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    request: Mapped[PortalRequest] = relationship(back_populates="status_events")

    @validates("status")
    def _validate_status(self, _key: str, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in PORTAL_STATUSES:
            raise ValueError(f"status must be one of {PORTAL_STATUSES}")
        return normalized


class PortalReply(Base):
    __tablename__ = "portal_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("portal_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    request: Mapped[PortalRequest] = relationship(back_populates="replies")


class PortalSequence(Base):
    __tablename__ = "portal_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def next_reference_id(db: Session, year: int | None = None) -> str:
    """Allocate the next sequential CSSD-YYYY-NNNNNN reference ID."""

    target_year = year or datetime.now(timezone.utc).year
    sequence = db.get(PortalSequence, target_year)
    if sequence is None:
        sequence = PortalSequence(year=target_year, last_value=0)
        db.add(sequence)
        db.flush()
    sequence.last_value += 1
    db.flush()
    return f"{REFERENCE_PREFIX}-{target_year}-{sequence.last_value:06d}"
