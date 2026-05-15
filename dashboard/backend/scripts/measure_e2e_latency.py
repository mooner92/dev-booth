#!/usr/bin/env python3
"""Measure end-to-end latency for the log → WebSocket path.

For each of N iterations:
  1. Append a timestamped LogEntry to the tail of an isolated session log.
  2. Receive it over a WebSocket subscribed to that session.
  3. Record (recv_time - send_time).

Reports p50 / p95 / max. Acceptance: p95 ≤ AC_LATENCY_LOCAL_P95_MS.

Usage:
    python scripts/measure_e2e_latency.py --session test-awg --count 100
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx
import websockets


async def measure(session: str, count: int, base_url: str, ws_url: str) -> tuple[list[float], int]:
    sessions_root = Path("/dev-booth/sessions") / session
    log_path = sessions_root / "log" / "messages.jsonl"
    if not log_path.exists():
        raise SystemExit(f"log file does not exist: {log_path}")

    received: dict[str, float] = {}

    async def consume(ws):
        while True:
            data = await ws.recv()
            msg = json.loads(data)
            if msg.get("type") == "log":
                marker = (msg.get("entry") or {}).get("id")
                if marker and marker.startswith("e2e-"):
                    received[marker] = time.monotonic()

    async with websockets.connect(f"{ws_url}/ws/{session}", ping_interval=None) as ws:
        # hello + subscribe
        hello = json.loads(await ws.recv())
        assert hello["type"] == "hello"
        await ws.send(json.dumps({"type": "subscribe"}))

        consumer = asyncio.create_task(consume(ws))
        send_times: dict[str, float] = {}
        for i in range(count):
            marker = f"e2e-{i}"
            entry = {
                "id": marker,
                "kind": "instruction",
                "from": "conductor",
                "to": "architect",
                "body": f"latency probe #{i}",
                "createdAt": "2026-05-14T03:00:00Z",
                "createdAtMs": int(time.time() * 1000),
            }
            send_times[marker] = time.monotonic()
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            await asyncio.sleep(0.05)

        # Wait up to 5s for the last one to arrive
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and len(received) < count:
            await asyncio.sleep(0.05)
        consumer.cancel()

        latencies = [
            (received[k] - send_times[k]) * 1000.0
            for k in send_times.keys() if k in received
        ]
        missing = count - len(received)
        return latencies, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="test-awg")
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--base-url", default="http://127.0.0.1:7001")
    ap.add_argument("--ws-url", default="ws://127.0.0.1:7001")
    args = ap.parse_args()

    latencies, missing = asyncio.run(measure(args.session, args.count, args.base_url, args.ws_url))
    if not latencies:
        raise SystemExit("no entries received over WebSocket")
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) >= 20 else latencies[-1]
    print(f"count={len(latencies)} missing={missing} p50={p50:.1f}ms p95={p95:.1f}ms max={latencies[-1]:.1f}ms")
    # Pass criterion is informational here; the assertion belongs in CI.
    if p95 > 500:
        print("WARN: p95 exceeded 500ms local AC")


if __name__ == "__main__":
    main()
