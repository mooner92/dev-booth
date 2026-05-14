"""Metrics router — preset-only proxy (A15)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..services.models import MetricsSnapshot
from ..services.prometheus_proxy import PRESETS, PrometheusProxy
from ..services.session_hub import COUNTERS

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/preset/{name}", response_model=MetricsSnapshot)
async def get_preset(name: str, request: Request) -> MetricsSnapshot:
    if name not in PRESETS:
        raise HTTPException(status_code=404, detail=f"unknown preset {name!r}")
    proxy: PrometheusProxy = request.app.state.prometheus
    return await proxy.query(name)


@router.get("/internal")
async def internal_counters() -> dict:
    return COUNTERS.snapshot()
