"""Preflight checks for the Dev-Booth multi-agent runtime (plan v3 Phase 0, PM-4).

Run standalone::

    /dev-booth/env/bin/python3.11 -m core.preflight

Or call :func:`run_all` from the orchestrator's ``setup()`` (with
``require_profiles=True`` once Phase 2 has created the agent profiles).

Hard checks (failure ⇒ non-zero exit / raised ``PreflightError``):
  * vLLM is alive AND serving the *expected* model (identity, not just liveness).
  * ``agent_working_group`` is importable under the venv interpreter.
  * ``gh`` is authenticated.

Soft check (warns, never fails on its own):
  * the three hermes agent profiles exist. Promoted to a hard check when
    ``require_profiles=True``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request

from core import config


class PreflightError(RuntimeError):
    """A hard preflight check failed."""


def _ok(msg: str) -> None:
    print(f"  ok    {msg}")


def _warn(msg: str) -> None:
    print(f"  warn  {msg}")


def check_vllm() -> None:
    """Assert the vLLM endpoint serves ``config.EXPECTED_MODEL`` (identity check)."""
    url = f"{config.VLLM_BASE_URL}/models"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 — local
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise PreflightError(f"vLLM unreachable at {url}: {exc}") from exc

    served = [m.get("id") for m in payload.get("data", [])]
    if config.EXPECTED_MODEL not in served:
        raise PreflightError(
            f"vLLM model mismatch — expected {config.EXPECTED_MODEL!r}, "
            f"served {served!r}"
        )
    _ok(f"vLLM serving {config.EXPECTED_MODEL}")


def check_awg() -> None:
    """Assert the AWG message queue is importable under this interpreter."""
    try:
        from agent_working_group import MessageQueue  # noqa: F401
    except ImportError as exc:
        raise PreflightError(
            "agent_working_group not importable — run under the venv "
            f"({config.VENV_PYTHON}): {exc}"
        ) from exc
    _ok("agent_working_group.MessageQueue importable")


def check_gh() -> None:
    """Assert the GitHub CLI is authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightError(f"gh auth status failed to run: {exc}") from exc
    if result.returncode != 0:
        raise PreflightError(f"gh not authenticated: {result.stderr.strip()}")
    _ok("gh authenticated")


def check_profiles(require: bool = False) -> bool:
    """Check that the three hermes agent profiles exist.

    Soft by default (returns ``False`` + warns). When ``require`` is set, a
    missing profile raises :class:`PreflightError`.
    """
    try:
        result = subprocess.run(
            [config.HERMES_BIN, "profile", "list"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightError(f"hermes profile list failed to run: {exc}") from exc

    listing = result.stdout
    missing = [name for name in config.AGENTS if name not in listing]
    if missing:
        msg = f"hermes profiles missing: {missing} (create them in Phase 2)"
        if require:
            raise PreflightError(msg)
        _warn(msg)
        return False
    _ok(f"hermes profiles present: {', '.join(config.AGENTS)}")
    return True


def run_all(require_profiles: bool = False) -> None:
    """Run every preflight check. Raises :class:`PreflightError` on hard failure."""
    print("[preflight] Dev-Booth multi-agent runtime")
    check_vllm()
    check_awg()
    check_gh()
    check_profiles(require=require_profiles)
    print("[preflight] all hard checks passed")


def main() -> int:
    try:
        run_all(require_profiles=False)
    except PreflightError as exc:
        print(f"[preflight] FAIL — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
