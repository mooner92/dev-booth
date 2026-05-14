from __future__ import annotations

import json
import os
from pathlib import Path

from dashboard.backend.services.log_tailer import (
    LogTailer,
    make_seq,
    parse_seq,
)


def _append(p: Path, msg: dict) -> None:
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(msg, ensure_ascii=False) + "\n")


def test_seq_roundtrip():
    s = make_seq(123, 4567)
    assert s == "123:4567"
    assert parse_seq(s) == (123, 4567)
    assert parse_seq("invalid") == (0, 0)


def test_tailer_reads_new_entries(tmp_path: Path):
    p = tmp_path / "messages.jsonl"
    p.touch()
    tailer = LogTailer(p)
    result = tailer.read_new()
    assert result.entries == []

    _append(p, {"id": "1", "body": "hello", "from": "openclaw"})
    _append(p, {"id": "2", "body": "world", "from": "hermes-a"})

    result = tailer.read_new()
    assert len(result.entries) == 2
    assert result.entries[0][1].id == "1"
    assert result.entries[1][1].id == "2"
    assert result.rotated is False

    # second call sees nothing new
    result = tailer.read_new()
    assert result.entries == []


def test_tailer_detects_rotation(tmp_path: Path):
    import shutil

    p = tmp_path / "messages.jsonl"
    _append(p, {"id": "1", "body": "first"})
    tailer = LogTailer(p)
    tailer.read_new()  # prime

    # rotate logrotate-style: rename old file then create fresh one. This
    # guarantees a new inode (Linux can reuse inodes on unlink+create).
    shutil.move(str(p), str(p.with_suffix(".jsonl.1")))
    _append(p, {"id": "2", "body": "after rotation"})

    result = tailer.read_new()
    assert result.rotated is True
    assert result.reset_signal is not None
    assert result.reset_signal["reason"] == "rotation"
    assert len(result.entries) == 1
    assert result.entries[0][1].id == "2"


def test_tailer_detects_truncate(tmp_path: Path):
    p = tmp_path / "messages.jsonl"
    _append(p, {"id": "1", "body": "first"})
    _append(p, {"id": "2", "body": "second"})
    tailer = LogTailer(p)
    tailer.read_new()

    # Truncate file in place (same inode)
    with p.open("w", encoding="utf-8") as fh:
        fh.write("")
    _append(p, {"id": "3", "body": "fresh"})

    result = tailer.read_new()
    assert result.rotated is True
    assert result.reset_signal is not None
    assert result.reset_signal["reason"] == "truncate"
    assert len(result.entries) == 1
    assert result.entries[0][1].id == "3"


def test_tailer_replay_from_within_ring(tmp_path: Path):
    p = tmp_path / "messages.jsonl"
    for i in range(5):
        _append(p, {"id": str(i), "body": f"msg-{i}"})
    tailer = LogTailer(p)
    result = tailer.read_new()
    seqs = [s for s, _ in result.entries]
    # ask for everything after the 2nd entry
    replay, reset = tailer.replay_from(seqs[1])
    assert reset is None
    # Should return entries with index 2,3,4 (after seq[1])
    assert len(replay) == 3
    assert [e.id for _, e in replay] == ["2", "3", "4"]


def test_tailer_replay_from_invalid_inode_returns_reset(tmp_path: Path):
    p = tmp_path / "messages.jsonl"
    _append(p, {"id": "1", "body": "x"})
    tailer = LogTailer(p)
    tailer.read_new()
    replay, reset = tailer.replay_from("99999:0")
    assert replay == []
    assert reset == "rotation"


def test_tailer_skips_partial_line(tmp_path: Path):
    p = tmp_path / "messages.jsonl"
    _append(p, {"id": "1", "body": "ok"})
    # Partial write (no trailing newline)
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"id":"2","body":"partial"')
    tailer = LogTailer(p)
    result = tailer.read_new()
    assert len(result.entries) == 1
    # Complete the partial line
    with p.open("a", encoding="utf-8") as fh:
        fh.write('}\n')
    result = tailer.read_new()
    assert len(result.entries) == 1
    assert result.entries[0][1].id == "2"
