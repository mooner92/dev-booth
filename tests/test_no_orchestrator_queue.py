"""US-004 — the orchestrator's narration path never creates a queues/ directory.

Plan v3 P3/N4: routing orchestrator narration through ``MessageQueue.send()``
would ``mkdir`` ``queues/orchestrator/``, which the dashboard surfaces as a
phantom 4th agent. ``core/logger.py`` writes by direct append only.

This module proves the *logger* side of that invariant. The full end-to-end
check (after a real dryrun session, ``queues/`` contains exactly
``openclaw/hermes-a/hermes-b``) lives in the US-008 E2E suite.
"""
from __future__ import annotations

from core.logger import SessionLog, log_message


def test_logger_usage_creates_no_queues_dir(tmp_path):
    slog = SessionLog(tmp_path)
    for stage in range(1, 13):
        slog.narrate(stage, f"stage {stage} narration line")
    slog.broadcast("a broadcast line")
    log_message(tmp_path, "orchestrator", "all", "low-level call", kind="status")

    # the ONLY thing the logger may create is log/messages.jsonl
    assert (tmp_path / "log" / "messages.jsonl").is_file()
    assert not (tmp_path / "queues").exists()
    assert not (tmp_path / "queues" / "orchestrator").exists()


def test_orchestrator_id_never_becomes_a_queue_agent(tmp_path):
    """Even after heavy narration, no 'orchestrator' queue dir appears."""
    slog = SessionLog(tmp_path)
    for _ in range(50):
        slog.broadcast("heartbeat")
    children = {p.name for p in tmp_path.iterdir()}
    assert "queues" not in children
    assert children == {"log"}
