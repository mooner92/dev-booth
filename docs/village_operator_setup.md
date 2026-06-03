# Dev-Booth Village — Operator setup TODO

This file documents the sudo-only steps required to fully publish the
Star-Office-UI–powered Village over the public domain. The Ralph automation
installed everything that did **not** require sudo. The remaining items below
must be executed by an operator with sudo on `data05lx`.

---

## 1. (Optional) Move install from `~/star-office-ui` to `/opt/star-office-ui`

Ralph installed the Star-Office-UI repo at:

- `~mooner92/star-office-ui` — repo + state.json + agents-state.json + devbooth_sync.py

Plan’s original target was `/opt/star-office-ui`. If a system-wide path is
preferred:

```bash
sudo rsync -a /home/mooner92/star-office-ui/ /opt/star-office-ui/
sudo chown -R mooner92:mooner92 /opt/star-office-ui
```

Then update the user systemd units (or rewrite as `/etc/systemd/system/*`) to
the new path before reloading.

---

## 2. Promote user services → system services (recommended for prod)

Currently running as **user** services for `mooner92`:

- `~/.config/systemd/user/star-office-ui.service`
- `~/.config/systemd/user/star-office-sync.service`

They will only stay up while the user has a login session **or** if linger is
enabled:

```bash
sudo loginctl enable-linger mooner92
```

For full system-level promotion (survives reboots without any user login):

```bash
sudo cp /home/mooner92/.config/systemd/user/star-office-ui.service   /etc/systemd/system/
sudo cp /home/mooner92/.config/systemd/user/star-office-sync.service /etc/systemd/system/

# Patch [Service] block to run as user mooner92
sudo sed -i 's|^\[Service\]|[Service]\nUser=mooner92\nGroup=mooner92|' \
  /etc/systemd/system/star-office-ui.service \
  /etc/systemd/system/star-office-sync.service

sudo systemctl daemon-reload
sudo systemctl --user disable star-office-ui star-office-sync 2>/dev/null || true
sudo systemctl enable --now star-office-ui star-office-sync

curl -sf http://127.0.0.1:19000/health
```

---

## 3. Cloudflare Tunnel ingress: `village.excusa.uk` → `127.0.0.1:19000`

The existing tunnel config lives at `/etc/cloudflared/config.yml`. Add this
ingress rule **above** the catch-all `service: http_status:404` entry:

```yaml
ingress:
  # …existing rules…
  - hostname: village.excusa.uk
    service: http://localhost:19000
  - service: http_status:404
```

Then reload and add the DNS route:

```bash
sudo cloudflared tunnel route dns <tunnel-name-or-id> village.excusa.uk
sudo systemctl restart cloudflared
```

Verify:

```bash
curl -sI https://village.excusa.uk/health
```

The new `/village` page in the dashboard frontend auto-resolves the iframe
target:

- `localhost` / `127.0.0.1` / `192.168.x.x` / `10.x.x.x` → `http://<host>:19000`
- anything else (`dashboard.excusa.uk`, etc.) → `https://village.excusa.uk`

---

## 4. Production hardening (when going public)

`/etc/systemd/system/star-office-ui.service` should grow these env vars
before exposing the tunnel to the internet:

```ini
Environment=STAR_OFFICE_ENV=production
Environment=FLASK_SECRET_KEY=<>=24 char random>
Environment=ASSET_DRAWER_PASS=<strong drawer password, NOT 1234>
```

Then `sudo systemctl restart star-office-ui` — the backend will refuse to
boot if either secret is weak.

---

## 5. Reference

- Star-Office-UI upstream: <https://github.com/ringhyacinth/Star-Office-UI>
- Backend endpoints: `/health`, `/status`, `/agents`, `/set_state`, `/join-agent`, `/agent-push`
- Dev-Booth sync: `devbooth_sync.py` rewrites `agents-state.json` every 2s
  from `~/.hermes/kanban/boards/<latest>/kanban.db`
