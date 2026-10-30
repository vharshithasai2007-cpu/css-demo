"""Unauthenticated portal metadata: categories, user types, institutions."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from ..categories import CATEGORIES, USER_TYPES
from ..request_types import REQUEST_TYPE_METADATA

router = APIRouter(prefix="/portal", tags=["portal-meta"])

INSTITUTIONS_PATH = Path(__file__).resolve().parents[1] / "institutions.json"


def load_institutions() -> list[dict[str, str]]:
    """Read the static institution list reproduced from the dashboard seed."""

    with INSTITUTIONS_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)

    return [
        {"name": str(item["name"]), "state": str(item["state"])}
        for item in data
    ]


@router.get("/meta")
def meta() -> dict[str, object]:
    return {
        "categories": [
            {
                "value": category.value,
                "label": category.label,
                "description": category.description,
                "department": category.department,
            }
            for category in CATEGORIES
        ],
        "request_types": list(REQUEST_TYPE_METADATA),
        "user_types": list(USER_TYPES),
        "institutions": load_institutions(),
    }
