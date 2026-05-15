"""Session REST endpoints."""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel

from .. import config
from ..services import awg_inspector, session_layout, session_registry
from ..services.log_tailer import iter_log_file, make_seq
from ..services.models import (
    FileContent,
    FileNode,
    FileTree,
    LogPage,
    QueueDepth,
    SessionDetail,
    SessionSummary,
    StatusSnapshot,
)
from ..services.path_guard import safe_session_path
from ..services.stage_mapper import StageTracker

router = APIRouter(prefix="/api", tags=["sessions"])


class SessionStartRequest(BaseModel):
    session_name: str
    repo_url: str
    goal: str = "코드 품질 개선 및 버그 수정"
    mode: Literal["dryrun", "live"] = "dryrun"


def _run_session_seed(session_name: str, repo_url: str, goal: str, dryrun: bool) -> None:
    env = os.environ.copy()
    env["DEV_BOOTH_DRYRUN"] = "1" if dryrun else "0"
    try:
        subprocess.run(
            ["/dev-booth/env/bin/python3", "-m", "core.session",
             session_name, repo_url, "--goal", goal],
            cwd="/dev-booth", env=env, timeout=300, capture_output=True, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass  # best-effort; UI will see the session dir appear if seed succeeded


@router.post("/sessions/start")
async def start_session(
    body: SessionStartRequest, background_tasks: BackgroundTasks, request: Request
) -> dict:
    slug = body.session_name.strip().lower().replace(" ", "-").replace("_", "-")
    if not slug or not slug.replace("-", "").isalnum():
        raise HTTPException(400, "세션명은 영문/숫자/하이픈만 가능합니다")
    sessions_root = Path(os.environ.get("DEVBOOTH_SESSIONS_ROOT", "/dev-booth/sessions"))
    session_path = sessions_root / slug
    if session_path.exists():
        raise HTTPException(409, f"세션 '{slug}' 이미 존재합니다")
    dryrun = body.mode != "live"
    background_tasks.add_task(_run_session_seed, slug, body.repo_url, body.goal, dryrun)
    return {"session_name": slug, "status": "starting"}


def _registry(request: Request) -> session_registry.SessionListCache:
    return request.app.state.session_registry


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(request: Request) -> list[SessionSummary]:
    return _registry(request).list()


@router.get("/sessions/{name}", response_model=SessionDetail)
async def get_session(name: str, request: Request) -> SessionDetail:
    try:
        layout = session_layout.resolve(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not layout.root.exists():
        raise HTTPException(status_code=404, detail="session not found")
    status = _build_status(layout)
    try:
        mtime = layout.root.stat().st_mtime
        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        last_modified = None
    return SessionDetail(
        name=layout.name,
        root=str(layout.root),
        has_log=layout.has_log,
        has_queues=layout.has_queues,
        agents=list(layout.agents),
        last_modified=last_modified,
        status=status,
    )


@router.get("/sessions/{name}/status", response_model=StatusSnapshot)
async def get_status(name: str, request: Request) -> StatusSnapshot:
    layout = _resolve_or_404(name)
    # Prefer SessionHub cached status if a hub already exists
    hubs = getattr(request.app.state, "hub_registry", None)
    if hubs is not None:
        hub = hubs._hubs.get(name)  # noqa: SLF001 — internal access is fine
        if hub is not None and hub.status_cache is not None:
            return hub.status_cache
    return _build_status(layout)


@router.get("/sessions/{name}/files", response_model=FileTree)
async def list_files(name: str) -> FileTree:
    layout = _resolve_or_404(name)
    root_node, truncated = _build_tree(layout.root, layout.root, max_entries=config.MAX_TREE_ENTRIES)
    return FileTree(session=layout.name, root=root_node, truncated=truncated)


@router.get("/sessions/{name}/file", response_model=FileContent)
async def read_file(
    name: str,
    path: str = Query(..., description="Path relative to session root"),
) -> FileContent:
    layout = _resolve_or_404(name)
    target = safe_session_path(config.SESSIONS_ROOT, layout.name, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    size = target.stat().st_size
    head = target.open("rb").read(1024)
    is_binary = b"\x00" in head
    if is_binary:
        return FileContent(session=layout.name, path=path, size=size, binary=True)
    truncated = size > config.MAX_FILE_BYTES
    content = target.open("rb").read(config.MAX_FILE_BYTES).decode("utf-8", errors="replace")
    return FileContent(
        session=layout.name,
        path=path,
        size=size,
        binary=False,
        truncated=truncated,
        content=content,
    )


@router.get("/sessions/{name}/logs", response_model=LogPage)
async def get_logs(
    name: str,
    after: str | None = Query(default=None, description="composite seq inode:offset"),
    limit: int = Query(default=200, ge=1, le=config.MAX_LOG_LINES_PER_REQUEST),
) -> LogPage:
    layout = _resolve_or_404(name)
    if not layout.has_log:
        return LogPage(session=layout.name, entries=[], next_after=None, has_more=False)
    try:
        st = layout.log_path.stat()
    except FileNotFoundError:
        return LogPage(session=layout.name, entries=[], next_after=None, has_more=False)

    inode = st.st_ino
    requested_inode: int | None = None
    requested_offset: int | None = None
    if after:
        try:
            req_inode_s, _, req_off_s = after.partition(":")
            requested_inode = int(req_inode_s)
            requested_offset = int(req_off_s)
        except ValueError:
            requested_inode = None
            requested_offset = None

    entries = []
    line_count = 0
    next_seq: str | None = None
    has_more = False

    with layout.log_path.open("rb") as fh:
        if requested_inode == inode and requested_offset is not None:
            fh.seek(requested_offset)
        elif requested_inode is not None and requested_inode != inode:
            # rotation since the requested seq → start from beginning
            fh.seek(0)
        while True:
            offset = fh.tell()
            raw = fh.readline()
            if not raw:
                break
            if not raw.endswith(b"\n"):
                break
            try:
                from json import loads
                data = loads(raw.decode("utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                data = {"body": raw.decode("utf-8", errors="replace").rstrip("\n"), "_parse_error": True}
            from ..services.models import LogEntry as _LE
            entry = _LE.model_validate(data)
            object.__setattr__(entry, "_offset", offset)
            entries.append(entry)
            line_count += 1
            if line_count >= limit:
                next_seq = make_seq(inode, fh.tell())
                has_more = fh.tell() < st.st_size
                break

    return LogPage(
        session=layout.name,
        entries=entries,
        next_after=next_seq or make_seq(inode, st.st_size),
        has_more=has_more,
    )


@router.get("/sessions/{name}/queues", response_model=dict[str, QueueDepth])
async def get_queues(name: str) -> dict[str, QueueDepth]:
    layout = _resolve_or_404(name)
    return awg_inspector.queue_depths(layout.root, layout.agents or None)


# ----------------------------------------------------------------- helpers
def _resolve_or_404(name: str) -> session_layout.SessionLayout:
    try:
        layout = session_layout.resolve(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not layout.root.exists():
        raise HTTPException(status_code=404, detail="session not found")
    return layout


def _build_status(layout: session_layout.SessionLayout) -> StatusSnapshot:
    depths = awg_inspector.queue_depths(layout.root, layout.agents or None)
    tracker = StageTracker()
    last_active = None
    last_agent: str | None = None
    if layout.has_log:
        # Best-effort cold derive: scan up to last 200 entries to seed stage tracker.
        # Avoid full-file scan; this is bounded.
        entries: list[Any] = []
        try:
            for entry in iter_log_file(layout.log_path):
                entries.append(entry)
                if len(entries) > 200:
                    entries.pop(0)
        except OSError:
            entries = []
        for entry in entries:
            if entry.body and entry.created_at_ms is not None:
                tracker.observe(entry.body, entry.created_at_ms)
        if entries:
            last_active = entries[-1].created_at
            last_agent = entries[-1].from_

    stage_no = 0
    stage_id: str | None = None
    current = tracker.current()
    if current:
        stage_no, stage_id = current

    any_running = any(d.inbox + d.processing > 0 for d in depths.values())
    if any_running:
        state = "running"
    elif layout.has_log:
        state = "idle"
    else:
        state = "unknown"

    return StatusSnapshot(
        session=layout.name,
        state=state,
        current_stage=stage_no,
        current_stage_id=stage_id,
        current_agent=last_agent,
        last_active_at=last_active,
        queues=depths,
    )


def _build_tree(root: Path, base: Path, max_entries: int, depth: int = 0) -> tuple[FileNode, bool]:
    truncated = False

    def make_node(path: Path) -> FileNode:
        try:
            stat = path.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
        except OSError:
            stat = None
            mtime = None
        return FileNode(
            name=path.name or path.as_posix(),
            path=str(path.relative_to(base)) if path != base else "",
            is_dir=path.is_dir(),
            size=stat.st_size if (stat and path.is_file()) else None,
            modified_at=mtime,
        )

    if not root.is_dir():
        return make_node(root), False

    node = make_node(root)
    children: list[FileNode] = []
    count = 0

    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        entries = []

    for entry in entries:
        if entry.is_symlink():
            link_target = entry.resolve()
            if not link_target.is_relative_to(base.resolve()):
                continue
        if count >= max_entries:
            truncated = True
            break
        if entry.is_dir():
            if depth < 6:
                child, sub_trunc = _build_tree(entry, base, max_entries - count, depth + 1)
                truncated = truncated or sub_trunc
                children.append(child)
            else:
                children.append(make_node(entry))
            count += 1
        else:
            children.append(make_node(entry))
            count += 1

    node.children = children
    return node, truncated
