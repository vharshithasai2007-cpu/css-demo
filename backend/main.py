import os
import random
import threading
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from portal.db import SessionLocal, get_session, init_db
from portal.feed import is_feed_eligible, request_to_ticket
from portal.models import PortalRequest, utcnow
from portal.routers.auth import router as portal_auth_router
from portal.routers.meta import router as portal_meta_router
from portal.routers.requests import router as portal_requests_router
from portal.routers.requests_v2 import router as portal_requests_v2_router
from portal.simulation import (
    advance_all_requests,
    advance_request,
    run_due_requests,
)

app = FastAPI(title="Mock CSS (SIMULATOR - synthetic data)")
INTERVAL = 20
_lock = threading.RLock()
_counter = 0
tickets: list[dict[str, Any]] = []

NOISY = [
    "St Xaviers Inst of Tech",
    "Natl Coll of Engg",
    "Shri Saraswati Inst of Engg & Tech",
    "Govt Coll Engg",
    "Modern Inst of Mgmt and Tech",
    "Global Coll of Tech",
]
NARRATIVES = [
    "Excessive fee charged beyond the approved fee structure for the current academic year.",
    "Faculty shortage in core engineering departments is affecting classes.",
    "Laboratory and hostel infrastructure is inadequate for students.",
    "Unauthorized intake beyond approved seats was observed during admission.",
    "शुल्क निर्धारित संरचना से अधिक लिया जा रहा है।",
    "கல்லூரியில் ஆசிரியர் பற்றாக்குறை காரணமாக வகுப்புகள் நடைபெறவில்லை.",
]
CATEGORIES = ["FEE", "FACULTY", "INFRASTRUCTURE", "APPROVAL_VIOLATION", "RAGGING_DISCRIMINATION", "OTHER"]


def make_ticket(institution: str | None = None) -> dict[str, Any]:
    global _counter
    with _lock:
        _counter += 1
        n = _counter
    now = datetime.utcnow()
    return {
        "ticket_no": f"CSS-{88000 + n}",
        "institution_name": institution or random.choice(NOISY),
        "grievance": random.choice(NARRATIVES),
        "grievance_category": random.choice(CATEGORIES),
        "received_date": now.strftime("%d/%m/%Y"),
        "current_status": "Pending",
        "bureau_code": "RB",
        "language": "hi" if "शुल्क" in NARRATIVES[4] else "en",
        "complainant_ref": f"demo-css-{random.randint(1, 300)}",
        "state": "Maharashtra",
        "simulator": True,
    }


def seed():
    with _lock:
        tickets.append(make_ticket("St. Xavier Institute of Technology"))
        tickets.append(make_ticket())


def generate_loop():
    while True:
        threading.Event().wait(INTERVAL)
        with _lock:
            tickets.append(make_ticket())


class InjectBody(BaseModel):
    institution_name: str | None = None
    grievance: str | None = None
    category: str | None = None


def autogen_enabled() -> bool:
    """Return whether random simulator tickets should be generated.

    MOCK_CSS_AUTOGEN defaults to "true". Setting it to "false" (any case)
    skips both the two seed tickets and the background generator thread.
    """

    return os.getenv("MOCK_CSS_AUTOGEN", "true").strip().lower() != "false"


SIM_INTERVAL = 10


def simulation_enabled() -> bool:
    """Return whether the portal simulation loop should run."""

    return os.getenv("CSS_PORTAL_SIM_ENABLED", "true").strip().lower() != "false"


def simulation_loop():
    while True:
        threading.Event().wait(SIM_INTERVAL)
        try:
            with SessionLocal() as session:
                run_due_requests(session, utcnow())
        except Exception:
            # Keep the demo loop alive across transient SQLite contention.
            pass


def _require_demo_admin_key(
    x_demo_admin_key: str | None = Header(default=None, alias="X-Demo-Admin-Key"),
) -> None:
    """Enforce X-Demo-Admin-Key only when CSS_PORTAL_ADMIN_KEY is set."""

    expected = os.getenv("CSS_PORTAL_ADMIN_KEY")
    if expected and x_demo_admin_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid demo admin key",
        )


@app.on_event("startup")
def startup():
    init_db()
    if simulation_enabled():
        threading.Thread(target=simulation_loop, daemon=True).start()
    if not autogen_enabled():
        return
    seed()
    threading.Thread(target=generate_loop, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-css", "simulator": True}


@app.get("/tickets")
def list_tickets(
    since: str | None = Query(default=None),
    db: Session = Depends(get_session),
):
    # The simulator's own tickets keep their original shape and stay first.
    with _lock:
        simulator_tickets = list(tickets)

    # Portal submissions are appended in the dashboard's CSS ticket shape.
    # The `since` parameter is intentionally ignored: the feed returns all.
    portal_requests = db.scalars(
        select(PortalRequest)
        .options(selectinload(PortalRequest.user))
        .order_by(PortalRequest.id.asc())
    ).all()
    portal_tickets = [
        request_to_ticket(request)
        for request in portal_requests
        if is_feed_eligible(request)
    ]

    return {
        "simulator": True,
        "source_type": "SIMULATOR",
        "banner": "SIMULATOR – synthetic data",
        "tickets": simulator_tickets + portal_tickets,
    }


@app.post("/admin/inject")
def inject(body: InjectBody):
    t = make_ticket(body.institution_name)
    if body.grievance:
        t["grievance"] = body.grievance
    if body.category:
        t["grievance_category"] = body.category
    with _lock:
        tickets.append(t)
    return {"simulator": True, "ticket": t}


@app.post("/admin/scenario")
def scenario():
    now = datetime.utcnow()
    a = {
        "ticket_no": f"CSS-HERO-{random.randint(1000,9999)}",
        "institution_name": "St Xaviers Inst of Tech",
        "grievance": "Unauthorised intake beyond sanctioned seats in engineering branches; approval conditions appear to be violated.",
        "grievance_category": "APPROVAL_VIOLATION",
        "received_date": now.strftime("%d/%m/%Y"),
        "current_status": "Pending",
        "bureau_code": "RB",
        "language": "en",
        "complainant_ref": f"scenario-css-{random.randint(1,999)}",
        "simulator": True,
    }
    with _lock:
        tickets.append(a)
    return {"simulator": True, "ticket": a}


@app.post("/admin/portal/advance/{reference_id}")
def admin_advance_request(
    reference_id: str,
    _admin: None = Depends(_require_demo_admin_key),
    db: Session = Depends(get_session),
):
    request = db.scalar(
        select(PortalRequest).where(PortalRequest.reference_id == reference_id)
    )
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    advanced = advance_request(db, request, utcnow())
    db.commit()
    db.refresh(request)
    return {
        "simulator": True,
        "reference_id": request.reference_id,
        "status": request.status,
        "advanced": advanced,
    }


@app.post("/admin/portal/advance-all")
def admin_advance_all(
    _admin: None = Depends(_require_demo_admin_key),
    db: Session = Depends(get_session),
):
    advanced = advance_all_requests(db, utcnow())
    return {"simulator": True, "advanced": advanced}


app.include_router(portal_auth_router)
app.include_router(portal_meta_router)
app.include_router(portal_requests_router)
app.include_router(portal_requests_v2_router)
