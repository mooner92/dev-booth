"""Pydantic models shared across services and routers.

The `LogEntry` schema mirrors the *actual* AWG message format observed at
``/dev-booth/sessions/test-awg/log/messages.jsonl``:

    {"id": "uuid", "kind": "instruction"|"response"|...,
     "from": "openclaw"|"hermes-a"|"hermes-b",
     "to":   "openclaw"|"hermes-a"|"hermes-b",
     "body": "<message>", "refs": {...},
     "priority": int, "createdAt": "ISO8601", "createdAtMs": int}

The plan's spec (``{time, agent, input, output}``) was unverified; we trust the
filesystem (Principle 1).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class LogEntry(BaseModel):
    """Single message line in messages.jsonl (AWG format)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: Optional[str] = None
    kind: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None
    body: Optional[str] = None
    refs: Optional[dict[str, Any]] = None
    priority: Optional[int] = None
    created_at: Optional[str] = Field(default=None, alias="createdAt")
    created_at_ms: Optional[int] = Field(default=None, alias="createdAtMs")

    # Server-side enrichment (not on disk)
    _line_no: Optional[int] = None
    _offset: Optional[int] = None

    @property
    def agent(self) -> Optional[str]:
        """For UI: the agent that *sent* this message."""
        return self.from_


class LogPage(BaseModel):
    session: str
    entries: list[LogEntry]
    next_after: Optional[str] = None  # composite seq (inode:offset)
    has_more: bool = False
    total_lines_estimate: Optional[int] = None


class QueueDepth(BaseModel):
    inbox: int = 0
    processing: int = 0
    processed: int = 0
    dead: int = 0


class StatusSnapshot(BaseModel):
    session: str
    state: Literal["running", "idle", "error", "unknown"] = "unknown"
    current_stage: int = 0  # 0 = none detected, 1..12 = stage
    current_stage_id: Optional[str] = None
    current_agent: Optional[str] = None
    last_active_at: Optional[str] = None
    queues: dict[str, QueueDepth] = Field(default_factory=dict)
    test_results: Optional[dict[str, int]] = None


class SessionSummary(BaseModel):
    name: str
    root: str
    has_log: bool
    has_queues: bool
    agents: list[str] = Field(default_factory=list)
    last_modified: Optional[str] = None


class SessionDetail(SessionSummary):
    status: StatusSnapshot
    repo_url: Optional[str] = None
    repo_name: Optional[str] = None
    branch: Optional[str] = None
    started_at: Optional[str] = None


class FileNode(BaseModel):
    name: str
    path: str  # relative to session root
    is_dir: bool
    size: Optional[int] = None
    modified_at: Optional[str] = None
    children: Optional[list["FileNode"]] = None


class FileTree(BaseModel):
    session: str
    root: FileNode
    truncated: bool = False


class FileContent(BaseModel):
    session: str
    path: str
    size: int
    binary: bool = False
    truncated: bool = False
    content: Optional[str] = None
    mime: Optional[str] = None


class MetricSeries(BaseModel):
    label: str
    points: list[tuple[float, float]] = Field(default_factory=list)  # (epoch_s, value)


class MetricsSnapshot(BaseModel):
    available: bool
    fetched_at: str
    series: dict[str, MetricSeries] = Field(default_factory=dict)
    error: Optional[str] = None


class HealthResponse(BaseModel):
    ok: bool = True
    version: str
    sessions_root: str


# WebSocket payloads are constructed as plain dicts (see backend/routers/ws.py
# and services/session_hub.py) and validated by TypeScript types on the client.
# Pydantic models for them would duplicate the schema without adding any
# server-side validation.


FileNode.model_rebuild()
