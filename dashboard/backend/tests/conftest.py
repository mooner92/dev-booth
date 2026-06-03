"""Shared pytest fixtures — overrides SESSIONS_ROOT to a tmp_path so unit
tests never touch the real /dev-booth/sessions directory.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture()
def tmp_sessions_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "sessions"
    root.mkdir()
    from dashboard.backend import config
    monkeypatch.setattr(config, "SESSIONS_ROOT", root)
    return root


@pytest.fixture()
def make_session(tmp_sessions_root: Path):
    def _factory(name: str, messages: list[dict] | None = None, queue_files: dict[tuple[str, str], int] | None = None) -> Path:
        session_root = tmp_sessions_root / name
        log_dir = session_root / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "messages.jsonl"
        if messages:
            with log_path.open("w", encoding="utf-8") as fh:
                for msg in messages:
                    fh.write(json.dumps(msg, ensure_ascii=False) + "\n")
        else:
            log_path.touch()
        queues_root = session_root / "queues"
        if queue_files:
            for (agent, state), count in queue_files.items():
                qdir = queues_root / agent / state
                qdir.mkdir(parents=True, exist_ok=True)
                for i in range(count):
                    (qdir / f"msg_{i}.json").write_text(json.dumps({"i": i}))
        else:
            for agent in ("conductor", "architect", "executor"):
                for state in ("inbox", "processing", "processed", "dead"):
                    (queues_root / agent / state).mkdir(parents=True, exist_ok=True)
        return session_root

    return _factory


@pytest.fixture()
def sample_awg_message():
    return {
        "id": "test-uuid-1",
        "kind": "instruction",
        "from": "conductor",
        "to": "architect",
        "body": "프로젝트 분석을 시작해주세요.",
        "refs": {},
        "priority": 50,
        "createdAt": "2026-05-14T01:00:00Z",
        "createdAtMs": 1778500800000,
    }
