"""US-005 / PM-2 — processing/ strand recovery via requeue_stale().

The real ``test-awg`` session ships with a message stranded in ``processing/``.
The orchestrator's ``setup()`` calls ``requeue_stale()`` so a strand left by a
crashed prior run is recovered into ``inbox/`` rather than deadlocking the loop.
"""
from __future__ import annotations

import json
import time

from agent_working_group import MessageQueue

AGENTS = ("openclaw", "hermes-a", "hermes-b")


def _place_in_processing(tmp_path, agent: str, body: str) -> str:
    """Send a message then receive(require_ack) so it lands in processing/."""
    mq = MessageQueue(str(tmp_path))
    mq.initialize(AGENTS)
    mq.send("openclaw", agent, "instruction", body)
    received = mq.receive(agent, timeout=2, require_ack=True)
    assert received is not None
    processing = tmp_path / "queues" / agent / "processing"
    assert len(list(processing.glob("*.json"))) == 1
    return received["id"]


def test_requeue_stale_recovers_a_strand(tmp_path):
    msg_id = _place_in_processing(tmp_path, "hermes-a", "stranded instruction")
    mq = MessageQueue(str(tmp_path))

    # older_than_sec=0 -> everything currently in processing is "stale"
    stats = mq.requeue_stale("hermes-a", older_than_sec=0)
    assert stats["requeued"] == 1
    assert stats["dead"] == 0

    inbox = tmp_path / "queues" / "hermes-a" / "inbox"
    processing = tmp_path / "queues" / "hermes-a" / "processing"
    assert len(list(inbox.glob("*.json"))) == 1
    assert len(list(processing.glob("*.json"))) == 0

    # the recovered message is consumable again
    again = mq.receive("hermes-a", timeout=2, require_ack=True)
    assert again is not None
    assert again["id"] == msg_id


def test_requeue_stale_noop_when_nothing_stranded(tmp_path):
    mq = MessageQueue(str(tmp_path))
    mq.initialize(AGENTS)
    stats = mq.requeue_stale("hermes-b", older_than_sec=0)
    assert stats == {"agent": "hermes-b", "requeued": 0, "dead": 0}


def test_fresh_message_not_requeued_with_default_window(tmp_path):
    _place_in_processing(tmp_path, "openclaw", "fresh instruction")
    mq = MessageQueue(str(tmp_path))
    # default 300s window -> a just-received message is NOT stale
    stats = mq.requeue_stale("openclaw")  # older_than_sec defaults to 300
    assert stats["requeued"] == 0
