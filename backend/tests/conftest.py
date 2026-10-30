"""Test fixtures for the CSS educational portal data layer.

The environment is configured before importing ``main`` so the engine points at
a throwaway SQLite file and the simulator's random generator stays off by
default. Individual tests opt back in when they exercise startup behaviour.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

MOCK_CSS_ROOT = Path(__file__).resolve().parents[1]
if str(MOCK_CSS_ROOT) not in sys.path:
    sys.path.insert(0, str(MOCK_CSS_ROOT))

_TMPDIR = tempfile.TemporaryDirectory(prefix="mock-css-portal-tests-")
os.environ["CSS_PORTAL_DB_PATH"] = str(Path(_TMPDIR.name) / "css_portal.db")
os.environ["CSS_PORTAL_ENV"] = "test"
os.environ["CSS_PORTAL_SECRET_KEY"] = "test-portal-secret-key"
os.environ["MOCK_CSS_AUTOGEN"] = "false"
# Keep the background simulator out of tests; Phase 6 tests call the engine
# directly and exercise startup gating explicitly.
os.environ["CSS_PORTAL_SIM_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from portal import models  # noqa: E402,F401  (register the tables)
from portal.db import Base, engine  # noqa: E402
from portal.rate_limit import reset_rate_limit  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _dispose_engine_at_end():
    yield
    engine.dispose()
    _TMPDIR.cleanup()


@pytest.fixture(autouse=True)
def _fresh_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    main.tickets.clear()
    reset_rate_limit()
    yield
    main.tickets.clear()
    reset_rate_limit()


@pytest.fixture()
def client():
    with TestClient(main.app) as test_client:
        yield test_client
