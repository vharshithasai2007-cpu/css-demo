"""Configuration for the CSS educational portal data layer.

Environment variables:
    CSS_PORTAL_DB_PATH       SQLite file path (default: ./data/css_portal.db)
    CSS_PORTAL_SECRET_KEY    signing secret; required in production
    CSS_PORTAL_TOKEN_MINUTES token lifetime in minutes (default: 120)
    CSS_PORTAL_SIM_STEP_SECONDS simulated lifecycle step in seconds (default: 45)
    CSS_PORTAL_ENV           deployment environment (default: development)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path("./data/css_portal.db")
DEFAULT_DB_PATH_STRING = "./data/css_portal.db"
DEFAULT_TOKEN_MINUTES = 120
DEFAULT_SIM_STEP_SECONDS = 45
DEFAULT_ENVIRONMENT = "development"
DEV_SECRET_KEY = "css-portal-dev-only-insecure-secret"


def _read_environment() -> str:
    return os.getenv("CSS_PORTAL_ENV", DEFAULT_ENVIRONMENT).strip().lower()


def _read_token_minutes() -> int:
    raw = os.getenv("CSS_PORTAL_TOKEN_MINUTES", str(DEFAULT_TOKEN_MINUTES))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("CSS_PORTAL_TOKEN_MINUTES must be an integer") from exc
    if value <= 0:
        raise ValueError("CSS_PORTAL_TOKEN_MINUTES must be greater than zero")
    return value


def _read_sim_step_seconds() -> int:
    raw = os.getenv("CSS_PORTAL_SIM_STEP_SECONDS", str(DEFAULT_SIM_STEP_SECONDS))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("CSS_PORTAL_SIM_STEP_SECONDS must be an integer") from exc
    if value <= 0:
        raise ValueError("CSS_PORTAL_SIM_STEP_SECONDS must be greater than zero")
    return value


def _read_secret_key(environment: str) -> str:
    configured = os.getenv("CSS_PORTAL_SECRET_KEY")
    if configured:
        return configured
    if environment == "production":
        raise RuntimeError(
            "CSS_PORTAL_SECRET_KEY must be set when CSS_PORTAL_ENV=production"
        )
    # The development default is intentionally obvious and insecure.
    return DEV_SECRET_KEY


@dataclass(frozen=True)
class PortalSettings:
    db_path: Path
    secret_key: str
    token_minutes: int
    sim_step_seconds: int
    environment: str

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def load_settings() -> PortalSettings:
    environment = _read_environment()
    return PortalSettings(
        db_path=Path(os.getenv("CSS_PORTAL_DB_PATH", DEFAULT_DB_PATH_STRING)),
        secret_key=_read_secret_key(environment),
        token_minutes=_read_token_minutes(),
        sim_step_seconds=_read_sim_step_seconds(),
        environment=environment,
    )


settings = load_settings()

# Convenience aliases for callers that prefer module-level constants.
DB_PATH = settings.db_path
SECRET_KEY = settings.secret_key
TOKEN_MINUTES = settings.token_minutes
SIM_STEP_SECONDS = settings.sim_step_seconds
ENVIRONMENT = settings.environment
