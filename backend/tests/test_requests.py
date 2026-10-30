"""Tests for Phase 4 portal request submission and metadata."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import select

import main
from portal.categories import DEPARTMENT_BY_CATEGORY
from portal.db import SessionLocal
from portal.models import PortalRequest

CATEGORIES = [
    "FEE",
    "FACULTY",
    "INFRASTRUCTURE",
    "APPROVAL_VIOLATION",
    "ACADEMIC_ADMINISTRATION",
    "GOVERNANCE_MISCONDUCT",
    "RAGGING_DISCRIMINATION",
]
ID_PATTERN = re.compile(r"^CSSD-\d{4}-\d{6}$")

EMAIL = "submitter@example.com"
PASSWORD = "correct-horse-battery"


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client) -> str:
    registered = client.post(
        "/portal/auth/register",
        json={
            "full_name": "Demo Submitter",
            "email": EMAIL,
            "password": PASSWORD,
            "user_type": "STUDENT",
            "institution_name": "Demo Institute of Technology",
        },
    )
    assert registered.status_code == 201, registered.text

    logged_in = client.post(
        "/portal/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
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


def test_each_category_returns_unique_reference_id(client):
    token = register_and_login(client)
    headers = auth_header(token)

    reference_ids: list[str] = []
    for category in CATEGORIES:
        response = client.post(
            "/portal/requests",
            json=submission(category=category),
            headers=headers,
        )
        assert response.status_code == 201, response.text
        body = response.json()

        assert set(body) == {"reference_id", "status", "category", "created_at"}
        assert body["status"] == "SUBMITTED"
        assert body["category"] == category
        assert ID_PATTERN.match(body["reference_id"])
        reference_ids.append(body["reference_id"])

    assert len(set(reference_ids)) == len(CATEGORIES)
    suffixes = sorted(int(reference_id.split("-")[-1]) for reference_id in reference_ids)
    assert suffixes == list(range(100001, 100008))


def test_other_and_unknown_category_are_422(client):
    token = register_and_login(client)
    headers = auth_header(token)

    for category in ("OTHER", "NOT_A_CATEGORY", "fee"):
        response = client.post(
            "/portal/requests",
            json=submission(category=category),
            headers=headers,
        )
        assert response.status_code == 422, (category, response.text)


def test_short_and_overlong_fields_are_422(client):
    token = register_and_login(client)
    headers = auth_header(token)

    invalid_payloads = [
        submission(subject="abcd"),
        submission(subject="x" * 151),
        submission(description="x" * 19),
        submission(description="x" * 4001),
        submission(institution_name="xy"),
        submission(institution_name="x" * 201),
        submission(state="x" * 81),
        submission(subject="     "),
        submission(description="\x00" * 40),
    ]

    for payload in invalid_payloads:
        response = client.post("/portal/requests", json=payload, headers=headers)
        assert response.status_code == 422, response.text


def test_unauthenticated_submission_is_401(client):
    response = client.post("/portal/requests", json=submission())
    assert response.status_code == 401


def test_control_characters_are_stripped_and_text_is_trimmed(client):
    token = register_and_login(client)
    headers = auth_header(token)

    response = client.post(
        "/portal/requests",
        json=submission(
            subject="  \x00Excess fee\x07 charged  ",
            description=(
                "\x01 The institute charged more than the approved fee "
                "structure for the current academic year. \x02"
            ),
            institution_name="  Demo \x03Institute of Technology  ",
            state="  Maharashtra  ",
        ),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    reference_id = response.json()["reference_id"]

    with SessionLocal() as db:
        request = db.scalar(
            select(PortalRequest).where(PortalRequest.reference_id == reference_id)
        )
        assert request is not None
        assert request.subject == "Excess fee charged"
        assert request.institution_name == "Demo Institute of Technology"
        assert request.state == "Maharashtra"
        assert "\x00" not in request.description
        assert request.description.startswith(
            "The institute charged more than the approved fee structure"
        )


def test_twenty_concurrent_submissions_have_distinct_ids(client):
    token = register_and_login(client)
    headers = auth_header(token)

    def submit(index: int):
        thread_client = TestClient(main.app)
        try:
            return thread_client.post(
                "/portal/requests",
                json=submission(
                    subject=f"Concurrent fee complaint {index}",
                    description=(
                        f"Concurrent submission number {index} reports fee "
                        "collection above the approved structure."
                    ),
                ),
                headers=headers,
            )
        finally:
            thread_client.close()

    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(submit, range(20)))

    assert [response.status_code for response in responses] == [201] * 20
    reference_ids = [response.json()["reference_id"] for response in responses]

    assert len(reference_ids) == 20
    assert len(set(reference_ids)) == 20
    assert all(ID_PATTERN.match(reference_id) for reference_id in reference_ids)
    suffixes = sorted(int(reference_id.split("-")[-1]) for reference_id in reference_ids)
    assert suffixes == list(range(100001, 100021))


def test_first_status_event_exists(client):
    token = register_and_login(client)
    headers = auth_header(token)

    response = client.post(
        "/portal/requests",
        json=submission(category="RAGGING_DISCRIMINATION"),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    reference_id = response.json()["reference_id"]

    with SessionLocal() as db:
        request = db.scalar(
            select(PortalRequest).where(PortalRequest.reference_id == reference_id)
        )
        assert request is not None
        assert request.department == DEPARTMENT_BY_CATEGORY["RAGGING_DISCRIMINATION"]
        assert request.next_step_at is not None
        assert len(request.status_events) == 1

        event = request.status_events[0]
        assert event.status == "SUBMITTED"
        assert event.remarks == "Request registered (simulated)"
        assert event.actor == "System (SIMULATED)"


def test_meta_lists_seven_categories_and_no_other(client):
    response = client.get("/portal/meta")
    assert response.status_code == 200, response.text
    body = response.json()

    categories = body["categories"]
    assert [category["value"] for category in categories] == CATEGORIES
    assert "OTHER" not in [category["value"] for category in categories]
    assert all(
        set(category) == {"value", "label", "description", "department"}
        for category in categories
    )
    assert all(category["department"] for category in categories)

    assert body["user_types"] == [
        "STUDENT",
        "FACULTY",
        "INSTITUTION_ADMIN",
        "OTHER",
    ]

    institutions = body["institutions"]
    assert len(institutions) == 301
    assert all(set(item) == {"name", "state"} for item in institutions)
    # The dashboard seed itself contains exact duplicate name/state pairs.
    assert len({(item["name"], item["state"]) for item in institutions}) == 255
