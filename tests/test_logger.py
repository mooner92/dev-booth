"""US-004 — core/logger.py: direct-append AWG-format writer."""
from __future__ import annotations

import ast
import json
import threading
from pathlib import Path

import pytest

from core import logger
from core.logger import SessionLog, log_message

_AWG_KEYS = {
    "id", "kind", "from", "to", "body", "refs", "priority",
    "createdAt", "createdAtMs",
}


def _read_lines(session: Path) -> list[dict]:
    log_file = session / "log" / "messages.jsonl"
    return [
        json.loads(ln)
        for ln in log_file.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


# --------------------------------------------------------------------------
# design constraint: NEVER import MessageQueue / agent_working_group
# (AST-based — docstrings/comments may *document* the constraint; what is
# forbidden is an actual import or a code-level reference.)
# --------------------------------------------------------------------------
def test_logger_does_not_import_message_queue():
    tree = ast.parse(Path(logger.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    code_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Name):
            code_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            code_names.add(node.attr)
    assert "agent_working_group" not in imported, "logger must not import AWG"
    assert "MessageQueue" not in code_names, "logger must not reference MessageQueue in code"


# --------------------------------------------------------------------------
# log_message — schema, append, defensive mkdir
# --------------------------------------------------------------------------
def test_log_message_appends_valid_awg_line(tmp_path):
    msg = log_message(tmp_path, "orchestrator", "all", "git clone done", kind="status")
    lines = _read_lines(tmp_path)
    assert len(lines) == 1
    written = lines[0]
    assert set(written.keys()) == _AWG_KEYS
    assert written == msg
    assert written["kind"] == "status"
    assert written["priority"] == 30
    assert written["from"] == "orchestrator"
    assert written["to"] == "all"
    assert written["body"] == "git clone done"
    assert written["refs"] == {}
    assert isinstance(written["createdAtMs"], int)
    assert written["createdAt"].endswith("Z")


def test_log_message_creates_log_dir_defensively(tmp_path):
    session = tmp_path / "fresh-session"
    # session dir does not exist yet
    log_message(session, "orchestrator", "all", "running tests", kind="status")
    assert (session / "log" / "messages.jsonl").is_file()


def test_log_message_appends_not_overwrites(tmp_path):
    log_message(tmp_path, "orchestrator", "all", "first", kind="status")
    log_message(tmp_path, "orchestrator", "all", "second", kind="note")
    lines = _read_lines(tmp_path)
    assert [m["body"] for m in lines] == ["first", "second"]
    assert lines[1]["priority"] == 10  # note


def test_log_message_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError, match="unknown kind"):
        log_message(tmp_path, "orchestrator", "all", "x", kind="bogus")


def test_log_message_never_creates_queues_dir(tmp_path):
    log_message(tmp_path, "orchestrator", "all", "anything", kind="status")
    assert not (tmp_path / "queues").exists(), "logger must never create queues/"


# --------------------------------------------------------------------------
# SessionLog wrapper
# --------------------------------------------------------------------------
def test_session_log_narrate_and_broadcast(tmp_path):
    slog = SessionLog(tmp_path)
    slog.narrate(1, "[STAGE 1/12: repo_clone] git clone of the target repo complete.")
    slog.broadcast("orchestrator heartbeat")
    lines = _read_lines(tmp_path)
    assert len(lines) == 2
    assert all(m["from"] == "orchestrator" for m in lines)
    assert all(m["to"] == "all" for m in lines)
    assert all(m["kind"] == "status" for m in lines)
    assert not (tmp_path / "queues").exists()


# --------------------------------------------------------------------------
# thread safety — concurrent appends produce N intact lines
# --------------------------------------------------------------------------
def test_concurrent_appends_are_atomic(tmp_path):
    n_threads = 12
    per_thread = 20

    def worker(tid: int):
        for i in range(per_thread):
            log_message(tmp_path, "orchestrator", "all", f"t{tid}-msg{i}", kind="status")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    log_file = tmp_path / "log" / "messages.jsonl"
    raw_lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == n_threads * per_thread
    # every line must be intact, parseable JSON (no torn writes)
    for ln in raw_lines:
        obj = json.loads(ln)
        assert set(obj.keys()) == _AWG_KEYS
