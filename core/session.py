"""Dev-Booth session manager — Hermes Kanban edition.

Replaces the v1 stateless orchestrator. This module does NOT run agents. It
creates a named Kanban board and seeds the v6 micro-task DAG (core/scenario.py)
as tasks; the always-running `hermes gateway` dispatcher then claims the tasks
and spawns the assigned profiles as workers.

CLI command form (verified in Phase 0): the ``--board <slug>`` flag is a
``hermes kanban``-LEVEL flag and must come BEFORE the subcommand:
    hermes kanban --board <slug> create "<title>" --assignee conductor ...
Board-management verbs (`boards create`, `boards list`) take the slug
positionally and do not use ``--board``.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.scenario import ALLOWED_ASSIGNEES, STAGE_DAG, format_task

HERMES_BIN = "/home/mooner92/.local/bin/hermes"
SESSIONS_ROOT = Path(os.getenv("DEV_BOOTH_PATH", "/dev-booth/sessions"))


class DevBoothSession:
    """Hermes-Kanban-backed Dev-Booth session: board setup + DAG seed.

    Unlike the v1 orchestrator, this class never spawns or drives agents. It
    only seeds the board; the gateway dispatcher does the rest.
    """

    def __init__(self, session_name: str, repo_url: str, goal: str):
        self.session_name = session_name
        self.repo_url = repo_url.rstrip("/")
        url_parts = self.repo_url.split("/")
        self.repo_name = url_parts[-1].removesuffix(".git")
        # upstream owner is whoever owns the source repo; the bot account
        # (CrownClownCrowd) forks into its own namespace.
        self.repo_owner = url_parts[-2] if len(url_parts) >= 2 else ""
        self.goal = goal
        # named board (NOT the default board) — isolation of an autonomous
        # git-action system from the operator's shared ~/.hermes/kanban.db
        self.board_slug = session_name.lower().replace("_", "-").replace(" ", "-")
        self.session_path = SESSIONS_ROOT / session_name

    # -------------------------------------------------------------- setup
    def setup(self) -> None:
        """Create the session dir + the named Kanban board; write status.json."""
        self.session_path.mkdir(parents=True, exist_ok=True)
        (self.session_path / "log").mkdir(exist_ok=True)

        existing = self._kanban_json("boards", "list")
        existing_slugs = {
            b.get("slug", b.get("name", ""))
            for b in (existing if isinstance(existing, list) else existing.get("boards", []))
        }
        if self.board_slug not in existing_slugs:
            self._kanban(
                "boards", "create", self.board_slug,
                "--name", self.session_name,
                "--description", self.goal,
            )

        self._write_status(step=0, agent="system", status="initializing")
        print(f"OK setup: session={self.session_name} board={self.board_slug}")
        self.seed()

    # --------------------------------------------------------------- seed
    def seed(self) -> dict[int, str]:
        """Seed the DAG as Kanban tasks with --parent dependency links.

        Returns the stage_no -> task_id map. The dispatcher promotes a child
        task to `ready` only when all its parents are `done`.
        """
        ctx = {
            "repo": self.repo_name,
            "repo_url": self.repo_url,
            "repo_owner": self.repo_owner,
            "goal": self.goal,
            "session": self.session_name,
            "session_path": str(self.session_path),  # v5: bodies hard-code absolute artifact paths
            "n": 1,
            "task_description": "initial implementation",
        }
        stage_id_map: dict[int, str] = {}

        for stage in STAGE_DAG:
            if stage.assignee not in ALLOWED_ASSIGNEES:
                raise ValueError(
                    f"stage {stage.stage} has unknown assignee {stage.assignee!r} "
                    f"(allowed: {sorted(ALLOWED_ASSIGNEES)}) — dispatcher would never spawn it"
                )
            params = format_task(stage, **ctx)
            args = [
                "--board", self.board_slug, "create", params["title"],
                "--assignee", params["assignee"],
                "--workspace", params["workspace"],
                "--body", params["body"],
                "--priority", "1",
                "--idempotency-key", f"devbooth-{self.board_slug}-stage{stage.stage}",
                "--json",
            ]
            for parent_stage in stage.parent_stages:
                if parent_stage in stage_id_map:
                    args += ["--parent", stage_id_map[parent_stage]]

            result = self._kanban_json(*args)
            task_id = result.get("id", "") if isinstance(result, dict) else ""
            stage_id_map[stage.stage] = task_id
            print(f"  stage {stage.stage:2d} [{params['assignee']:9s}] {params['title'][:46]} -> {task_id}")

        (self.session_path / "stage_task_map.json").write_text(
            json.dumps(stage_id_map, indent=2), encoding="utf-8"
        )
        self._write_status(
            step=1, agent="conductor", status="active",
            board_slug=self.board_slug, stage_task_map=stage_id_map,
        )
        print(f"OK seed: {len(stage_id_map)} tasks on board {self.board_slug}")
        print(f"  dashboard: http://localhost:7000/session/{self.session_name}")
        print(f"  kanban:    hermes kanban --board {self.board_slug} watch")
        return stage_id_map

    # ------------------------------------------------------------ helpers
    def _kanban(self, *args: str) -> str:
        """Run ``hermes kanban <args...>`` and return stdout. Raises on failure."""
        result = subprocess.run(
            [HERMES_BIN, "kanban", *args],
            capture_output=True, text=True, check=True,
        )
        return result.stdout

    def _kanban_json(self, *args: str):
        """Run ``hermes kanban <args...>`` and parse JSON stdout (list or dict).

        Returns ``{}`` on a non-zero exit or unparseable output — callers treat
        an empty result as "nothing there" rather than crashing.
        """
        try:
            output = self._kanban(*args)
            return json.loads(output) if output.strip() else {}
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return {}

    def _write_status(self, step: int, agent: str, status: str, **extra) -> None:
        """Write status.json — an operator artifact; the dashboard reads the board."""
        data = {
            "session": self.session_name,
            "status": status,
            "current_step": step,
            "current_agent": agent,
            "repo_url": self.repo_url,
            "repo_name": self.repo_name,
            "board_slug": self.board_slug,
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            **extra,
        }
        (self.session_path / "status.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="core.session",
        description="Seed the Dev-Booth scenario DAG onto a Hermes Kanban board.",
    )
    parser.add_argument("session", help="session name (also the board slug)")
    parser.add_argument("repo_url", help="GitHub repo URL to fork/clone/improve")
    parser.add_argument("--goal", default="코드 품질 개선 및 버그 수정", help="session goal")
    args = parser.parse_args(argv)

    session = DevBoothSession(args.session, args.repo_url, goal=args.goal)
    session.setup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
