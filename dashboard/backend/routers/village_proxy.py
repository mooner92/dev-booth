"""Same-origin reverse proxy for Star-Office-UI.

The `/village/` iframe targets `/api/village-iframe/` so the browser never
reaches Star-Office-UI directly on port 19000 (which is bound to 0.0.0.0
but blocked from other LAN hosts by the host firewall). This also means
the iframe works identically over Cloudflare (`dashboard.excusa.uk`)
without a separate tunnel for the Star-Office hostname.

HTML / JS / CSS / JSON responses get a path rewrite so Star-Office's
absolute references (`/static/...`, `/agents`, `/status`, etc.) route back
through this proxy. Binary assets pass through unchanged.
"""
from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, Request, Response

PROXY_PREFIX = "/api/village-iframe"
UPSTREAM = "http://localhost:19000"

router = APIRouter(prefix=PROXY_PREFIX, tags=["village-proxy"])

_client = httpx.AsyncClient(
    base_url=UPSTREAM, follow_redirects=False, timeout=30.0,
)

# Star-Office-UI's known absolute paths. Anything quoted starting with one
# of these gets prefixed with PROXY_PREFIX inside text responses.
_ABS_PATHS = (
    "/static/", "/agents", "/status", "/health", "/yesterday-memo",
    "/set_state", "/join-agent", "/agent-push", "/agent-approve",
    "/agent-reject", "/leave-agent", "/assets/", "/electron-standalone",
    "/join", "/invite", "/config/",
)

_REWRITE_RE = re.compile(
    r"""(?P<q>["'`])(?P<path>(?:""" + "|".join(re.escape(p) for p in _ABS_PATHS) + r"""))"""
)

# Response headers we strip — content-length is wrong after rewrite, x-frame
# / CSP would block embedding in the dashboard.
_STRIP_HEADERS = {
    "content-length", "content-encoding", "transfer-encoding",
    "x-frame-options", "content-security-policy",
}


def _rewrite_text(content: bytes) -> bytes:
    text = content.decode("utf-8", errors="replace")
    text = _REWRITE_RE.sub(lambda m: f"{m.group('q')}{PROXY_PREFIX}{m.group('path')}", text)
    return text.encode("utf-8")


async def _proxy(path: str, request: Request) -> Response:
    upstream_path = "/" + path
    if request.url.query:
        upstream_path += "?" + request.url.query
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in {"host", "content-length", "content-encoding"}}
    body = await request.body() if request.method in {"POST", "PUT", "PATCH"} else None

    try:
        resp = await _client.request(request.method, upstream_path,
                                     headers=headers, content=body)
    except httpx.RequestError as exc:
        return Response(content=f"upstream unreachable: {exc}",
                        status_code=502, media_type="text/plain")

    content = resp.content
    ctype = resp.headers.get("content-type", "")
    if any(t in ctype for t in ("text/html", "javascript", "text/css", "application/json")):
        content = _rewrite_text(content)

    out_headers = {k: v for k, v in resp.headers.items()
                   if k.lower() not in _STRIP_HEADERS}
    return Response(content=content, status_code=resp.status_code,
                    headers=out_headers, media_type=ctype or None)


@router.api_route("/", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_root(request: Request) -> Response:
    return await _proxy("", request)


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_path(path: str, request: Request) -> Response:
    return await _proxy(path, request)
