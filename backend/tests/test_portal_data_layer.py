"""Tests for the Phase 2 CSS educational portal data layer."""

from __future__ import annotations

import main
from portal.categories import (
    BUREAU_BY_CATEGORY,
    CATEGORIES,
    DEPARTMENT_BY_CATEGORY,
    USER_TYPES,
)
from portal.db import SessionLocal, engine, init_db
from portal.models import (
    PortalReply,
    PortalRequest,
    PortalStatusEvent,
    PortalUser,
    next_reference_id,
)

EXPECTED_TABLES = {
    "portal_users",
    "portal_requests",
    "portal_status_events",
    "portal_replies",
    "portal_sequences",
}


class _FakeThread:
    def __init__(self, target=None, daemon=None, **kwargs):
        self.target = target
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True


def _capture_threads(monkeypatch):
    created: list[_FakeThread] = []

    def factory(*args, **kwargs):
        thread = _FakeThread(*args, **kwargs)
        created.append(thread)
        return thread

    monkeypatch.setattr(main.threading, "Thread", factory)
    return created


def test_init_db_creates_all_tables_and_pragmas():
    from sqlalchemy import inspect

    init_db()
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)

    with engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert str(journal_mode).lower() == "wal"
    assert int(foreign_keys) == 1


def test_row_survives_engine_dispose_and_reconnect():
    init_db()
    with SessionLocal() as db:
        user = PortalUser(
            email="Test.User@Example.COM",
            full_name="Test User",
            user_type="STUDENT",
            password_hash="hashed-password",
        )
        db.add(user)
        db.commit()
        user_id = user.id
        public_ref = user.public_ref

    engine.dispose()

    with SessionLocal() as db:
        loaded = db.get(PortalUser, user_id)
        assert loaded is not None
        assert loaded.email == "test.user@example.com"
        assert loaded.public_ref == public_ref
        assert loaded.is_active is True


def test_request_events_and_replies_survive_reconnect():
    init_db()
    with SessionLocal() as db:
        user = PortalUser(
            email="student@example.com",
            full_name="Student",
            user_type="STUDENT",
            password_hash="hashed-password",
        )
        db.add(user)
        db.flush()
        request = PortalRequest(
            user_id=user.id,
            category="FEE",
            subject="Excess fee charged",
            description="The institute charged more than the approved fee.",
            institution_name="Demo Institute of Technology",
            state="Maharashtra",
        )
        db.add(request)
        db.flush()
        db.add(
            PortalStatusEvent(
                request_id=request.id,
                status="SUBMITTED",
                remarks="Created by test",
                actor="student",
            )
        )
        db.add(
            PortalReply(
                request_id=request.id,
                department="Fee Regulation Cell",
                message="We are reviewing the fee records.",
            )
        )
        db.commit()
        request_id = request.id
        reference_id = request.reference_id

    engine.dispose()

    with SessionLocal() as db:
        loaded = db.get(PortalRequest, request_id)
        assert loaded is not None
        assert loaded.reference_id == reference_id
        assert loaded.department == "Fee Regulation Cell"
        assert len(loaded.status_events) == 1
        assert loaded.status_events[0].status == "SUBMITTED"
        assert len(loaded.replies) == 1
        assert loaded.replies[0].is_simulated is True


def test_startup_with_flag_unset_seeds_and_starts_generator(monkeypatch):
    monkeypatch.delenv("MOCK_CSS_AUTOGEN", raising=False)
    main.tickets.clear()
    created = _capture_threads(monkeypatch)

    main.startup()

    assert len(main.tickets) == 2
    assert len(created) == 1
    assert created[0].target is main.generate_loop
    assert created[0].daemon is True
    assert created[0].started is True


def test_startup_with_autogen_false_skips_seed_and_generator(monkeypatch):
    monkeypatch.setenv("MOCK_CSS_AUTOGEN", "false")
    main.tickets.clear()
    created = _capture_threads(monkeypatch)

    main.startup()

    assert main.tickets == []
    assert created == []


def test_tickets_endpoint_keeps_original_shape(client):
    response = client.get("/tickets")
    assert response.status_code == 200
    body = response.json()
    assert {"simulator", "source_type", "banner", "tickets"}.issubset(body)
    assert body["simulator"] is True
    assert body["source_type"] == "SIMULATOR"
    assert isinstance(body["tickets"], list)


def test_category_routing_and_user_types():
    assert [category.value for category in CATEGORIES] == [
        "FEE",
        "FACULTY",
        "INFRASTRUCTURE",
        "APPROVAL_VIOLATION",
        "ACADEMIC_ADMINISTRATION",
        "GOVERNANCE_MISCONDUCT",
        "RAGGING_DISCRIMINATION",
    ]
    assert BUREAU_BY_CATEGORY == {
        "FEE": "RB",
        "FACULTY": "RB",
        "INFRASTRUCTURE": "RB",
        "APPROVAL_VIOLATION": "RB",
        "ACADEMIC_ADMINISTRATION": "PGRC",
        "GOVERNANCE_MISCONDUCT": "PGRC",
        "RAGGING_DISCRIMINATION": "PGRC",
    }
    assert all(DEPARTMENT_BY_CATEGORY.values())
    assert USER_TYPES == ("STUDENT", "FACULTY", "INSTITUTION_ADMIN", "OTHER")


def test_sequence_allocates_sequential_reference_ids():
    init_db()
    with SessionLocal() as db:
        first = next_reference_id(db, 2026)
        second = next_reference_id(db, 2026)
        db.commit()

    assert first == "CSSD-2026-000001"
    assert second == "CSSD-2026-000002"
