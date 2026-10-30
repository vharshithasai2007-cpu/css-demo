"""Reference-ID allocation for portal requests.

The portal uses ``CSSD-YYYY-NNNNNN`` identifiers. Values come from the
``PortalSequence`` row for the current year and start at ``100000``, so the
first allocated ID is ``CSSD-YYYY-100001``.

The sequence increment, request insert and status-event insert share one
transaction. The unique constraint on ``reference_id`` is the final backstop;
an ``IntegrityError`` rolls the transaction back and retries allocation up to
``MAX_REFERENCE_ATTEMPTS`` times.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import REFERENCE_PREFIX, PortalSequence

REFERENCE_START_VALUE = 100_000
MAX_REFERENCE_ATTEMPTS = 3
REFERENCE_ID_PATTERN = r"^CSSD-\d{4}-\d{6}$"

T = TypeVar("T")


class ReferenceAllocationError(RuntimeError):
    """Raised when a unique reference ID could not be allocated."""


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def allocate_reference_id(db: Session, year: int | None = None) -> str:
    """Increment the year's sequence atomically and return the next ID.

    The increment is a single SQL ``UPDATE`` so concurrent sessions cannot
    read the same value and write it back. The row is created on first use.
    """

    target_year = year or _current_year()

    db.execute(
        sqlite_insert(PortalSequence)
        .values(year=target_year, last_value=REFERENCE_START_VALUE)
        .on_conflict_do_nothing(index_elements=["year"])
    )
    db.execute(
        update(PortalSequence)
        .where(PortalSequence.year == target_year)
        .values(last_value=PortalSequence.last_value + 1)
    )
    value = db.scalar(
        select(PortalSequence.last_value).where(PortalSequence.year == target_year)
    )
    if value is None:
        raise ReferenceAllocationError("Portal sequence row could not be read")

    return f"{REFERENCE_PREFIX}-{target_year}-{int(value):06d}"


def persist_with_reference(
    db: Session,
    factory: Callable[[str], T],
    year: int | None = None,
) -> T:
    """Build, insert and commit an object with a freshly allocated reference ID.

    ``factory`` receives the allocated reference ID and must return the object
    to persist. Any dependent rows it attaches through relationships are
    committed in the same transaction.
    """

    # End any implicit read transaction from the authentication lookup so the
    # write transaction starts from a current SQLite snapshot.
    db.rollback()

    last_error: IntegrityError | None = None
    for _ in range(MAX_REFERENCE_ATTEMPTS):
        try:
            reference_id = allocate_reference_id(db, year)
            instance = factory(reference_id)
            db.add(instance)
            db.flush()
            db.commit()
            db.refresh(instance)
            return instance
        except IntegrityError as exc:
            last_error = exc
            db.rollback()

    raise ReferenceAllocationError(
        "Could not allocate a unique portal reference id"
    ) from last_error
