"""US-005 — real AWG MessageQueue send -> receive -> ack roundtrip.

No mocking: exercises the actual ``agent_working_group.MessageQueue`` against a
tmp session dir, the same way the orchestrator uses it.
"""
from __future__ import annotations

import json

from agent_working_group import MessageQueue

AGENTS = ("openclaw", "hermes-a", "hermes-b")


def test_initialize_creates_exactly_the_three_agent_queues(tmp_path):
    mq = MessageQueue(str(tmp_path))
    mq.initialize(AGENTS)
    queue_dirs = {p.name for p in (tmp_path / "queues").iterdir() if p.is_dir()}
    assert queue_dirs == set(AGENTS)
    assert "orchestrator" not in queue_dirs
    assert (tmp_path / "log" / "messages.jsonl").is_file()


def test_send_receive_ack_roundtrip(tmp_path):
    mq = MessageQueue(str(tmp_path))
    mq.initialize(AGENTS)

    msg_id = mq.send("openclaw", "hermes-a", "instruction", "analyze the repo")
    assert msg_id

    # inbox has one message
    inbox = tmp_path / "queues" / "hermes-a" / "inbox"
    assert len(list(inbox.glob("*.json"))) == 1

    received = mq.receive("hermes-a", timeout=2, require_ack=True)
    assert received is not None
    assert received["from"] == "openclaw"
    assert received["to"] == "hermes-a"
    assert received["kind"] == "instruction"
    assert received["body"] == "analyze the repo"

    # require_ack moved it inbox -> processing
    assert len(list(inbox.glob("*.json"))) == 0
    processing = tmp_path / "queues" / "hermes-a" / "processing"
    assert len(list(processing.glob("*.json"))) == 1

    mq.ack("hermes-a", received["id"])
    # ack moved it processing -> processed
    assert len(list(processing.glob("*.json"))) == 0
    processed = tmp_path / "queues" / "hermes-a" / "processed"
    assert len(list(processed.glob("*.json"))) == 1


def test_send_appends_to_messages_jsonl(tmp_path):
    mq = MessageQueue(str(tmp_path))
    mq.initialize(AGENTS)
    mq.send("hermes-b", "openclaw", "answer", "done implementing")
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "log" / "messages.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert len(lines) == 1
    assert lines[0]["from"] == "hermes-b"
    assert lines[0]["kind"] == "answer"


def test_retry_requeues_a_processing_message(tmp_path):
    mq = MessageQueue(str(tmp_path))
    mq.initialize(AGENTS)
    mq.send("openclaw", "hermes-b", "instruction", "implement TASK-001")
    received = mq.receive("hermes-b", timeout=2, require_ack=True)
    assert received is not None

    # simulate a failed turn -> retry (nack) requeues it
    mq.retry("hermes-b", received["id"])
    inbox = tmp_path / "queues" / "hermes-b" / "inbox"
    processing = tmp_path / "queues" / "hermes-b" / "processing"
    assert len(list(inbox.glob("*.json"))) == 1
    assert len(list(processing.glob("*.json"))) == 0
