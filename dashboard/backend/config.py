"""Centralised configuration constants for the Dev-Booth dashboard backend.

Every magic number from the plan §3.3 Variables & Constants table lives here so
it can be tweaked without code spelunking, and pytest can override it through
``tests/conftest.py``.
"""
from __future__ import annotations

import os
from pathlib import Path

VERSION = "0.1.0"

# Filesystem roots
SESSIONS_ROOT: Path = Path(os.environ.get("DEVBOOTH_SESSIONS_ROOT", "/dev-booth/sessions")).resolve()

# Plan §3.3 said /dev-booth/awg/queues (global). Reality: queues live per-session
# at <SESSIONS_ROOT>/<name>/queues/<agent>/<state>/. ADR-005 still applies:
# we read ``queues/`` only, ignoring any ``awg/`` legacy subdir.
QUEUE_SUBDIR = "queues"
LOG_SUBDIR = "log"
LOG_FILENAME = "messages.jsonl"

# Session listing cache (A10)
SESSION_LIST_TTL_S: float = 5.0

# Log tailer (A8)
LOG_RING_SIZE: int = 1000
LOG_FILE_MAX_BYTES: int = 8 * 1024 * 1024
LOG_TAIL_INTERVAL_MS: int = 200
LOG_TAIL_DEBOUNCE_MS: int = 200

# WebSocket (A5, C5)
WS_HEARTBEAT_INTERVAL_S: float = 20.0
WS_IDLE_TIMEOUT_S: float = 60.0
WS_BROADCAST_QUEUE_MAX: int = 256
WS_TUNNEL_IDLE_LIMIT_S: float = 100.0  # informational

# stage_mapper (C1 / ADR-004)
STAGE_CONFLICT_WINDOW_S: float = 60.0

# AWG queue inspector
AWG_POLL_INTERVAL_S: float = 2.0
KNOWN_AGENTS: tuple[str, ...] = ("conductor", "architect", "executor")
QUEUE_STATES: tuple[str, ...] = ("inbox", "processing", "processed", "dead")

# Prometheus proxy
PROMETHEUS_URL: str = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
PROM_PROXY_TIMEOUT_S: float = 3.0

# Read limits
MAX_FILE_BYTES: int = 8 * 1024 * 1024
MAX_TREE_ENTRIES: int = 5000
MAX_LOG_LINES_PER_REQUEST: int = 2000

# Acceptance criteria values (also referenced by tests)
AC_LATENCY_LOCAL_P95_MS: int = 500
AC_LATENCY_TUNNEL_P95_MS: int = 1500
AC_STAGE_ACCURACY_MIN: float = 0.9
AC_INITIAL_JS_GZIP_KB: int = 250
AC_MONACO_FIRST_OPEN_MS: int = 800

# CORS — dev only; production runs same-origin behind Cloudflare Tunnel
CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:3001",
    "http://localhost:7000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:7000",
)
