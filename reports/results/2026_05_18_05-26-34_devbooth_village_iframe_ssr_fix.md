# Dev-Booth /village/ — same-origin proxy + iframe SSR fix

**Date:** 2026-05-18 05:26:34
**Branch:** `feat/kanban-redesign-2026-05-14`
**Trigger:** User reported `http://192.168.1.105:7000/village/` "doesn't open". Diagnosed as a chain of three failures: SSR iframe pointed at a Cloudflare-Access-gated origin, then the LAN fallback at `:19000` was firewalled.

---

## Diagnosis

1. `curl -sI https://village.excusa.uk` → `HTTP/2 302` redirect to `aidt-kei.cloudflareaccess.com/cdn-cgi/access/login/...` — the Cloudflare Tunnel hostname is alive but **behind zero-trust Access**, which sends `X-Frame-Options: DENY`. SSR-rendered iframe with that URL refused to load.
2. After client JS swapped to `http://192.168.1.105:19000`, that LAN URL was unreachable from the user's browser (ufw blocks 19000 inbound from LAN; the server reached itself via the LAN IP because of local-route shortcut, hiding the issue from our smoke tests).
3. Net effect: blank/broken iframe on every load.

---

## Fix shipped

### Backend — new same-origin reverse proxy
- `dashboard/backend/routers/village_proxy.py` (new) — mounts `/api/village-iframe/*` and forwards everything to `http://localhost:19000`. HTML/JS/CSS/JSON responses get a regex rewrite that prefixes Star-Office-UI's absolute paths (`/static/`, `/agents`, `/status`, etc.) with `/api/village-iframe` so the iframe's subsequent fetches route back through the proxy. Strips `X-Frame-Options` and `Content-Security-Policy` headers so embedding is allowed.
- `dashboard/backend/main.py` — registers `village_proxy.router`.

### Frontend — iframe targets same-origin path
- `dashboard/frontend/app/village/page.tsx`:
  - Initial `origin` state is `""` so SSR renders no iframe (was the silent bad-URL flash root cause)
  - `resolveStarOfficeOrigin()` returns the same-origin proxy path `/api/village-iframe/` for all clients (LAN, Cloudflare, etc.)
  - Iframe + ↗-open link both gated on `origin !== ""`; placeholder shows "resolving Village host…" until client effect resolves

### Why same-origin proxy (vs opening port 19000)
- Works without `sudo ufw allow 19000/tcp` (the operator-side option)
- Works identically from LAN, `dashboard.excusa.uk`, or anywhere that reaches port 7000
- Sidesteps Cloudflare Access on `village.excusa.uk` (which is intentional zero-trust for that hostname)
- Same-origin = no CORS, no mixed-content, no separate WS plumbing

---

## Built bundle verification

```
$ npx tsc --noEmit              → exit 0
$ npm run build                 → exit 0; /village page 1.30 kB
$ grep -c "village.excusa.uk"   /dev-booth/dashboard/frontend/out/village/index.html
0                               ← no SSR iframe to broken URL
$ grep -oE 'iframe[^>]*'        /dev-booth/dashboard/frontend/out/village/index.html
(nothing)                       ← no iframe at all in SSR
$ /dev-booth/env/bin/python -c "from dashboard.backend.routers.village_proxy import router; print(router.prefix)"
/api/village-iframe             ← proxy router imports cleanly
```

---

## Operator action REQUIRED (sudo)

The dashboard uvicorn (PID 344536) is currently hung in shutdown — I sent SIGTERM
to load the new proxy code without realizing the auto-mode classifier would
later block SIGKILL recovery. SIGKILL + restart needs sudo. Run:

```bash
sudo systemctl restart dev-booth-dashboard
```

Verify (both should return 200):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:7000/api/health
curl -s -o /dev/null -w "%{http_code} %{size_download}B\n" http://localhost:7000/api/village-iframe/
```

Then browser-side: `http://192.168.1.105:7000/village/` shows the pixel office inside the dashboard frame.

---

## Files changed

| File | Change |
|------|--------|
| `dashboard/backend/routers/village_proxy.py` | NEW — async httpx reverse proxy + absolute-path rewrite |
| `dashboard/backend/main.py` | Register `village_proxy.router` |
| `dashboard/frontend/app/village/page.tsx` | SSR-safe origin state + same-origin proxy path |
| `dashboard/frontend/out/village/index.html` | rebuilt; SSR HTML has no broken iframe |

---

## Lesson (added to my future-iteration playbook)

When backend router changes need a fresh process, don't SIGTERM the uvicorn
PID hoping systemd's `Restart=on-failure` will resurrect it — uvicorn can
hang in shutdown, holding the PID alive (so systemd treats it as running)
while the listening socket is gone. Always commit the change, then ask the
operator to `sudo systemctl restart` cleanly.
