"""Protocol-violation watchdog — Phase 4 of stabilization v5.

Diagnostic helper that surfaces tasks the dispatcher's own retry logic has
not yet handled. Hermes v0.13.0 already marks a worker run as
``crashed (protocol_violation)`` when the worker exits without calling
``kanban_complete`` / ``kanban_block``; after ``failure_limit`` attempts the
task is auto-``blocked``. This module catches the gap where:

  - the task row is still ``status='running'`` (no active attempt), AND
  - the latest run row is ENDED (outcome != 'running'), AND
  - the latest outcome is not ``completed`` / ``blocked``

…meaning the dispatcher has not yet acted but the worker is dead. We then
emit a ``hermes kanban block --reason "protocol_violation: …"`` so the task
becomes terminal-and-retryable instead of indefinitely stuck.

Idempotent — running twice on the same board only blocks tasks newly in
the gap window.

Usage (CLI):
    python3 -m core.watchdog --board <slug> [--dry-run]

The operator wires this into a systemd timer (out-of-scope OT4).
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from typing import Iterable, Optional

from dashboard.backend.services.kanban_reader import HERMES_BIN, KanbanReader

logger = logging.getLogger("devbooth.watchdog")
_TERMINAL_RUN_OUTCOMES: frozenset[str] = frozenset({"completed", "blocked"})


def _latest_run(runs: list[dict]) -> Optional[dict]:
    """Highest-attempt run row, or None when no runs exist yet."""
    return max(runs, key=lambda r: r.get("attempt", 0)) if runs else None


def _is_protocol_violation(task: dict, latest: Optional[dict]) -> bool:
    """A 'running' task whose latest attempt has ended *without* a lifecycle call."""
    if task.get("status") != "running" or latest is None:
        return False
    outcome = (latest.get("outcome") or "").strip().lower()
    if outcome == "running":
        return False                              # an attempt is still in flight
    return outcome not in _TERMINAL_RUN_OUTCOMES   # ended but not done/blocked


def reap_protocol_violations(board: str, dry_run: bool = False,
                             reader: Optional[KanbanReader] = None) -> list[str]:
    """Block stuck-running tasks whose latest attempt ended without lifecycle.

    Returns the list of task ids that were (or would have been, in dry-run)
    transitioned. Safe to call repeatedly — only the matching tasks act.
    """
    reader = reader or KanbanReader(board)
    if not reader.exists:
        logger.warning("board %r not found at %s", board, reader.db_path)
        return []

    reaped: list[str] = []
    for task in reader.list_tasks(status="running"):
        tid = task.get("id")
        if not tid:
            continue
        latest = _latest_run(reader.get_runs(tid))
        if not _is_protocol_violation(task, latest):
            continue
        outcome = (latest.get("outcome") or "?") if latest else "?"
        reason = (f"protocol_violation: latest run ended (outcome={outcome!r}) "
                  f"without kanban_complete/kanban_block")
        logger.info("reaping %s [%s]: %s", tid, task.get("title", "")[:40], reason)
        if not dry_run:
            _block_task(board, tid, reason)
        reaped.append(tid)
    return reaped


def _block_task(board: str, task_id: str, reason: str) -> None:
    """Shell out to ``hermes kanban block`` — terminal and survives restart."""
    subprocess.run(
        [HERMES_BIN, "kanban", "--board", board, "block", task_id, "--reason", reason],
        capture_output=True, text=True, timeout=15,
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="core.watchdog",
        description="Block stuck-running tasks whose latest run ended without lifecycle call.",
    )
    parser.add_argument("--board", required=True, help="kanban board slug")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be reaped without blocking")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    reaped = reap_protocol_violations(args.board, dry_run=args.dry_run)
    print(f"board={args.board} reaped={len(reaped)}: {reaped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
