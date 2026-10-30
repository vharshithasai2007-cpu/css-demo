"""Tests for the Phase 6 simulated department lifecycle.

Every test uses injected ``now`` values; nothing sleeps or depends on wall-clock
time. The background simulation loop is disabled in ``conftest.py`` so the
engine is exercised deterministically, and startup gating is tested explicitly.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

import main
from portal.categories import CATEGORY_VALUES, DEPARTMENT_BY_CATEGORY
from portal.db import SessionLocal
from portal.models import (
    STATUS_REPLY_SENT,
    STATUS_RESOLVED,
    STATUS_SUBMITTED,
    STATUS_UNDER_REVIEW,
    PortalReply,
    PortalRequest,
    PortalStatusEvent,
)
from portal.simulation import (
    ACTOR,
    NEXT_STATUS,
    REPLY_TEMPLATES,
    advance_all_requests,
    advance_request,
    run_due_requests,
    select_reply_template,
)

NOW = datetime(2026, 10, 30, 12, 0, 0)
STEP = timedelta(seconds=45)

PASSWORD = "correct-horse-battery"
EMAIL = "simulation.owner@example.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_request(
    reference_id: str,
    *,
    category: str = "FEE",
    status: str = STATUS_SUBMITTED,
    next_step_at: datetime | None = NOW,
    created_at: datetime = NOW,
) -> PortalRequest:
    return PortalRequest(
        reference_id=reference_id,
        user_id=None,
        category=category,
        subject="Simulated lifecycle complaint",
        description=(
            "A sufficiently detailed description used to exercise the "
            "simulated lifecycle without any real personal data."
        ),
        institution_name="Demo Institute of Technology",
        state="Maharashtra",
        status=status,
        department=DEPARTMENT_BY_CATEGORY[category],
        created_at=created_at,
        updated_at=created_at,
        next_step_at=next_step_at,
    )


def persist_request(reference_id: str, **kwargs) -> int:
    with SessionLocal() as db:
        request = make_request(reference_id, **kwargs)
        db.add(request)
        db.commit()
        return request.id


def load_request(request_id: int) -> PortalRequest:
    with SessionLocal() as db:
        request = db.get(PortalRequest, request_id)
        assert request is not None
        db.expunge(request)
        return request


def event_statuses(request_id: int) -> list[str]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(PortalStatusEvent)
            .where(PortalStatusEvent.request_id == request_id)
            .order_by(PortalStatusEvent.created_at.asc(), PortalStatusEvent.id.asc())
        ).all()
        return [row.status for row in rows]


def reply_count(request_id: int) -> int:
    with SessionLocal() as db:
        rows = db.scalars(
            select(PortalReply).where(PortalReply.request_id == request_id)
        ).all()
        return len(rows)


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client, email: str = EMAIL) -> str:
    registered = client.post(
        "/portal/auth/register",
        json={
            "full_name": "Simulation Owner",
            "email": email,
            "password": PASSWORD,
            "user_type": "STUDENT",
            "institution_name": "Demo Institute of Technology",
        },
    )
    assert registered.status_code == 201, registered.text

    logged_in = client.post(
        "/portal/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert logged_in.status_code == 200, logged_in.text
    return logged_in.json()["access_token"]


def submit(client, token: str, category: str = "FEE") -> str:
    response = client.post(
        "/portal/requests",
        json={
            "category": category,
            "subject": "Excess fee charged",
            "description": (
                "The institute charged more than the approved fee structure "
                "for the current academic year."
            ),
            "institution_name": "Demo Institute of Technology",
            "state": "Maharashtra",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["reference_id"]


def detail(client, token: str, reference_id: str) -> dict:
    response = client.get(
        f"/portal/requests/{reference_id}",
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_full_lifecycle_order_and_reply_once(client, monkeypatch):
    monkeypatch.delenv("CSS_PORTAL_ADMIN_KEY", raising=False)
    token = register_and_login(client)
    reference_id = submit(client, token)

    expected = [STATUS_SUBMITTED, STATUS_UNDER_REVIEW, STATUS_REPLY_SENT, STATUS_RESOLVED]

    body = detail(client, token, reference_id)
    assert body["status"] == STATUS_SUBMITTED
    assert [event["status"] for event in body["status_events"]] == [STATUS_SUBMITTED]
    assert body["replies"] == []

    for index, status in enumerate(expected[1:], start=1):
        response = client.post(f"/admin/portal/advance/{reference_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["advanced"] is True
        assert payload["status"] == status
        assert payload["reference_id"] == reference_id
        assert payload["simulator"] is True

        body = detail(client, token, reference_id)
        assert body["status"] == status
        assert [event["status"] for event in body["status_events"]] == expected[: index + 1]

        # The reply appears exactly when the request enters REPLY_SENT.
        assert len(body["replies"]) == (1 if index >= 2 else 0)

    # RESOLVED is terminal: another call changes nothing and adds no reply.
    terminal = client.post(f"/admin/portal/advance/{reference_id}")
    assert terminal.status_code == 200, terminal.text
    assert terminal.json()["advanced"] is False
    assert terminal.json()["status"] == STATUS_RESOLVED

    body = detail(client, token, reference_id)
    assert [event["status"] for event in body["status_events"]] == expected
    assert len(body["replies"]) == 1
    assert body["replies"][0]["is_simulated"] is True


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (STATUS_SUBMITTED, STATUS_UNDER_REVIEW),
        (STATUS_UNDER_REVIEW, STATUS_REPLY_SENT),
        (STATUS_REPLY_SENT, STATUS_RESOLVED),
    ],
)
def test_advance_request_follows_forward_map(status, expected):
    request_id = persist_request("CSSD-2026-900001", status=status)

    with SessionLocal() as db:
        request = db.get(PortalRequest, request_id)
        assert request is not None
        assert advance_request(db, request, NOW) is True
        db.commit()
        assert request.status == expected

    assert event_statuses(request_id) == [expected]
    assert reply_count(request_id) == (1 if expected == STATUS_REPLY_SENT else 0)


def test_terminal_request_never_advances():
    request_id = persist_request(
        "CSSD-2026-900002",
        status=STATUS_RESOLVED,
        next_step_at=NOW - STEP,
    )

    with SessionLocal() as db:
        request = db.get(PortalRequest, request_id)
        assert request is not None
        assert advance_request(db, request, NOW) is False
        db.commit()
        assert request.status == STATUS_RESOLVED

        assert run_due_requests(db, NOW + STEP) == 0
        assert advance_all_requests(db, NOW + STEP) == 0

    assert event_statuses(request_id) == []
    assert reply_count(request_id) == 0


def test_next_status_map_is_forward_only():
    assert NEXT_STATUS == {
        STATUS_SUBMITTED: STATUS_UNDER_REVIEW,
        STATUS_UNDER_REVIEW: STATUS_REPLY_SENT,
        STATUS_REPLY_SENT: STATUS_RESOLVED,
        STATUS_RESOLVED: None,
    }


def test_stale_session_cannot_advance_the_same_request_twice():
    request_id = persist_request("CSSD-2026-900003")

    with SessionLocal() as first, SessionLocal() as second:
        first_request = first.get(PortalRequest, request_id)
        second_request = second.get(PortalRequest, request_id)
        assert first_request is not None and second_request is not None

        assert advance_request(first, first_request, NOW) is True
        first.commit()

        # ``second_request`` still believes the status is SUBMITTED. The
        # conditional UPDATE must reject it because the row has moved on.
        assert advance_request(second, second_request, NOW) is False
        second.rollback()

    assert event_statuses(request_id) == [STATUS_UNDER_REVIEW]


# ---------------------------------------------------------------------------
# Due-time processing
# ---------------------------------------------------------------------------


def test_run_due_requests_advances_only_due_and_is_idempotent():
    due_id = persist_request("CSSD-2026-910001", next_step_at=NOW - STEP)
    future_id = persist_request("CSSD-2026-910002", next_step_at=NOW + 1000 * STEP)
    resolved_id = persist_request(
        "CSSD-2026-910003",
        status=STATUS_RESOLVED,
        next_step_at=NOW - STEP,
    )

    with SessionLocal() as db:
        assert run_due_requests(db, NOW) == 1

        assert load_request(due_id).status == STATUS_UNDER_REVIEW
        assert load_request(future_id).status == STATUS_SUBMITTED
        assert load_request(resolved_id).status == STATUS_RESOLVED

        events_after_first = event_statuses(due_id)

        # Same ``now`` again: the due request's next step is in the future, so
        # nothing is advanced and no duplicate events are written.
        assert run_due_requests(db, NOW) == 0
        assert event_statuses(due_id) == events_after_first

        # After the step interval the same request advances exactly one more
        # step; the future request is still not due.
        assert run_due_requests(db, NOW + STEP + timedelta(seconds=1)) == 1
        assert load_request(due_id).status == STATUS_REPLY_SENT
        assert load_request(future_id).status == STATUS_SUBMITTED
        assert event_statuses(due_id) == [STATUS_UNDER_REVIEW, STATUS_REPLY_SENT]

    assert reply_count(due_id) == 1
    assert reply_count(future_id) == 0
    assert reply_count(resolved_id) == 0


def test_advance_all_ignores_due_time_and_skips_terminal():
    submitted_id = persist_request("CSSD-2026-920001", next_step_at=NOW + 1000 * STEP)
    review_id = persist_request(
        "CSSD-2026-920002",
        status=STATUS_UNDER_REVIEW,
        next_step_at=NOW + 1000 * STEP,
    )
    resolved_id = persist_request(
        "CSSD-2026-920003",
        status=STATUS_RESOLVED,
        next_step_at=NOW - STEP,
    )

    with SessionLocal() as db:
        assert advance_all_requests(db, NOW) == 2

    assert load_request(submitted_id).status == STATUS_UNDER_REVIEW
    assert load_request(review_id).status == STATUS_REPLY_SENT
    assert load_request(resolved_id).status == STATUS_RESOLVED

    assert event_statuses(submitted_id) == [STATUS_UNDER_REVIEW]
    assert event_statuses(review_id) == [STATUS_REPLY_SENT]
    assert event_statuses(resolved_id) == []
    assert reply_count(review_id) == 1


def test_advance_all_endpoint_advances_every_non_terminal_request(client, monkeypatch):
    monkeypatch.delenv("CSS_PORTAL_ADMIN_KEY", raising=False)
    token = register_and_login(client)
    resolved_ref = submit(client, token, category="FEE")
    pending_ref = submit(client, token, category="FACULTY")

    for _ in range(3):
        assert client.post(f"/admin/portal/advance/{resolved_ref}").status_code == 200
    assert detail(client, token, resolved_ref)["status"] == STATUS_RESOLVED

    response = client.post("/admin/portal/advance-all")
    assert response.status_code == 200, response.text
    assert response.json() == {"simulator": True, "advanced": 1}

    assert detail(client, token, pending_ref)["status"] == STATUS_UNDER_REVIEW
    resolved = detail(client, token, resolved_ref)
    assert resolved["status"] == STATUS_RESOLVED
    assert len(resolved["status_events"]) == 4
    assert len(resolved["replies"]) == 1


# ---------------------------------------------------------------------------
# Reply templates
# ---------------------------------------------------------------------------


def test_every_category_has_three_templates_and_no_other_category():
    assert set(REPLY_TEMPLATES) == set(CATEGORY_VALUES)
    assert "OTHER" not in REPLY_TEMPLATES
    assert all(len(templates) == 3 for templates in REPLY_TEMPLATES.values())


def test_reply_template_selection_is_deterministic():
    reference_id = "CSSD-2026-930001"
    digest = hashlib.sha256(reference_id.encode("utf-8")).digest()
    expected_index = int.from_bytes(digest[:8], "big") % 3

    for category in CATEGORY_VALUES:
        first = select_reply_template(reference_id, category)
        second = select_reply_template(reference_id, category)

        assert first == second
        assert first == REPLY_TEMPLATES[category][expected_index]
        assert first in REPLY_TEMPLATES[category]
        assert "{department}" in first


def test_reply_uses_the_request_department_and_is_marked_simulated():
    request_id = persist_request(
        "CSSD-2026-940001",
        category="RAGGING_DISCRIMINATION",
        status=STATUS_UNDER_REVIEW,
    )

    with SessionLocal() as db:
        request = db.get(PortalRequest, request_id)
        assert request is not None
        assert advance_request(db, request, NOW) is True
        db.commit()
        department = request.department

    with SessionLocal() as db:
        replies = db.scalars(
            select(PortalReply).where(PortalReply.request_id == request_id)
        ).all()

    assert len(replies) == 1
    reply = replies[0]
    assert reply.department == department
    assert reply.is_simulated is True
    assert "{department}" not in reply.message
    assert department in reply.message
    assert reply.message in {
        template.format(department=department)
        for template in REPLY_TEMPLATES["RAGGING_DISCRIMINATION"]
    }


# ---------------------------------------------------------------------------
# Demo admin controls
# ---------------------------------------------------------------------------


def test_admin_key_is_enforced_only_when_configured(client, monkeypatch):
    monkeypatch.setenv("CSS_PORTAL_ADMIN_KEY", "demo-secret")

    missing = client.post("/admin/portal/advance-all")
    wrong = client.post(
        "/admin/portal/advance-all",
        headers={"X-Demo-Admin-Key": "wrong"},
    )
    accepted = client.post(
        "/admin/portal/advance-all",
        headers={"X-Demo-Admin-Key": "demo-secret"},
    )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert missing.json() == wrong.json() == {"detail": "Invalid demo admin key"}
    assert accepted.status_code == 200
    assert accepted.json() == {"simulator": True, "advanced": 0}

    unknown = client.post(
        "/admin/portal/advance/CSSD-2099-999999",
        headers={"X-Demo-Admin-Key": "demo-secret"},
    )
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "Request not found"}


def test_admin_key_is_not_required_when_unset(client, monkeypatch):
    monkeypatch.delenv("CSS_PORTAL_ADMIN_KEY", raising=False)

    response = client.post("/admin/portal/advance-all")
    assert response.status_code == 200
    assert response.json() == {"simulator": True, "advanced": 0}


# ---------------------------------------------------------------------------
# Startup gating
# ---------------------------------------------------------------------------


class _FakeThread:
    def __init__(self, target=None, daemon=None, **_kwargs):
        self.target = target
        self.daemon = daemon

    def start(self) -> None:
        return None


def _capture_startup_threads(monkeypatch) -> list[_FakeThread]:
    started: list[_FakeThread] = []

    def factory(target=None, daemon=None, **kwargs):
        thread = _FakeThread(target=target, daemon=daemon, **kwargs)
        started.append(thread)
        return thread

    monkeypatch.setattr(main.threading, "Thread", factory)
    monkeypatch.setenv("MOCK_CSS_AUTOGEN", "false")
    return started


def test_startup_starts_simulation_thread_when_enabled(monkeypatch):
    monkeypatch.setenv("CSS_PORTAL_SIM_ENABLED", "true")
    started = _capture_startup_threads(monkeypatch)

    main.startup()

    assert [thread.target for thread in started] == [main.simulation_loop]
    assert all(thread.daemon is True for thread in started)


def test_startup_skips_simulation_thread_when_disabled(monkeypatch):
    monkeypatch.setenv("CSS_PORTAL_SIM_ENABLED", "false")
    started = _capture_startup_threads(monkeypatch)

    main.startup()

    assert started == []


def test_simulation_enabled_flag_parsing(monkeypatch):
    monkeypatch.delenv("CSS_PORTAL_SIM_ENABLED", raising=False)
    assert main.simulation_enabled() is True

    monkeypatch.setenv("CSS_PORTAL_SIM_ENABLED", "FALSE")
    assert main.simulation_enabled() is False

    monkeypatch.setenv("CSS_PORTAL_SIM_ENABLED", "true")
    assert main.simulation_enabled() is True


# ---------------------------------------------------------------------------
# Feed integration
# ---------------------------------------------------------------------------


def test_simulated_statuses_update_the_pull_feed(client, monkeypatch):
    monkeypatch.delenv("CSS_PORTAL_ADMIN_KEY", raising=False)
    token = register_and_login(client)
    reference_id = submit(client, token)

    def ticket_status() -> str:
        body = client.get("/tickets").json()
        ticket = next(
            item for item in body["tickets"] if item["ticket_no"] == reference_id
        )
        return ticket["current_status"]

    assert ticket_status() == "Pending"

    client.post(f"/admin/portal/advance/{reference_id}")
    assert ticket_status() == "Under Process"

    client.post(f"/admin/portal/advance/{reference_id}")
    assert ticket_status() == "Under Process"

    client.post(f"/admin/portal/advance/{reference_id}")
    assert ticket_status() == "Disposed"

    # Terminal requests stay disposed no matter how often the simulator runs.
    client.post(f"/admin/portal/advance/{reference_id}")
    assert ticket_status() == "Disposed"
