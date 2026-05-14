# Cloudflare Access Policy for `dashboard.excusa.uk`

Zero-Trust Application configuration. Apply in the Cloudflare Zero Trust
dashboard or via `cloudflared` Terraform provider.

## Application
- **Name**: `dev-booth-dashboard`
- **Domain**: `dashboard.excusa.uk`
- **Type**: Self-hosted
- **Session duration**: 24 hours
- **Allowed identity providers**: Google OAuth (or One-Time PIN as fallback)
- **App launcher visibility**: hidden

## Policy: `mooner92-only`
- **Action**: Allow
- **Include**:
  - Email: `mooner92@kakao.com`
- **Require**: (none)
- **Exclude**: (none)

## Degraded mode
If Cloudflare Access is unavailable, the Tunnel ingress still requires a
service token header. Absent token → 403. Set the service token in
`~/.cloudflared/config.yml`:

```yaml
ingress:
  - hostname: dashboard.excusa.uk
    service: http://127.0.0.1:7000
    originRequest:
      access:
        required: true
        teamName: <your-team>
        audTag:
          - <application-AUD-tag>
```

## Why this is read-only
The dashboard backend exposes only HTTP GET endpoints. Even if Access were
bypassed, no mutating action is possible — the FastAPI router refuses
non-GET verbs with 405. Filesystem access is constrained to
`/dev-booth/sessions/`.
