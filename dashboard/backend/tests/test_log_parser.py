"""Test the LogEntry model against the real AWG schema."""
from __future__ import annotations

import json
from pathlib import Path

from dashboard.backend.services.log_tailer import iter_log_file
from dashboard.backend.services.models import LogEntry


def test_log_entry_parses_real_schema(sample_awg_message):
    entry = LogEntry.model_validate(sample_awg_message)
    assert entry.id == "test-uuid-1"
    assert entry.kind == "instruction"
    assert entry.from_ == "conductor"
    assert entry.to == "architect"
    assert entry.body.startswith("프로젝트")
    assert entry.created_at_ms == 1778500800000
    assert entry.agent == "conductor"


def test_log_entry_round_trip(sample_awg_message):
    entry = LogEntry.model_validate(sample_awg_message)
    dumped = entry.model_dump(by_alias=True, exclude_none=True)
    assert dumped["from"] == "conductor"
    assert "createdAt" in dumped
    assert "createdAtMs" in dumped


def test_iter_log_file(tmp_path: Path, sample_awg_message):
    p = tmp_path / "messages.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for i in range(5):
            msg = dict(sample_awg_message, id=f"id-{i}")
            fh.write(json.dumps(msg, ensure_ascii=False) + "\n")
    entries = list(iter_log_file(p))
    assert len(entries) == 5
    assert all(e.from_ == "conductor" for e in entries)
    assert entries[3].id == "id-3"


def test_iter_log_file_handles_bad_json(tmp_path: Path):
    p = tmp_path / "messages.jsonl"
    p.write_text('{"id":"good","body":"ok"}\nnot json\n{"id":"good2","body":"ok2"}\n', encoding="utf-8")
    entries = list(iter_log_file(p))
    assert len(entries) == 3
    assert entries[1].body == "not json"
