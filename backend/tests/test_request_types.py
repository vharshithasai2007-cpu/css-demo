"""Tests for stakeholder request types and the additive v2 request API.

These tests cover the reconciliation between stakeholder request types and the
technical ``CaseCategory`` values. They do not replace or weaken the existing
v1 contract tests.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

import main
from portal.categories import CATEGORY_VALUES, DEPARTMENT_BY_CATEGORY
from portal.db import SessionLocal, migrate_portal_requests
from portal.models import PortalRequest
from portal.request_types import (
    CATEGORY_REQUIRED_TYPES,
    GENERIC_DESK,
    LEGACY_REQUEST_TYPE_LABEL,
    REQUEST_TYPES,
    REQUEST_TYPE_VALUES,
)
from portal.simulation import GENERIC_REPLY_TEMPLATES

PASSWORD = "correct-horse-battery"
ID_PATTERN = re.compile(r"^CSSD-\d{4}-\d{6}$")

CREATED_V2_KEYS = {
    "reference_id",
    "request_type",
    "category",
    "department",
    "status",
    "created_at",
}

SUMMARY_V2_KEYS = {
    "reference_id",
    "request_type",
    "category",
    "subject",
    "department",
    "status",
    "created_at",
    "updated_at",
}

DETAIL_V2_KEYS = {
    "reference_id",
    "request_type",
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

REQUEST_TYPE_CASES = [
    ("SUGGESTION", None),
    ("ENQUIRY", None),
    ("GRIEVANCE", "FEE"),
    ("COMPLAINT", "FACULTY"),
    ("APPRECIATION", None),
    ("REQUIRED_SUPPORT", None),
    ("WILLING_TO_SUPPORT", None),
]


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


def submit_v2(client, token: str, request_type: str, category: str | None = None, **overrides):
    payload = submission(request_type=request_type, **overrides)
    if category is not None:
        payload["category"] = category
    response = client.post(
        "/portal/v2/requests",
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Request-type catalogue
# ---------------------------------------------------------------------------


def test_request_types_are_separate_from_case_categories():
    assert REQUEST_TYPE_VALUES == (
        "SUGGESTION",
        "ENQUIRY",
        "GRIEVANCE",
        "COMPLAINT",
        "APPRECIATION",
        "REQUIRED_SUPPORT",
        "WILLING_TO_SUPPORT",
    )
    assert len(REQUEST_TYPES) == 7
    assert "OTHER" not in REQUEST_TYPE_VALUES
    assert set(REQUEST_TYPE_VALUES).isdisjoint(CATEGORY_VALUES)
    assert CATEGORY_REQUIRED_TYPES == frozenset({"COMPLAINT", "GRIEVANCE"})
    assert LEGACY_REQUEST_TYPE_LABEL == "Not recorded (legacy)"
    assert GENERIC_DESK == "Centralized Support System Desk (SIMULATED)"


def test_meta_lists_request_types_additively(client):
    response = client.get("/portal/meta")
    assert response.status_code == 200, response.text
    body = response.json()

    assert [item["value"] for item in body["request_types"]] == list(
        REQUEST_TYPE_VALUES
    )
    assert all(
        set(item) == {"value", "label", "description", "requires_category"}
        for item in body["request_types"]
    )
    assert {
        item["value"]
        for item in body["request_types"]
        if item["requires_category"]
    } == {"COMPLAINT", "GRIEVANCE"}

    # The existing category metadata is still present and unchanged.
    assert [item["value"] for item in body["categories"]] == list(CATEGORY_VALUES)


# ---------------------------------------------------------------------------
# v2 submission
# ---------------------------------------------------------------------------


def test_v2_submission_supports_all_seven_request_types(client):
    token = register_and_login(client, "v2.types@example.com")
    reference_ids: list[str] = []

    for request_type, category in REQUEST_TYPE_CASES:
        body = submit_v2(client, token, request_type, category)

        assert set(body) == CREATED_V2_KEYS
        assert body["request_type"] == request_type
        assert body["category"] == category
        assert body["status"] == "SUBMITTED"
        assert ID_PATTERN.match(body["reference_id"])
        expected_department = (
            DEPARTMENT_BY_CATEGORY[category]
            if category is not None
            else GENERIC_DESK
        )
        assert body["department"] == expected_department
        reference_ids.append(body["reference_id"])

    assert len(set(reference_ids)) == len(REQUEST_TYPE_CASES)


def test_v2_category_rules_are_enforced(client):
    token = register_and_login(client, "v2.rules@example.com")
    headers = auth_header(token)

    missing_category = client.post(
        "/portal/v2/requests",
        json=submission(request_type="COMPLAINT"),
        headers=headers,
    )
    assert missing_category.status_code == 422, missing_category.text

    grievance_missing = client.post(
        "/portal/v2/requests",
        json=submission(request_type="GRIEVANCE"),
        headers=headers,
    )
    assert grievance_missing.status_code == 422, grievance_missing.text

    category_on_suggestion = client.post(
        "/portal/v2/requests",
        json=submission(request_type="SUGGESTION", category="FEE"),
        headers=headers,
    )
    assert category_on_suggestion.status_code == 422, category_on_suggestion.text

    for request_type in ("OTHER", "NOT_A_TYPE", "complaint"):
        response = client.post(
            "/portal/v2/requests",
            json=submission(request_type=request_type),
            headers=headers,
        )
        assert response.status_code == 422, (request_type, response.text)

    for category in ("OTHER", "NOT_A_CATEGORY", "fee"):
        response = client.post(
            "/portal/v2/requests",
            json=submission(request_type="COMPLAINT", category=category),
            headers=headers,
        )
        assert response.status_code == 422, (category, response.text)


def test_v2_field_validation_matches_v1(client):
    token = register_and_login(client, "v2.fields@example.com")
    headers = auth_header(token)

    invalid_payloads = [
        submission(request_type="SUGGESTION", subject="abcd"),
        submission(request_type="SUGGESTION", subject="x" * 151),
        submission(request_type="SUGGESTION", description="x" * 19),
        submission(request_type="SUGGESTION", description="x" * 4001),
        submission(request_type="SUGGESTION", institution_name="xy"),
        submission(request_type="SUGGESTION", state="x" * 81),
    ]
    for payload in invalid_payloads:
        response = client.post("/portal/v2/requests", json=payload, headers=headers)
        assert response.status_code == 422, response.text

    unauthenticated = client.post(
        "/portal/v2/requests",
        json=submission(request_type="SUGGESTION"),
    )
    assert unauthenticated.status_code == 401


def test_v1_submission_stays_legacy_and_keeps_exact_shape(client):
    token = register_and_login(client, "v1.legacy@example.com")

    response = client.post(
        "/portal/requests",
        json=submission(category="FEE"),
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"reference_id", "status", "category", "created_at"}

    with SessionLocal() as db:
        row = db.scalar(
            select(PortalRequest).where(
                PortalRequest.reference_id == body["reference_id"]
            )
        )
        assert row is not None
        assert row.request_type is None
        assert row.category == "FEE"
        assert row.department == DEPARTMENT_BY_CATEGORY["FEE"]


# ---------------------------------------------------------------------------
# v2 list and detail
# ---------------------------------------------------------------------------


def test_v2_list_and_detail_expose_both_concepts(client):
    token = register_and_login(client, "v2.list@example.com")
    headers = auth_header(token)

    complaint = submit_v2(client, token, "COMPLAINT", "FEE")
    suggestion = submit_v2(
        client,
        token,
        "SUGGESTION",
        subject="Improve the enquiry form",
        description=(
            "The enquiry form could include a clearer explanation of the "
            "information required from students."
        ),
    )

    listing = client.get("/portal/v2/requests", headers=headers)
    assert listing.status_code == 200, listing.text
    body = listing.json()

    assert body["total"] == 2
    assert body["counts"] == {
        "SUBMITTED": 2,
        "UNDER_REVIEW": 0,
        "REPLY_SENT": 0,
        "RESOLVED": 0,
    }
    assert all(set(item) == SUMMARY_V2_KEYS for item in body["items"])
    by_reference = {item["reference_id"]: item for item in body["items"]}
    assert by_reference[complaint["reference_id"]]["request_type"] == "COMPLAINT"
    assert by_reference[complaint["reference_id"]]["category"] == "FEE"
    assert by_reference[suggestion["reference_id"]]["request_type"] == "SUGGESTION"
    assert by_reference[suggestion["reference_id"]]["category"] is None

    suggestions = client.get(
        "/portal/v2/requests?request_type=SUGGESTION",
        headers=headers,
    )
    assert suggestions.status_code == 200
    assert suggestions.json()["total"] == 1
    assert suggestions.json()["items"][0]["reference_id"] == suggestion["reference_id"]

    fee = client.get("/portal/v2/requests?category=FEE", headers=headers)
    assert fee.status_code == 200
    assert fee.json()["total"] == 1
    assert fee.json()["items"][0]["reference_id"] == complaint["reference_id"]

    detail = client.get(
        f"/portal/v2/requests/{suggestion['reference_id']}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert set(detail_body) == DETAIL_V2_KEYS
    assert detail_body["request_type"] == "SUGGESTION"
    assert detail_body["category"] is None
    assert detail_body["department"] == GENERIC_DESK
    assert [event["status"] for event in detail_body["status_events"]] == [
        "SUBMITTED"
    ]


def test_v2_detail_hides_other_users_requests(client):
    token_a = register_and_login(client, "v2.alice@example.com", "Alice A")
    token_b = register_and_login(client, "v2.bob@example.com", "Bob B")

    created = submit_v2(client, token_a, "ENQUIRY")

    other = client.get(
        f"/portal/v2/requests/{created['reference_id']}",
        headers=auth_header(token_b),
    )
    unknown = client.get(
        "/portal/v2/requests/CSSD-2099-999999",
        headers=auth_header(token_b),
    )
    assert other.status_code == 404
    assert unknown.status_code == 404
    assert other.json() == unknown.json() == {"detail": "Request not found"}


def test_v1_endpoints_do_not_expose_non_complaint_requests(client):
    token = register_and_login(client, "v1.exclusion@example.com")
    headers = auth_header(token)

    suggestion = submit_v2(client, token, "SUGGESTION")

    listing = client.get("/portal/requests", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 0
    assert listing.json()["items"] == []

    detail = client.get(
        f"/portal/requests/{suggestion['reference_id']}",
        headers=headers,
    )
    assert detail.status_code == 404
    assert detail.json() == {"detail": "Request not found"}


# ---------------------------------------------------------------------------
# Feed and simulation
# ---------------------------------------------------------------------------


def test_feed_includes_complaints_and_legacy_but_excludes_non_complaints(client):
    token = register_and_login(client, "feed.types@example.com")
    headers = auth_header(token)

    complaint = submit_v2(client, token, "COMPLAINT", "FEE")
    suggestion = submit_v2(client, token, "SUGGESTION")
    legacy = client.post(
        "/portal/requests",
        json=submission(category="FACULTY"),
        headers=headers,
    )
    assert legacy.status_code == 201, legacy.text
    legacy_reference = legacy.json()["reference_id"]

    body = client.get("/tickets").json()
    ticket_references = {ticket["ticket_no"] for ticket in body["tickets"]}

    assert complaint["reference_id"] in ticket_references
    assert legacy_reference in ticket_references
    assert suggestion["reference_id"] not in ticket_references

    complaint_ticket = next(
        ticket
        for ticket in body["tickets"]
        if ticket["ticket_no"] == complaint["reference_id"]
    )
    assert complaint_ticket["grievance_category"] == "FEE"
    assert complaint_ticket["bureau_code"] == "RB"
    assert complaint_ticket["portal_submission"] is True


def test_non_complaint_simulation_uses_generic_template(client, monkeypatch):
    monkeypatch.delenv("CSS_PORTAL_ADMIN_KEY", raising=False)
    token = register_and_login(client, "sim.generic@example.com")
    headers = auth_header(token)

    created = submit_v2(client, token, "WILLING_TO_SUPPORT")

    for _ in range(2):
        response = client.post(
            f"/admin/portal/advance/{created['reference_id']}"
        )
        assert response.status_code == 200, response.text

    detail = client.get(
        f"/portal/v2/requests/{created['reference_id']}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["status"] == "REPLY_SENT"
    assert len(body["replies"]) == 1
    reply = body["replies"][0]
    assert reply["department"] == GENERIC_DESK
    assert reply["is_simulated"] is True
    assert "{department}" not in reply["message"]
    assert reply["message"] in {
        template.format(department=GENERIC_DESK)
        for template in GENERIC_REPLY_TEMPLATES["WILLING_TO_SUPPORT"]
    }


# ---------------------------------------------------------------------------
# Migration preservation
# ---------------------------------------------------------------------------

LEGACY_REQUESTS_DDL = """
CREATE TABLE portal_requests (
    id INTEGER NOT NULL,
    reference_id VARCHAR(32) NOT NULL,
    user_id INTEGER,
    category VARCHAR(48) NOT NULL,
    subject VARCHAR(240) NOT NULL,
    description TEXT NOT NULL,
    institution_name VARCHAR(240) NOT NULL,
    state VARCHAR(80),
    status VARCHAR(32) NOT NULL,
    department VARCHAR(160) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    next_step_at DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT uq_portal_requests_reference_id UNIQUE (reference_id),
    CONSTRAINT ck_portal_requests_category CHECK (
        category IN (
            'FEE', 'FACULTY', 'INFRASTRUCTURE', 'APPROVAL_VIOLATION',
            'ACADEMIC_ADMINISTRATION', 'GOVERNANCE_MISCONDUCT',
            'RAGGING_DISCRIMINATION'
        )
    ),
    CONSTRAINT ck_portal_requests_status CHECK (
        status IN ('SUBMITTED', 'UNDER_REVIEW', 'REPLY_SENT', 'RESOLVED')
    ),
    UNIQUE (reference_id),
    FOREIGN KEY(user_id) REFERENCES portal_users (id) ON DELETE SET NULL
)
"""


def _legacy_engine(
    tmp_path,
    *,
    orphan_status_event: bool = False,
    static_pool: bool = False,
    enable_foreign_keys: bool = True,
):
    engine_kwargs = {
        "connect_args": {"check_same_thread": False},
        "future": True,
    }
    if static_pool:
        engine_kwargs["poolclass"] = StaticPool
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'legacy_portal.db').as_posix()}",
        **engine_kwargs,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        if not enable_foreign_keys:
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE portal_users (id INTEGER NOT NULL PRIMARY KEY)"
        )
        connection.exec_driver_sql(LEGACY_REQUESTS_DDL)
        connection.exec_driver_sql(
            "CREATE INDEX ix_portal_requests_user_id "
            "ON portal_requests (user_id)"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE portal_status_events (
                id INTEGER NOT NULL PRIMARY KEY,
                request_id INTEGER NOT NULL,
                status VARCHAR(32) NOT NULL,
                remarks TEXT,
                actor VARCHAR(160),
                created_at DATETIME NOT NULL,
                FOREIGN KEY(request_id) REFERENCES portal_requests (id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE portal_replies (
                id INTEGER NOT NULL PRIMARY KEY,
                request_id INTEGER NOT NULL,
                department VARCHAR(160) NOT NULL,
                message TEXT NOT NULL,
                is_simulated BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(request_id) REFERENCES portal_requests (id)
                    ON DELETE CASCADE
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO portal_users (id) VALUES (1)"
        )
        connection.exec_driver_sql(
            """
            INSERT INTO portal_requests (
                id, reference_id, user_id, category, subject, description,
                institution_name, state, status, department, created_at,
                updated_at, next_step_at
            ) VALUES (
                1, 'CSSD-2025-100001', 1, 'FEE', 'Legacy fee complaint',
                'A legacy complaint created before request types existed.',
                'Demo Institute of Technology', 'Maharashtra', 'UNDER_REVIEW',
                'Fee Regulation Cell', '2025-01-02 03:04:05',
                '2025-01-03 04:05:06', '2025-01-04 05:06:07'
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO portal_status_events (
                id, request_id, status, remarks, actor, created_at
            ) VALUES (
                1, 1, 'UNDER_REVIEW', 'Legacy event', 'Department (SIMULATED)',
                '2025-01-03 04:05:06'
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO portal_replies (
                id, request_id, department, message, is_simulated, created_at
            ) VALUES (
                1, 1, 'Fee Regulation Cell', 'Legacy simulated reply', 1,
                '2025-01-03 04:05:06'
            )
            """
        )
        if orphan_status_event:
            # Deliberate orphan used to make PRAGMA foreign_key_check fail
            # during the migration. It is only insertable while enforcement
            # is disabled for this setup connection.
            connection.exec_driver_sql(
                """
                INSERT INTO portal_status_events (
                    id, request_id, status, remarks, actor, created_at
                ) VALUES (
                    2, 999, 'SUBMITTED', 'Orphan event',
                    'System (SIMULATED)', '2025-01-03 04:05:06'
                )
                """
            )

    return engine


def _table_schema(engine):
    """Snapshot columns, indexes and foreign keys for portal_requests."""

    with engine.connect() as connection:
        columns = {
            row[1]: {
                "type": row[2],
                "notnull": bool(row[3]),
                "pk": bool(row[5]),
            }
            for row in connection.exec_driver_sql(
                "PRAGMA table_info('portal_requests')"
            ).fetchall()
        }
        indexes = {}
        for row in connection.exec_driver_sql(
            "PRAGMA index_list('portal_requests')"
        ).fetchall():
            name = row[1]
            index_columns = tuple(
                info[2]
                for info in connection.exec_driver_sql(
                    f"PRAGMA index_info('{name}')"
                ).fetchall()
            )
            indexes[name] = {
                "unique": bool(row[2]),
                "origin": row[3],
                "columns": index_columns,
            }
        foreign_keys = [
            {
                "table": row[2],
                "from": row[3],
                "to": row[4],
                "on_update": row[5],
                "on_delete": row[6],
            }
            for row in connection.exec_driver_sql(
                "PRAGMA foreign_key_list('portal_requests')"
            ).fetchall()
        ]

    return columns, indexes, foreign_keys


def test_migration_preserves_all_indexes_and_constraints(tmp_path):
    engine = _legacy_engine(tmp_path)
    try:
        before_columns, before_indexes, before_foreign_keys = _table_schema(engine)
        assert migrate_portal_requests(engine) is True
        after_columns, after_indexes, after_foreign_keys = _table_schema(engine)

        # request_type is the only added column and category becomes nullable.
        assert set(after_columns) - set(before_columns) == {"request_type"}
        assert set(before_columns) - set(after_columns) == set()
        for name, definition in before_columns.items():
            if name == "category":
                assert after_columns[name]["type"] == definition["type"]
                assert after_columns[name]["pk"] == definition["pk"]
                assert after_columns[name]["notnull"] is False
            else:
                assert after_columns[name] == definition
        assert after_columns["request_type"] == {
            "type": "VARCHAR(32)",
            "notnull": False,
            "pk": False,
        }

        # Every index is recreated with the same name, uniqueness, origin and
        # columns, including both reference_id UNIQUE constraints.
        assert after_indexes == before_indexes
        assert after_indexes["ix_portal_requests_user_id"] == {
            "unique": False,
            "origin": "c",
            "columns": ("user_id",),
        }
        # SQLite enforces both UNIQUE (reference_id) declarations with one
        # autoindex; the point is that the index snapshot is unchanged.
        unique_indexes = [
            definition
            for definition in after_indexes.values()
            if definition["unique"]
        ]
        assert len(unique_indexes) == 1
        assert unique_indexes[0]["columns"] == ("reference_id",)

        # The user_id foreign key is preserved exactly.
        assert after_foreign_keys == before_foreign_keys
        assert len(after_foreign_keys) == 1
        foreign_key = after_foreign_keys[0]
        assert foreign_key["table"] == "portal_users"
        assert foreign_key["from"] == "user_id"
        assert foreign_key["to"] == "id"
        assert foreign_key["on_delete"] == "SET NULL"

        # Check constraints remain active after the rebuild.
        invalid_rows = [
            # duplicate reference ID
            (10, "CSSD-2025-100001", "SUGGESTION", None, "SUBMITTED"),
            # invalid status
            (11, "CSSD-2025-100011", "SUGGESTION", None, "NOT_A_STATUS"),
            # invalid request type
            (12, "CSSD-2025-100012", "OTHER", None, "SUBMITTED"),
            # invalid category
            (13, "CSSD-2025-100013", "COMPLAINT", "OTHER", "SUBMITTED"),
        ]
        for row_id, reference_id, request_type, category, status in invalid_rows:
            with pytest.raises(IntegrityError):
                with engine.begin() as connection:
                    connection.exec_driver_sql(
                        """
                        INSERT INTO portal_requests (
                            id, reference_id, request_type, category, subject,
                            description, institution_name, status, department,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 'Constraint test',
                                  'A row used to verify the check constraints.',
                                  'Demo Institute of Technology', ?,
                                  'Centralized Support System Desk (SIMULATED)',
                                  '2025-02-01 10:00:00',
                                  '2025-02-01 10:00:00')
                        """,
                        (row_id, reference_id, request_type, category, status),
                    )
    finally:
        engine.dispose()


def test_migration_rolls_back_when_foreign_key_check_fails(tmp_path):
    engine = _legacy_engine(
        tmp_path,
        orphan_status_event=True,
        static_pool=True,
        enable_foreign_keys=False,
    )
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM portal_requests"
                ).scalar()
                == 1
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM portal_status_events"
                ).scalar()
                == 2
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM portal_replies"
                ).scalar()
                == 1
            )

        with pytest.raises(RuntimeError, match="foreign-key violations"):
            migrate_portal_requests(engine)

        with engine.connect() as connection:
            columns = {
                row[1]: row
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info('portal_requests')"
                ).fetchall()
            }
            # The original schema survived the rollback.
            assert "request_type" not in columns
            assert columns["category"][3] == 1  # NOT NULL still in force

            row = connection.exec_driver_sql(
                """
                SELECT id, reference_id, category, status, department
                FROM portal_requests
                """
            ).fetchone()
            assert row == (
                1,
                "CSSD-2025-100001",
                "FEE",
                "UNDER_REVIEW",
                "Fee Regulation Cell",
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM portal_status_events"
                ).scalar()
                == 2
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM portal_replies"
                ).scalar()
                == 1
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type='table' AND name='portal_requests_migrated'"
                ).scalar()
                == 0
            )
            # The migration restores enforcement on the same pooled connection.
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    finally:
        engine.dispose()


def test_migration_preserves_existing_rows_and_children(tmp_path):
    engine = _legacy_engine(tmp_path)
    try:
        assert migrate_portal_requests(engine) is True
        assert migrate_portal_requests(engine) is False

        with engine.connect() as connection:
            columns = {
                row[1]: row
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(portal_requests)"
                ).fetchall()
            }
            assert "request_type" in columns
            assert columns["category"][3] == 0  # nullable flag cleared

            row = connection.exec_driver_sql(
                """
                SELECT id, reference_id, user_id, request_type, category,
                       subject, description, institution_name, state, status,
                       department, created_at, updated_at, next_step_at
                FROM portal_requests
                """
            ).fetchone()
            assert row is not None
            assert row[0] == 1
            assert row[1] == "CSSD-2025-100001"
            assert row[2] == 1
            assert row[3] is None
            assert row[4] == "FEE"
            assert row[5] == "Legacy fee complaint"
            assert row[9] == "UNDER_REVIEW"
            assert row[10] == "Fee Regulation Cell"
            assert row[12] == "2025-01-03 04:05:06"
            assert row[13] == "2025-01-04 05:06:07"

            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM portal_status_events"
                ).scalar()
                == 1
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM portal_replies"
                ).scalar()
                == 1
            )
            assert connection.exec_driver_sql(
                "PRAGMA foreign_key_check"
            ).fetchall() == []

        # The rebuilt schema accepts a non-complaint row with no category and
        # still rejects unknown categories.
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO portal_requests (
                    id, reference_id, request_type, category, subject,
                    description, institution_name, status, department,
                    created_at, updated_at
                ) VALUES (
                    2, 'CSSD-2025-100002', 'SUGGESTION', NULL,
                    'Improve the form',
                    'A suggestion recorded after the migration.',
                    'Demo Institute of Technology', 'SUBMITTED',
                    'Centralized Support System Desk (SIMULATED)',
                    '2025-02-01 10:00:00', '2025-02-01 10:00:00'
                )
                """
            )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    """
                    INSERT INTO portal_requests (
                        id, reference_id, request_type, category, subject,
                        description, institution_name, status, department,
                        created_at, updated_at
                    ) VALUES (
                        3, 'CSSD-2025-100003', 'COMPLAINT', 'OTHER',
                        'Unknown category',
                        'This row must be rejected by the check constraint.',
                        'Demo Institute of Technology', 'SUBMITTED',
                        'Fee Regulation Cell',
                        '2025-02-01 10:00:00', '2025-02-01 10:00:00'
                    )
                    """
                )
    finally:
        engine.dispose()
