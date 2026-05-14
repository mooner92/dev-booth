"""Prometheus preset proxy (A15).

Free-form PromQL is **not** accepted — only the named presets below. This
defends against SSRF and resource-exhaustion via arbitrary queries.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from .. import config
from .models import MetricSeries, MetricsSnapshot


# Named preset queries
PRESETS: dict[str, str] = {
    "gpu_utilization": 'avg by (gpu) (DCGM_FI_DEV_GPU_UTIL)',
    "gpu_memory_used": 'avg by (gpu) (DCGM_FI_DEV_FB_USED)',
    "gpu_temperature": 'avg by (gpu) (DCGM_FI_DEV_GPU_TEMP)',
    "vllm_requests": 'sum(rate(vllm:request_success_total[1m]))',
    "dashboard_cpu": 'rate(process_cpu_seconds_total{job="dev-booth-dashboard"}[1m])',
}


class PrometheusProxy:
    def __init__(self, url: str = config.PROMETHEUS_URL, timeout: float = config.PROM_PROXY_TIMEOUT_S):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: dict[str, tuple[float, MetricsSnapshot]] = {}
        self._cache_ttl = 5.0

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _client_or_default(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def query(self, preset: str) -> MetricsSnapshot:
        if preset not in PRESETS:
            return MetricsSnapshot(
                available=False,
                fetched_at=_now_iso(),
                error=f"unknown preset: {preset}",
            )
        now = time.time()
        cached = self._cache.get(preset)
        if cached and (now - cached[0]) < self._cache_ttl:
            return cached[1]

        promql = PRESETS[preset]
        client = self._client_or_default()
        try:
            resp = await client.get(f"{self.url}/api/v1/query", params={"query": promql})
            resp.raise_for_status()
            data = resp.json()
            snapshot = MetricsSnapshot(
                available=True,
                fetched_at=_now_iso(),
                series=_parse_prometheus(data, preset),
            )
        except (httpx.HTTPError, ValueError) as exc:
            snapshot = MetricsSnapshot(
                available=False,
                fetched_at=_now_iso(),
                error=str(exc)[:200],
            )
        self._cache[preset] = (now, snapshot)
        return snapshot


def _parse_prometheus(data: dict, preset: str) -> dict[str, MetricSeries]:
    if data.get("status") != "success":
        return {}
    result = data.get("data", {}).get("result", [])
    out: dict[str, MetricSeries] = {}
    for item in result:
        metric = item.get("metric", {})
        label = ",".join(f"{k}={v}" for k, v in sorted(metric.items())) or preset
        value = item.get("value", [None, None])
        try:
            ts = float(value[0])
            v = float(value[1])
        except (TypeError, ValueError):
            continue
        out[label] = MetricSeries(label=label, points=[(ts, v)])
    return out


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")
