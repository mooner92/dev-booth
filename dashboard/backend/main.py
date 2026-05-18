"""FastAPI app entry point.

Run with:
    /dev-booth/env/bin/uvicorn backend.main:app --host 127.0.0.1 --port 7000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import github, health, kanban, metrics, sessions, village, village_proxy, ws
from .services.prometheus_proxy import PrometheusProxy
from .services.session_hub import HubRegistry
from .services.session_registry import SessionListCache


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session_registry = SessionListCache()
    app.state.hub_registry = HubRegistry()
    app.state.prometheus = PrometheusProxy()
    try:
        yield
    finally:
        await app.state.hub_registry.close_all()
        await app.state.prometheus.aclose()


app = FastAPI(
    title="Dev-Booth Dashboard",
    version=config.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.CORS_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(github.router)
app.include_router(metrics.router)
app.include_router(ws.router)
app.include_router(kanban.router)
app.include_router(village.router)
app.include_router(village_proxy.router)


# Mount frontend export if available (production single-port mode)
_static_dir = os.environ.get("DASHBOARD_STATIC_DIR")
if _static_dir:
    static_path = Path(_static_dir)
    if static_path.is_dir():
        from fastapi import Request as _Req
        from fastapi.responses import FileResponse as _FR

        @app.get("/session/{name:path}")
        async def _session_placeholder(name: str, request: _Req):
            # next-export emits one placeholder at /session/_/index.html;
            # serve it for any session name so client-side routing works.
            placeholder = static_path / "session" / "_" / "index.html"
            if placeholder.is_file():
                return _FR(str(placeholder))
            raise HTTPException(status_code=404, detail="placeholder not found")

        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="frontend")
