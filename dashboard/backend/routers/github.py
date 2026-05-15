"""GitHub bot-account status — surfaces `gh auth status` for the dashboard."""
from __future__ import annotations

import subprocess

from fastapi import APIRouter

router = APIRouter(prefix="/api/github", tags=["github"])


@router.get("/status")
def github_status() -> dict:
    """Return CrownClownCrowd bot-account login state."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=5,
        )
        text = (result.stdout or "") + (result.stderr or "")
        logged_in = "CrownClownCrowd" in text
        return {
            "logged_in": logged_in,
            "account": "CrownClownCrowd" if logged_in else None,
            "target": "mooner92",
        }
    except (subprocess.TimeoutExpired, OSError):
        return {"logged_in": False, "account": None, "target": "mooner92"}
