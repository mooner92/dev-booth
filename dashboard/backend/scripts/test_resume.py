#!/usr/bin/env python3
"""Exercise resume_from across forced WebSocket reconnects."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import websockets


async def append(log_path: Path, marker: str) -> None:
    entry = {
        "id": marker,
        "kind": "instruction",
        "from": "conductor",
        "to": "architect",
        "body": f"resume probe {marker}",
        "createdAt": "2026-05-14T03:00:00Z",
        "createdAtMs": int(time.time() * 1000),
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def run(session: str, ws_url: str) -> int:
    log_path = Path("/dev-booth/sessions") / session / "log" / "messages.jsonl"
    if not log_path.exists():
        raise SystemExit(f"log not found: {log_path}")

    # Phase 1: connect, receive a few, capture last seq, then disconnect.
    last_seq = None
    received_ids: list[str] = []
    async with websockets.connect(f"{ws_url}/ws/{session}", ping_interval=None) as ws:
        await ws.recv()  # hello
        await ws.send(json.dumps({"type": "subscribe"}))
        for i in range(3):
            marker = f"resume-pre-{i}"
            await append(log_path, marker)
        # gather messages for 1s
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            try:
                data = await asyncio.wait_for(ws.recv(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            msg = json.loads(data)
            if msg.get("type") == "log":
                last_seq = msg.get("seq")
                received_ids.append(msg["entry"]["id"])

    # Phase 2: append more while disconnected.
    for i in range(3):
        await append(log_path, f"resume-during-{i}")

    # Phase 3: reconnect with resume_from = last_seq; expect the during-* entries.
    async with websockets.connect(f"{ws_url}/ws/{session}", ping_interval=None) as ws:
        await ws.recv()  # hello
        await ws.send(json.dumps({"type": "subscribe", "resume_from": last_seq}))
        replay: list[str] = []
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                data = await asyncio.wait_for(ws.recv(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            msg = json.loads(data)
            if msg.get("type") == "log":
                replay.append(msg["entry"]["id"])
            elif msg.get("type") == "reset":
                print("reset received:", msg.get("reason"))

    missed = [m for m in ("resume-during-0", "resume-during-1", "resume-during-2") if m not in replay]
    if missed:
        print(f"FAIL: missed {missed}; replay={replay}")
        return 1
    print(f"OK: replay seq received {replay}, last_seq before disconnect = {last_seq}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="test-awg")
    ap.add_argument("--ws-url", default="ws://127.0.0.1:7001")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.session, args.ws_url)))


if __name__ == "__main__":
    main()
