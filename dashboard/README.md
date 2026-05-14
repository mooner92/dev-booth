# Dev-Booth Dashboard

실시간 AI 에이전트 세션 모니터링 대시보드. FastAPI + Next.js 14 정적 export.

## 구조

```
dashboard/
├── backend/         # FastAPI + watchfiles + httpx (Python 3.11)
│   ├── main.py              # FastAPI app
│   ├── config.py            # 모든 매직 넘버
│   ├── routers/             # REST + WebSocket
│   ├── services/            # session_layout / log_tailer / stage_mapper ...
│   ├── tests/               # pytest 37건
│   ├── scripts/             # smoke / latency / resume
│   └── requirements.txt
├── frontend/        # Next.js 14 App Router + TS + Tailwind + shadcn
│   ├── app/                 # /, /session/[name] (placeholder + 클라이언트 라우팅)
│   ├── components/          # AppHeader / SessionCard / ChatStream / MonacoModal ...
│   ├── lib/                 # api / ws / constants / utils
│   ├── types/               # 백엔드 모델 미러
│   └── public/fonts/        # Pretendard (현재 next/font 시스템 폴백)
└── ops/             # systemd / cloudflared / journald / Access 정책
```

## 빠른 시작 (개발)

### 1. 백엔드

```bash
/dev-booth/env/bin/pip install -r dashboard/backend/requirements.txt
PYTHONPATH=/dev-booth /dev-booth/env/bin/uvicorn \
    dashboard.backend.main:app --host 127.0.0.1 --port 7001 --reload
```

확인:
```bash
curl http://127.0.0.1:7001/api/health
# {"ok":true,"version":"0.1.0","sessions_root":"/dev-booth/sessions"}
```

### 2. 프론트엔드 (dev)

```bash
cd dashboard/frontend
npm install
npm run dev          # http://localhost:3001
```

`next.config.mjs`에 dev-only rewrites가 들어있어 `/api/*` 와 `/ws/*`가
백엔드 :7001 로 프록시됩니다.

### 3. 프론트엔드 빌드 (prod)

```bash
cd dashboard/frontend
npm run build        # → out/
```

정적 export 산출물은 `frontend/out/` 입니다.

### 4. 단일 포트 통합 실행

백엔드를 띄울 때 `DASHBOARD_STATIC_DIR` 환경변수를 주면 같은 포트(7000)에서
정적 자산을 함께 서빙합니다. `/session/<name>/` 같은 동적 라우트는
`session/_/index.html` placeholder로 폴백되며, 클라이언트가 URL에서 실제
세션명을 읽어 동작합니다.

```bash
DASHBOARD_STATIC_DIR=/dev-booth/dashboard/frontend/out \
PYTHONPATH=/dev-booth /dev-booth/env/bin/uvicorn \
    dashboard.backend.main:app --host 127.0.0.1 --port 7000
```

## 테스트

```bash
PYTHONPATH=/dev-booth /dev-booth/env/bin/pytest -q dashboard/backend/tests/
# 37 passed

bash dashboard/backend/scripts/smoke.sh       # REST endpoints
python dashboard/backend/scripts/test_resume.py
python dashboard/backend/scripts/measure_e2e_latency.py --count 100
```

`pnpm`이 설치되지 않은 환경이므로 Playwright 등 프런트엔드 e2e는 `npx`로
실행하세요:

```bash
cd dashboard/frontend
npx playwright test    # 브라우저 설치 후 실행
```

## 운영 배포

> `sudo` 권한이 필요한 단계는 운영자가 별도로 실행합니다.

1. `useradd --system --no-create-home devbooth`
2. 빌드 산출물 권한 부여: `chown -R devbooth:devbooth /dev-booth/dashboard/frontend/out`
3. systemd 유닛 설치: `cp ops/dev-booth-dashboard.service /etc/systemd/system/`
4. journald 한도: `cp ops/journald-devbooth.conf /etc/systemd/journald.conf.d/`
5. cloudflared ingress 갱신: `ops/cloudflared-ingress.yml` 참고
6. Cloudflare Access 정책: `ops/cloudflare-access-policy.md` 참고
7. 시작:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart systemd-journald
   sudo systemctl enable --now dev-booth-dashboard
   ```

## 폰트

`public/fonts/`에 Pretendard woff2가 없으면 시스템 폰트로 폴백합니다.
공식 배포(OFL 1.1)를 직접 받아 넣을 때는 `public/fonts/OFL.txt`에 라이선스를
함께 두세요. 이 코드베이스에는 라이선스 의무 위반을 피하기 위해 폰트를
체크인하지 않았습니다 — 운영자가 추가합니다.

## ADR 추적

다음 다섯 가지가 본 구현에 못 박혀 있습니다 (자세한 근거는
`/dev-booth/reports/plans/2026_05_14_02-39-23_dev_booth_dashboard_plan.md`).

- ADR-001: Cloudflare Tunnel WS Heartbeat 20s
- ADR-002: Next.js `output: "export"` + 클라이언트 전용 동적 라우트
- ADR-003: Runtime / Build 사용자 분리 (`devbooth` / `mooner92`)
- ADR-004: stage_mapper Unicode/언어 정책 (NFC + 한/영 + 60초 윈도우)
- ADR-005: 큐 경로 단일화 (`queues/`만 사용)
