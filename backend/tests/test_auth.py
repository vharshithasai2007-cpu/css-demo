"""Tests for Phase 3 portal authentication (mock_css/portal)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import jwt

from portal.security import (
    PORTAL_JWT_ALGORITHM,
    PORTAL_JWT_AUDIENCE,
    PORTAL_JWT_ISSUER,
    create_access_token,
)

REGISTER_URL = "/portal/auth/register"
LOGIN_URL = "/portal/auth/login"
ME_URL = "/portal/auth/me"

PASSWORD = "correct-horse-battery"


def register_payload(**overrides):
    payload = {
        "full_name": "Demo Student",
        "email": "student@example.com",
        "password": PASSWORD,
        "user_type": "STUDENT",
        "institution_name": "Demo Institute of Technology",
    }
    payload.update(overrides)
    return payload


def register(client, **overrides):
    response = client.post(REGISTER_URL, json=register_payload(**overrides))
    assert response.status_code == 201, response.text
    return response


def login(client, email="student@example.com", password=PASSWORD):
    return client.post(LOGIN_URL, json={"email": email, "password": password})


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_then_login_then_me(client):
    created = register(client)
    body = created.json()

    assert body["full_name"] == "Demo Student"
    assert body["email"] == "student@example.com"
    assert body["user_type"] == "STUDENT"
    assert body["institution_name"] == "Demo Institute of Technology"
    assert isinstance(body["id"], int)
    # Registration must not auto-login.
    assert "access_token" not in body
    assert "token_type" not in body

    logged_in = login(client)
    assert logged_in.status_code == 200, logged_in.text
    tokens = logged_in.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]

    me = client.get(ME_URL, headers=auth_header(tokens["access_token"]))
    assert me.status_code == 200, me.text
    profile = me.json()
    assert profile == {
        "id": body["id"],
        "full_name": "Demo Student",
        "email": "student@example.com",
        "user_type": "STUDENT",
        "institution_name": "Demo Institute of Technology",
    }


def test_register_normalizes_email_and_user_type(client):
    response = register(
        client,
        email="  Mixed.Case@Example.COM  ",
        user_type="faculty",
        institution_name="  Demo College  ",
    )
    body = response.json()
    assert body["email"] == "mixed.case@example.com"
    assert body["user_type"] == "FACULTY"
    assert body["institution_name"] == "Demo College"

    logged_in = login(client, email="MIXED.CASE@example.com")
    assert logged_in.status_code == 200, logged_in.text


def test_duplicate_email_returns_409(client):
    register(client)
    duplicate = client.post(REGISTER_URL, json=register_payload())
    assert duplicate.status_code == 409


def test_wrong_password_and_unknown_email_have_identical_401_bodies(client):
    register(client)

    wrong_password = login(client, password="definitely-not-it")
    unknown_email = login(client, email="nobody@example.com", password=PASSWORD)

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["detail"] == "Incorrect email or password."


def test_weak_password_is_rejected(client):
    too_short = client.post(
        REGISTER_URL,
        json=register_payload(password="short"),
    )
    assert too_short.status_code == 422

    same_as_email = client.post(
        REGISTER_URL,
        json=register_payload(email="same@example.com", password="same@example.com"),
    )
    assert same_as_email.status_code == 422


def test_token_signed_with_different_secret_is_rejected(client):
    register(client)

    forged = jwt.encode(
        {
            "sub": "1",
            "aud": PORTAL_JWT_AUDIENCE,
            "iss": PORTAL_JWT_ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "some-other-secret",
        algorithm=PORTAL_JWT_ALGORITHM,
    )
    response = client.get(ME_URL, headers=auth_header(forged))
    assert response.status_code == 401


def test_wrong_audience_token_is_rejected(client):
    register(client)

    # Shaped like a dashboard token: sub is the email, no aud claim, and a
    # completely different signing secret.
    dashboard_shaped = jwt.encode(
        {
            "sub": "student@example.com",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "dashboard-secret",
        algorithm=PORTAL_JWT_ALGORITHM,
    )
    response = client.get(ME_URL, headers=auth_header(dashboard_shaped))
    assert response.status_code == 401


def test_token_with_portal_secret_but_wrong_audience_is_rejected(client):
    register(client)

    from portal.config import settings

    wrong_aud = jwt.encode(
        {
            "sub": "1",
            "aud": "some-other-audience",
            "iss": PORTAL_JWT_ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.secret_key,
        algorithm=PORTAL_JWT_ALGORITHM,
    )
    response = client.get(ME_URL, headers=auth_header(wrong_aud))
    assert response.status_code == 401


def test_expired_token_is_rejected(client):
    register(client)

    expired = create_access_token(1, expires_delta=timedelta(minutes=-5))
    response = client.get(ME_URL, headers=auth_header(expired))
    assert response.status_code == 401


def test_missing_token_is_rejected(client):
    response = client.get(ME_URL)
    assert response.status_code == 401


def test_eleventh_rapid_login_attempt_returns_429(client):
    register(client)

    statuses = [
        login(client, password="wrong-password").status_code for _ in range(10)
    ]
    assert statuses == [401] * 10

    throttled = login(client, password="wrong-password")
    assert throttled.status_code == 429
    assert throttled.headers.get("Retry-After")
    assert int(throttled.headers["Retry-After"]) >= 1


def test_password_hash_and_public_ref_never_appear_in_responses(client):
    created = register(client)
    logged_in = login(client)
    token = logged_in.json()["access_token"]
    me = client.get(ME_URL, headers=auth_header(token))

    for response in (created, logged_in, me):
        assert response.status_code < 400
        text = response.text
        assert "password_hash" not in text
        assert "public_ref" not in text
        assert PASSWORD not in text

    # The stored hash must never equal the plaintext password either.
    from sqlalchemy import select

    from portal.db import SessionLocal
    from portal.models import PortalUser

    with SessionLocal() as db:
        user = db.scalar(select(PortalUser))
        assert user is not None
        assert user.password_hash != PASSWORD
        assert user.password_hash.startswith("$2")
        assert user.public_ref not in created.text
        assert user.public_ref not in me.text
