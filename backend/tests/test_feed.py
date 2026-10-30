"""Tests for Phase 5 tracking endpoints and the /tickets pull feed."""

from __future__ import annotations

import re

from sqlalchemy import select

import main
from portal.categories import DEPARTMENT_BY_CATEGORY
from portal.db import SessionLocal
from portal.models import PortalReply, PortalRequest, PortalStatusEvent, PortalUser

PASSWORD = "correct-horse-battery"
DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")

EXPECTED_TICKET_KEYS = {
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
}

ORIGINAL_SIMULATOR_KEYS = {
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
}

EXPECTED_SUMMARY_KEYS = {
    "reference_id",
    "created_at",
    "category",
    "subject",
    "department",
    "status",
    "updated_at",
}

EXPECTED_DETAIL_KEYS = {
    "reference_id",
    "category",
    "subject",
    "description",
    "institution_name",
    "state",
    "status",
    "department",
    "created_at",
    "updated_at",
    "next_step_at",
    "status_events",
    "replies",
}


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client, email: str, full_name: str = "Demo User") -> str:
    registered = client.post(
        "/portal/auth/register",
        json={
            "full_name": full_name,
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


def submission(**overrides):
    payload = {
        "category": "FEE",
        "subject": "Excess fee charged",
        "description": (
            "The institute charged more than the approved fee structure for "
            "the current academic year."
        ),
        "institution_name": "Demo Institute of Technology",
        "state": "Maharashtra",
    }
    payload.update(overrides)
    return payload


def submit(client, token: str, **overrides):
    response = client.post(
        "/portal/requests",
        json=submission(**overrides),
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def tickets(client):
    response = client.get("/tickets")
    assert response.status_code == 200, response.text
    return response.json()


def find_ticket(body, reference_id: str):
    for ticket in body["tickets"]:
        if ticket.get("ticket_no") == reference_id:
            return ticket
    raise AssertionError(f"ticket {reference_id} not found in feed")


def set_status(reference_id: str, status: str) -> None:
    with SessionLocal() as db:
        request = db.scalar(
            select(PortalRequest).where(PortalRequest.reference_id == reference_id)
        )
        assert request is not None
        request.status = status
        db.commit()


def test_submission_appears_in_tickets_with_exact_keys(client):
    token = register_and_login(client, "feed.owner@example.com")
    created = submit(client, token)
    reference_id = created["reference_id"]

    body = tickets(client)
    ticket = find_ticket(body, reference_id)

    assert set(ticket) == EXPECTED_TICKET_KEYS
    assert ticket["ticket_no"] == reference_id
    assert ticket["institution_name"] == "Demo Institute of Technology"
    assert ticket["grievance"] == (
        "Excess fee charged. The institute charged more than the approved fee "
        "structure for the current academic year."
    )
    assert ticket["grievance_category"] == "FEE"
    assert DATE_PATTERN.match(ticket["received_date"])
    assert ticket["current_status"] == "Pending"
    assert ticket["bureau_code"] == "RB"
    assert ticket["language"] == "en"
    assert ticket["state"] == "Maharashtra"
    assert ticket["simulator"] is True
    assert ticket["portal_submission"] is True

    with SessionLocal() as db:
        user = db.scalar(
            select(PortalUser).where(PortalUser.email == "feed.owner@example.com")
        )
        assert user is not None
        assert ticket["complainant_ref"] == user.public_ref


def test_status_changes_update_current_status(client):
    token = register_and_login(client, "status.owner@example.com")
    reference_id = submit(client, token)["reference_id"]

    assert find_ticket(tickets(client), reference_id)["current_status"] == "Pending"

    for status, label in (
        ("UNDER_REVIEW", "Under Process"),
        ("REPLY_SENT", "Under Process"),
        ("RESOLVED", "Disposed"),
    ):
        set_status(reference_id, status)
        assert find_ticket(tickets(client), reference_id)["current_status"] == label


def test_tickets_never_contains_email_or_full_name(client):
    token = register_and_login(
        client,
        "secret.person@example.com",
        full_name="Secret Person",
    )
    submit(client, token)

    response = client.get("/tickets")
    assert response.status_code == 200
    text = response.text

    assert "secret.person@example.com" not in text
    assert "Secret Person" not in text

    for ticket in response.json()["tickets"]:
        assert "email" not in ticket
        assert "full_name" not in ticket
        assert "user_id" not in ticket


def test_existing_simulator_tickets_keep_original_keys(client):
    injected = client.post(
        "/admin/inject",
        json={
            "institution_name": "Simulator Test Institute",
            "grievance": "Original simulator grievance",
            "category": "FEE",
        },
    )
    assert injected.status_code == 200, injected.text
    original = injected.json()["ticket"]

    body = tickets(client)
    simulator_ticket = find_ticket(body, original["ticket_no"])

    assert set(simulator_ticket) == ORIGINAL_SIMULATOR_KEYS
    assert simulator_ticket == original
    assert "portal_submission" not in simulator_ticket


def test_user_cannot_read_another_users_request(client):
    token_a = register_and_login(client, "alice@example.com", full_name="Alice A")
    token_b = register_and_login(client, "bob@example.com", full_name="Bob B")

    reference_id = submit(client, token_a)["reference_id"]

    own = client.get(
        f"/portal/requests/{reference_id}",
        headers=auth_header(token_a),
    )
    assert own.status_code == 200

    other = client.get(
        f"/portal/requests/{reference_id}",
        headers=auth_header(token_b),
    )
    unknown = client.get(
        "/portal/requests/CSSD-2099-999999",
        headers=auth_header(token_b),
    )

    assert other.status_code == 404
    assert unknown.status_code == 404
    assert other.json() == unknown.json() == {"detail": "Request not found"}

    listing = client.get("/portal/requests", headers=auth_header(token_b))
    assert listing.status_code == 200
    assert listing.json()["total"] == 0
    assert listing.json()["items"] == []

    own_listing = client.get("/portal/requests", headers=auth_header(token_a))
    assert own_listing.json()["total"] == 1


def test_list_filters_and_pagination(client):
    token = register_and_login(client, "lister@example.com")
    headers = auth_header(token)

    categories = ["FEE", "FEE", "FEE", "FACULTY", "FACULTY"]
    reference_ids = []
    for index, category in enumerate(categories):
        created = submit(
            client,
            token,
            category=category,
            subject=f"Complaint number {index}",
            description=(
                f"Detailed description for complaint number {index} with "
                "enough characters to be accepted."
            ),
        )
        reference_ids.append(created["reference_id"])

    set_status(reference_ids[0], "UNDER_REVIEW")
    set_status(reference_ids[1], "RESOLVED")
    set_status(reference_ids[3], "REPLY_SENT")

    def fetch(query: str):
        response = client.get(f"/portal/requests?{query}", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    page_one = fetch("page=1&page_size=2")
    page_two = fetch("page=2&page_size=2")
    page_three = fetch("page=3&page_size=2")

    assert page_one["total"] == page_two["total"] == page_three["total"] == 5
    assert [len(page["items"]) for page in (page_one, page_two, page_three)] == [2, 2, 1]

    all_ids = [
        item["reference_id"]
        for page in (page_one, page_two, page_three)
        for item in page["items"]
    ]
    assert len(all_ids) == 5
    assert set(all_ids) == set(reference_ids)
    assert all(set(item) == EXPECTED_SUMMARY_KEYS for item in page_one["items"])

    assert page_one["counts"] == {
        "SUBMITTED": 2,
        "UNDER_REVIEW": 1,
        "REPLY_SENT": 1,
        "RESOLVED": 1,
    }

    under_review = fetch("status=UNDER_REVIEW")
    assert under_review["total"] == 1
    assert under_review["items"][0]["reference_id"] == reference_ids[0]

    faculty = fetch("category=FACULTY")
    assert faculty["total"] == 2
    assert {item["reference_id"] for item in faculty["items"]} == {
        reference_ids[3],
        reference_ids[4],
    }

    fee_resolved = fetch("category=FEE&status=RESOLVED")
    assert fee_resolved["total"] == 1
    assert fee_resolved["items"][0]["reference_id"] == reference_ids[1]

    for invalid in (
        "page=0",
        "page_size=51",
        "status=OTHER",
        "category=OTHER",
    ):
        response = client.get(f"/portal/requests?{invalid}", headers=headers)
        assert response.status_code == 422, (invalid, response.text)


def test_detail_returns_events_oldest_first_and_replies(client):
    token = register_and_login(client, "detail.owner@example.com")
    reference_id = submit(client, token, category="FACULTY")["reference_id"]

    with SessionLocal() as db:
        request = db.scalar(
            select(PortalRequest).where(PortalRequest.reference_id == reference_id)
        )
        assert request is not None
        db.add(
            PortalStatusEvent(
                request_id=request.id,
                status="UNDER_REVIEW",
                remarks="Under review",
                actor="Department (SIMULATED)",
            )
        )
        db.add(
            PortalReply(
                request_id=request.id,
                department=request.department,
                message="We are reviewing your complaint.",
                is_simulated=True,
            )
        )
        db.commit()

    response = client.get(
        f"/portal/requests/{reference_id}",
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) == EXPECTED_DETAIL_KEYS
    assert body["reference_id"] == reference_id
    assert body["category"] == "FACULTY"
    assert body["status"] == "SUBMITTED"
    assert [event["status"] for event in body["status_events"]] == [
        "SUBMITTED",
        "UNDER_REVIEW",
    ]
    assert body["status_events"][0]["remarks"] == "Request registered (simulated)"
    assert body["status_events"][1]["actor"] == "Department (SIMULATED)"

    assert len(body["replies"]) == 1
    assert body["replies"][0]["department"] == DEPARTMENT_BY_CATEGORY["FACULTY"]
    assert body["replies"][0]["is_simulated"] is True

    for forbidden in ("user_id", "public_ref", "email", "full_name", "password_hash"):
        assert forbidden not in body


def test_autogen_false_feed_contains_only_portal_tickets(client):
    assert main.tickets == []

    token = register_and_login(client, "portal.only@example.com")
    reference_id = submit(client, token)["reference_id"]

    body = tickets(client)
    assert set(body) == {"simulator", "source_type", "banner", "tickets"}
    assert len(body["tickets"]) == 1
    assert body["tickets"][0]["ticket_no"] == reference_id
    assert body["tickets"][0]["portal_submission"] is True
    assert all(ticket.get("portal_submission") is True for ticket in body["tickets"])
