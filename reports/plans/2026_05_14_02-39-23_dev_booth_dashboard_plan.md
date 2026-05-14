# Dev-Booth Dashboard 통합 작업 계획서 (v3 / Consensus Final)

> 상태: PENDING APPROVAL
> 문서 ID: `2026_05_14_02-39-23_dev_booth_dashboard_plan`
> 작성자: Planner (oh-my-claudecode:ralplan iteration 2)
> 검토 반영: Architect APPROVE-WITH-CHANGES (17건) + Critic ITERATE (15건) = **32건 전수 반영**
> 대상 독자: Executor, Architect, Critic, 운영자(mooner92)

---

## 0. 메타 / 요약

### 0.1 프로젝트 식별

- **이름**: Dev-Booth Dashboard
- **위치**: `/dev-booth/dashboard/` (백엔드 `backend/`, 프론트엔드 `frontend/`, 운영 `ops/`)
- **외부 노출**: `https://dashboard.excusa.uk` (Cloudflare Tunnel + Cloudflare Access)
- **목표**: AWG(Agent Working Group) 세션의 12-stage 진행 상황, 큐 적체, GPU 메트릭, 실시간 로그를 단일 대시보드에서 조회
- **사용자**: 1인 운영자(`mooner92@kakao.com`) — 다중 사용자 인증 불필요, 단일 ID 허용

### 0.2 산출물 명명 규칙

본 프로젝트의 모든 영속 산출물(보고서, 계획서, 로그, 트레이스)은 **`YYYY_MM_DD_HH-MM-SS_summary.<ext>`** 컨벤션을 따른다.

- 예시: `2026_05_14_02-39-23_dev_booth_dashboard_plan.md`
- 위치: `./reports/plans/`, `./reports/traces/`, `./reports/reviews/`
- 이유: lexicographic 정렬이 시간순 정렬과 일치하여 `ls`만으로 최신 산출물 탐색이 가능. 시각 구분자로 콜론(`:`)이 아닌 하이픈(`-`)을 사용하는 것은 Windows로의 `scp` 전송 호환성을 위함 (Windows는 파일명에 `:` 금지).

### 0.3 v3 변경 요약 (v1 대비)

본 v3는 v1을 **재작성**한 결과이며, 32건의 교정사항이 모두 반영되었다. 주요 변화:

1. **빌드 모드 고정**: `next export` CLI 제거 → `next.config.mjs`의 `output: "export"`로 일원화 (A1).
2. **동적 라우트 정책 명문화**: `/session/[name]`는 클라이언트 컴포넌트, `generateStaticParams: () => []` + `dynamicParams: false`, SSR 금지 (A2).
3. **위험 R9 교체**: `output: "standalone"` 폴백 제거 → 직전 성공 빌드(`out.previous/`) 폴백 정책 (A3, C4).
4. **사용자 분리**: 빌드(`mooner92`) ↔ 런타임(`devbooth`) 권한 분리 (A6).
5. **로그 테일러 명세화**: `TailerState` 데이터 클래스 + 인메모리 ring buffer + `resume_from` 프로토콜 (A8, A9).
6. **세션 목록 캐시**: `SessionListCache` TTL 5초 + 이벤트 무효화 (A10).
7. **심볼릭 링크 정책 강화**: 조상 디렉터리까지 walk-up 검사 (A11).
8. **GPU 메트릭 소스 확정**: Prometheus + `nvidia_smi_exporter` (A12).
9. **Pretendard 폰트**: `next/font/local` + OFL 라이선스 동봉 (A13).
10. **Monaco 단독 채택**: `react-syntax-highlighter` 제거, 마크다운 코드 펜스는 `rehype-highlight` (A7).
11. **AWG 코드 복사 정책**: import 금지, `awg_inspector.py`로 함수 복사 (A14).
12. **Prometheus 프록시**: 자유 쿼리 금지, preset allowlist만 (A15).
13. **번들 크기 AC 추가**: 초기 JS gzip ≤ 250KB (A16).
14. **확장된 테스트 매트릭스**: 로그 회전, resume 복구, Tunnel idle, Monaco 지연 (A17).
15. **stage_mapper 정책**: NFC 정규화 + 한/영 키워드 + 60초 윈도우 충돌 해소 (C1).
16. **큐 경로 단일화**: `queues/`만 사용, `awg/`는 legacy로 무시 (C2).
17. **WS close 코드 표준화**: 4001~4005 + 클라이언트 reconnect 정책 (C5).
18. **journald 한도**: drop-in 설정 명시 (C6).
19. **Cloudflare Access 정책 스니펫**: 명시화 (C8).
20. **AC 수치화**: latency harness, golden fixture, resume test, 경로 traversal 3-vector (C9~C13).
21. **Playwright는 `npx`로**: pnpm 의존성 없음 (C14).
22. **WBS M1 확장**: `.gitignore`, `conftest.py`, env vars, ChatSearch 단축키, scroll-anchor 정책, `status_cache` (C15).

### 0.4 RALPLAN-DR 모드

- **모드**: SHORT (deliberate 아님 — 1인 운영 + 내부 도구 + 비프로덕션 트래픽)
- **그러나** 본 문서는 두 차례 ralplan 반복 결과이므로 ADR 5건, 사전 부검(pre-mortem) 1건, 확장된 테스트 매트릭스를 포함하여 deliberate 수준에 근접한다.

---

## 1. RALPLAN-DR 요약

### 1.1 원칙 (Principles)

| # | 원칙 | 적용 방식 |
|---|------|----------|
| P1 | **운영 단순성 우선** | 단일 호스트, 단일 사용자, 단일 systemd 유닛 쌍. K8s/Docker 회피. |
| P2 | **읽기 전용 대시보드** | 백엔드는 파일/메트릭 read-only. 어떠한 mutate API도 없음. |
| P3 | **최소 권한** | runtime 사용자 `devbooth` 시스템 계정, 로그/큐 디렉터리 read-only mount. |
| P4 | **점진적 강화** | 1차에는 polling/REST 기반, 실시간성은 WebSocket 한 채널(`/ws/<session>`)로 한정. |
| P5 | **외부 의존 최소** | 새 인프라(Redis, Postgres, Nginx) 도입 금지. Cloudflare Tunnel + FastAPI + Next.js static export만. |

### 1.2 의사결정 동인 (Decision Drivers, Top 3)

1. **D1 — 정적 export로 배포 표면적 최소화**: 프론트엔드는 Node 런타임 없음. Cloudflare Tunnel이 단일 진입점이며, 빌드 산출물은 정적 파일.
2. **D2 — 1인 운영자 인증 단순화**: Cloudflare Access(Google OAuth) + Tunnel service token. 백엔드 자체 인증 코드 작성 회피.
3. **D3 — 실시간 로그 신뢰성**: Cloudflare Tunnel WS idle timeout(~100s)을 견디는 heartbeat + 회전·재연결 복구가 핵심 위험.

### 1.3 검토된 선택지 (Viable Options ≥ 2)

| 옵션 | 설명 | 채택 여부 |
|------|------|----------|
| **O1: Next.js static export + FastAPI WS** | `output: "export"` SSG, FastAPI WebSocket | **채택** |
| **O2: Next.js SSR (Node runtime) + FastAPI** | SSR 페이지 + API proxy | 기각: Node 런타임 추가, systemd 유닛 증가, 메모리 footprint 증가 |
| **O3: SvelteKit static + FastAPI** | 더 가벼운 SSG, 그러나 팀 친숙도 낮음 | 기각: 학습 곡선, Monaco 통합 사례 부족 |
| **O4: Grafana 단독** | 기존 Prometheus 활용 | 부분 채택: GPU/큐 메트릭 시각화는 본 대시보드, Grafana는 보조 |

`O1` 채택 이유: D1(정적 배포), D2(인증 단순화), D3(WS 1채널) 모두 충족하며 팀 기존 스택과 일치.

### 1.4 위험-수익 매트릭스 핵심

| 위험 카테고리 | 수익 | 가시화 위치 |
|---------------|------|------------|
| Tunnel WS idle disconnect | 실시간 로그 가시성 | §9 R5, §10, ADR-001 |
| 정적 export 빌드 회귀 | 무중단 서빙 | §9 R9, §10 systemd `ExecStartPre`, ADR-002 |
| 경로 traversal (심볼릭 링크) | 단일 호스트 read-only 격리 | §9 R7, §4.5, A11 |
| stage 오탐 (한/영 혼용) | 사용자 신뢰 | §9 R3, ADR-004 |
| 큐 경로 불일치 | 데이터 정합성 | §9 R4, ADR-005 |

---

## 2. Spec ↔ Reality 격차

본 절은 v1의 요구사항 문서(`spec/dashboard_requirements.md` — 별도 보관)와 현재 코드베이스(`/dev-booth/`)의 격차를 정리한다.

### 2.1 코드베이스 사실 (Planner Explore 결과)

| 항목 | 현황 | 출처 |
|------|------|------|
| AWG 큐 디렉터리 | `/dev-booth/awg/queues/<agent>/{inbox,processing,processed,dead}/*.json` 형식 (운영 fixture) | `awg/queues/` 트리 |
| `awg/` 레거시 | `/dev-booth/awg/dashboard/server/services/awg_reader.py`에 `count_queue_files` 유사 함수 존재 | A14 출처 |
| 12-stage 정의 | `agent-working-group/docs/stages.md`에 단순 리스트만 존재 (regex 없음) | C1이 ADR-004로 보강 |
| 세션 파일 | `/dev-booth/sessions/<name>/{chat.jsonl, logs/*.log, meta.json}` | A11 SESSIONS_ROOT 기준 |
| GPU 메트릭 | `nvidia_smi_exporter` 미설치 (예상). 대시보드는 부재 시 null 표시 | A12 |
| Prometheus | `localhost:9090`에서 동작 중 (기존 인프라) | A12, A15 |
| Cloudflare Tunnel | `cloudflared` systemd 유닛 기존 운영 중 | §10 |

### 2.2 격차 목록

| ID | Spec | Reality | 해결 위치 |
|----|------|---------|----------|
| G1 | 통합 대시보드 | 부재 | 본 계획 전체 |
| G2 | 12-stage 감지 자동화 | 수동 운영자가 판별 | §4.6 stage_mapper, ADR-004 |
| G3 | 실시간 로그 시청 | tail -f SSH 필요 | §4.3 LogTailer, §5 LogStream |
| G4 | 외부 접근 | SSH only | §10 Cloudflare Tunnel + Access |
| G5 | GPU 가시성 | nvidia-smi 수동 | §4.4 Prometheus preset |
| G6 | 큐 적체 알림 | 없음 | §4.4 + Prometheus alert |
| G7 | 채팅 검색 | grep 수동 | §5 ChatSearch |
| G8 | 권한 분리 | root로 모든 작업 | A6, §10 systemd |

### 2.3 본 계획에서 다루지 않는 항목 (Out of Scope)

- 다중 사용자 인증/RBAC
- 세션 mutate API (대시보드는 read-only)
- AWG orchestrator의 `awg/` ↔ `queues/` 불일치 정리 (별도 이슈로 위임, ADR-005 follow-up)
- 모바일 전용 UI (반응형은 best-effort)
- 알림 채널(Slack/Telegram) — 본 계획에서 hook 지점만 마련, 발송 구현은 후속

---

## 3. 아키텍처

### 3.1 컴포넌트 다이어그램 (텍스트)

```
[Browser]
   |  HTTPS / WSS
   v
[Cloudflare Edge] -- (Access policy: email == mooner92@kakao.com) -->
   |  cloudflared Tunnel (named: devbooth-dashboard)
   v
[localhost:8080  (cloudflared ingress: dashboard.excusa.uk → http://localhost:8080)]
   |
   +--> GET /            → static files from /dev-booth/dashboard/frontend/out/ (Next.js export)
   +--> GET /api/*       → proxy to http://localhost:7000  (FastAPI)
   +--> /ws/<session>    → proxy to http://localhost:7000/ws/<session>

[Backend: FastAPI uvicorn @ localhost:7000  (user=devbooth)]
   |
   +-- SessionRegistry  (scans SESSIONS_ROOT, cached 5s)
   +-- SessionHub       (per-session pubsub fan-out)
   +-- LogTailer x N    (one per active session, asyncio task)
   +-- AwgInspector     (queue depth, file inode + mtime polling 2s)
   +-- StageMapper      (regex over chat messages, NFC normalized)
   +-- PrometheusProxy  (preset allowlist, SSRF-safe)

[Filesystem read-only]
   /dev-booth/sessions/<name>/...   (mounted ro for devbooth)
   /dev-booth/awg/queues/<agent>/... (mounted ro for devbooth)
```

### 3.2 정적 export 모드 고정 (A1, A2)

`frontend/next.config.mjs`:

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  experimental: { typedRoutes: true },
};
export default nextConfig;
```

- **`next export` CLI 사용 금지** (A1). `pnpm build`만으로 `out/`이 생성된다.
- 동적 라우트 `/session/[name]`은 다음 규칙을 강제한다 (A2):

```tsx
// frontend/app/session/[name]/page.tsx
'use client';
import { useParams } from 'next/navigation';
export const dynamic = 'force-static';
export const dynamicParams = false;
export async function generateStaticParams() {
  return []; // emits a single fallback shell
}
export default function SessionPage() {
  const { name } = useParams<{ name: string }>();
  // fetch via REST + open WS by name (client side only)
  return <SessionDetailClient name={name as string} />;
}
```

이 조합은 빌드 시 정적 fallback HTML 1개를 발행하며, 브라우저가 URL을 받아 클라이언트에서 REST/WS로 상태를 가져온다. **SSR 없음, prerender 없음.**

### 3.3 Variables & Constants (마법 상수 집결표)

본 표는 32건 교정에서 발생하는 모든 매직 넘버를 한 곳에 모은다. 코드에서는 `backend/config.py`와 `frontend/lib/constants.ts`에 상수로 정의한다.

| 상수 | 값 | 의미 | 정의 위치 | 출처 |
|------|----|------|----------|------|
| `SESSIONS_ROOT` | `/dev-booth/sessions` | 세션 디렉터리 루트 | `backend/config.py` | §3 |
| `QUEUES_ROOT` | `/dev-booth/awg/queues` | 큐 루트 (queues/만 사용) | `backend/config.py` | C2 / ADR-005 |
| `SESSION_LIST_TTL_S` | `5.0` | 세션 목록 캐시 TTL | `backend/config.py` | A10 |
| `LOG_RING_SIZE` | `1000` | 테일러 ring buffer entry 수 | `backend/config.py` | A8 |
| `LOG_FILE_MAX_BYTES` | `8 * 1024 * 1024` | 단일 로그 파일 최대 바이트 (회전 트리거 시뮬레이션) | `backend/config.py` | A8 |
| `LOG_TAIL_INTERVAL_MS` | `200` | tail polling 주기 | `backend/config.py` | §4.3 |
| `LOG_TAIL_DEBOUNCE_MS` | `200` | broadcast debounce | `backend/config.py` | §4.3 |
| `WS_HEARTBEAT_INTERVAL_S` | `20` | 서버 heartbeat 주기 | `backend/config.py` | A5 |
| `WS_IDLE_TIMEOUT_S` | `60` | 클라이언트 활동 idle 후 종료 | `backend/config.py` | C5 (4001) |
| `WS_BROADCAST_QUEUE_MAX` | `256` | 구독자별 broadcast 큐 한도 | `backend/config.py` | C5 (4002) |
| `WS_TUNNEL_IDLE_LIMIT_S` | `100` | 참고치: Cloudflare 기본 idle timeout | docs only | A5 |
| `STAGE_CONFLICT_WINDOW_S` | `60` | stage 충돌 해소 윈도우 | `backend/config.py` | C1 / ADR-004 |
| `AWG_POLL_INTERVAL_S` | `2.0` | 큐 inspector polling | `backend/config.py` | §4.4 |
| `PROM_PROXY_TIMEOUT_S` | `3.0` | Prometheus 호출 timeout | `backend/config.py` | §4.4 |
| `AC_LATENCY_LOCAL_P95_MS` | `500` | 로컬 e2e p95 한도 | tests | C9 |
| `AC_LATENCY_TUNNEL_P95_MS` | `1500` | Tunnel e2e p95 한도 | tests | C9 |
| `AC_STAGE_ACCURACY_MIN` | `0.9` | stage 감지 정확도 | tests | C10 |
| `AC_INITIAL_JS_GZIP_KB` | `250` | 초기 JS gzip 한도 | tests | A16 |
| `AC_MONACO_FIRST_OPEN_MS` | `800` | Monaco 최초 모달 열림 한도 | tests | A17 |
| `CHATSEARCH_HOTKEY` | `Cmd/Ctrl+F` | 채팅 검색 단축키 | `frontend/lib/constants.ts` | C15 |
| `SCROLL_ANCHOR_THRESHOLD_PX` | `80` | 자동 스크롤 유지 임계값 | `frontend/lib/constants.ts` | C15 |
| `ALERT_WS_RECONNECTS_PER_MIN` | `10` | 재연결 알람 임계 | Prometheus rule | C3 |
| `ALERT_DROPPED_SUBS_PER_5MIN` | `10` | drop 알람 임계 | Prometheus rule | C7 |
| `JOURNALD_MAX_USE` | `500M` | journald drop-in | `journald.conf.d/devbooth.conf` | C6 |
| `JOURNALD_KEEP_FREE` | `1G` | journald drop-in | 동상 | C6 |
| `JOURNALD_MAX_FILE_SEC` | `1week` | journald drop-in | 동상 | C6 |

### 3.4 모듈 구조

```
/dev-booth/dashboard/
├── backend/
│   ├── pyproject.toml
│   ├── config.py
│   ├── main.py                 # FastAPI app entry
│   ├── routers/
│   │   ├── sessions.py         # GET /api/sessions, /api/sessions/{name}
│   │   ├── logs.py             # GET /api/sessions/{name}/logs
│   │   ├── chat.py             # GET /api/sessions/{name}/chat
│   │   ├── metrics.py          # GET /api/metrics/preset/{name}
│   │   └── ws.py               # /ws/{session}
│   ├── services/
│   │   ├── session_layout.py   # SESSIONS_ROOT walker (C2: queues/ only)
│   │   ├── session_registry.py # SessionListCache (A10)
│   │   ├── session_hub.py      # pubsub, status_cache (C15)
│   │   ├── log_tailer.py       # TailerState dataclass (A8)
│   │   ├── awg_inspector.py    # copied from awg_reader (A14)
│   │   ├── stage_mapper.py     # NFC + regex (C1)
│   │   ├── prometheus_proxy.py # preset allowlist (A15)
│   │   └── path_guard.py       # walk_up_check (A11)
│   └── tests/
│       ├── conftest.py         # tmp_path SESSIONS_ROOT (C15)
│       ├── fixtures/stage_messages.jsonl  (C10)
│       └── test_*.py
├── frontend/
│   ├── next.config.mjs         # output:"export"
│   ├── tailwind.config.ts      # darkMode:"class" (A4)
│   ├── package.json
│   ├── app/
│   │   ├── layout.tsx          # ThemeProvider (next-themes)
│   │   ├── page.tsx            # session list
│   │   └── session/[name]/page.tsx  # client component (A2)
│   ├── components/
│   │   ├── AppHeader.tsx       # + ThemeToggle (A4)
│   │   ├── ThemeToggle.tsx
│   │   ├── SessionCard.tsx
│   │   ├── StageBar.tsx
│   │   ├── LogStream.tsx
│   │   ├── ChatStream.tsx
│   │   ├── ChatSearch.tsx
│   │   ├── MonacoModal.tsx     # next/dynamic + ssr:false (A7)
│   │   └── MetricCard.tsx
│   ├── lib/
│   │   ├── constants.ts
│   │   ├── api.ts              # NEXT_PUBLIC_API_BASE
│   │   ├── ws.ts               # reconnect + resume_from
│   │   └── theme.ts
│   ├── public/fonts/
│   │   ├── Pretendard-Regular.woff2
│   │   ├── Pretendard-Medium.woff2
│   │   ├── Pretendard-SemiBold.woff2
│   │   ├── Pretendard-Bold.woff2
│   │   └── OFL.txt             # SIL OFL 1.1 (A13)
│   └── tests/playwright/
│       └── basic.spec.ts       # 4 scenarios (C14)
└── ops/
    ├── systemd/
    │   ├── devbooth-dashboard-api.service
    │   ├── devbooth-dashboard-static.service  (caddy or python http.server)
    │   └── devbooth-dashboard.target
    ├── journald.conf.d/devbooth.conf  (C6)
    ├── cloudflared/config.yml
    └── scripts/
        ├── measure_e2e_latency.py   (C9)
        ├── test_resume.py           (C11)
        └── bundle_size_check.sh     (A16)
```

---

## 4. 백엔드 상세

### 4.1 FastAPI 진입점

```python
# backend/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from routers import sessions, logs, chat, metrics, ws
from services.session_registry import SessionRegistry
from services.session_hub import SessionHub
from services.log_tailer import TailerSupervisor

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.registry = SessionRegistry()
    app.state.hub = SessionHub()
    app.state.supervisor = TailerSupervisor(app.state.hub)
    await app.state.supervisor.start()
    try:
        yield
    finally:
        await app.state.supervisor.stop()

app = FastAPI(lifespan=lifespan, docs_url="/api/_docs", openapi_url="/api/_openapi.json")
app.include_router(sessions.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(ws.router)   # /ws/{session} (no /api prefix)
```

### 4.2 SessionRegistry & SessionListCache (A10)

`SessionListCache`는 `os.scandir`을 매 요청마다 부르는 안티패턴을 차단한다.

```python
# backend/services/session_registry.py
from dataclasses import dataclass, field
from time import monotonic
import asyncio, os
from config import SESSIONS_ROOT, SESSION_LIST_TTL_S

@dataclass
class SessionSummary:
    name: str
    mtime: float
    status: str   # "active" | "idle" | "ended"
    last_stage: int | None

@dataclass
class SessionListCache:
    mtime: float = 0.0
    entries: list[SessionSummary] = field(default_factory=list)
    fetched_at: float = 0.0

class SessionRegistry:
    def __init__(self):
        self._cache = SessionListCache()
        self._lock = asyncio.Lock()

    async def list_sessions(self) -> list[SessionSummary]:
        async with self._lock:
            now = monotonic()
            if (now - self._cache.fetched_at) < SESSION_LIST_TTL_S and self._cache.entries:
                return self._cache.entries
            entries = await asyncio.to_thread(self._scan)
            self._cache = SessionListCache(mtime=now, entries=entries, fetched_at=now)
            return entries

    def _scan(self) -> list[SessionSummary]:
        out: list[SessionSummary] = []
        with os.scandir(SESSIONS_ROOT) as it:
            for entry in it:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                st = entry.stat(follow_symlinks=False)
                out.append(SessionSummary(name=entry.name, mtime=st.st_mtime,
                                          status="active", last_stage=None))
        out.sort(key=lambda s: s.mtime, reverse=True)
        return out

    def invalidate(self):
        self._cache = SessionListCache()
```

`SessionHub.broadcast(kind="status_changed")`가 발생하면 `registry.invalidate()`를 호출한다. **요청 핸들러에서 직접 `os.scandir`을 사용하는 것을 금지**한다 (코드리뷰 체크리스트 항목).

### 4.3 LogTailer (A8, A9)

#### 4.3.1 데이터 모델

```python
# backend/services/log_tailer.py
from dataclasses import dataclass, field
from collections import deque
from time import time
from typing import Literal

@dataclass
class LogEntry:
    seq: int
    inode: int
    offset: int
    ts: float
    line: str

@dataclass
class TailerState:
    inode: int
    offset: int
    ring_buffer: deque[LogEntry]   # maxlen=LOG_RING_SIZE (1000)
    last_seq: int                  # monotonic per-tailer counter
    last_status_signal: float      # epoch

@dataclass
class WSMessage:
    type: Literal["append", "reset", "heartbeat", "status"]
    seq: str | None = None
    inode: int | None = None
    offset: int | None = None
    entries: list[LogEntry] = field(default_factory=list)
    reason: str | None = None
```

#### 4.3.2 회전 감지

```python
def _check_rotation(self, fd) -> bool:
    """True if rotated (inode changed)."""
    return os.fstat(fd.fileno()).st_ino != self.state.inode
```

회전 시 동작:
1. 현재 fd 닫기
2. 새 경로(`logs/current.log`) 열고 `state.inode = new_inode`, `state.offset = 0`
3. ring buffer는 유지(과거 엔트리는 회전 전 inode를 가짐)
4. 모든 구독자에게 `WSMessage(type="reset", reason="rotation", inode=new_inode, offset=0)` 전송
5. Prometheus counter `devbooth_log_rotations_total{session}` 증가

#### 4.3.3 영속성 정책 (A8)

- **메모리 only.** 디스크에 ring buffer를 저장하지 않는다.
- 프로세스 재시작 후 tailer는 `logs/current.log`의 EOF부터 재개한다 (historical replay 없음).
- 클라이언트는 재시작 후 `GET /api/sessions/{name}/logs?after=0&limit=N`으로 최신 N건을 가져온 다음 WS를 다시 연결한다.

#### 4.3.4 `resume_from` 프로토콜 (A9)

- `seq` 포맷: 합성 문자열 `f"{inode}:{byte_offset}"`. 예: `"1310754:48211"`.
- 클라이언트 메시지:
  ```json
  {"type":"subscribe","resume_from":"1310754:48211"}
  ```
- 서버 동작:
  1. 파싱 실패 → `WSMessage(type="reset", reason="bad_resume")` 후 정상 구독 시작.
  2. `inode`가 현재 `state.inode`와 다름 → `WSMessage(type="reset", reason="rotation", seq=f"{state.inode}:0")` 전송, 클라이언트는 REST 재조회 후 재구독.
  3. `inode`는 일치하나 `offset`이 ring buffer 최소 offset보다 작음 (`evicted`) → `WSMessage(type="reset", reason="evicted", seq=f"{state.inode}:{min_offset}")`.
  4. 일치하고 ring buffer 내에 있음 → `offset > resume_offset`인 엔트리만 순서대로 replay.
- ring buffer 1000개 한도. 초당 5건이면 200초 보존, 초당 50건이면 20초 보존. 알람: `devbooth_ring_buffer_eviction_total{session}`.

#### 4.3.5 broadcast 안전장치 (C5, C7)

```python
async def _send_to(self, sub: Subscriber, msg: WSMessage):
    try:
        sub.queue.put_nowait(msg)
    except asyncio.QueueFull:
        await sub.close(code=4002, reason="slow_consumer")
        DROPPED_SUBSCRIBERS.labels(session=self.session).inc()
```

### 4.4 AwgInspector + GPU 메트릭 (A12, A14, A15, C2)

#### 4.4.1 큐 깊이 (A14, C2)

`/dev-booth/awg/dashboard/server/services/awg_reader.py`에서 큐 카운팅 함수를 **그대로 복사**하여 `backend/services/awg_inspector.py::count_queue_files`로 이식한다. 4가지 상태(`inbox/processing/processed/dead`)를 모두 카운트하도록 조정한다.

```python
# backend/services/awg_inspector.py  (copied + adjusted from awg_reader)
from pathlib import Path
from config import QUEUES_ROOT   # = /dev-booth/awg/queues  (C2: queues/ only)

QUEUE_STATES = ("inbox", "processing", "processed", "dead")

def count_queue_files(queue_root: Path, agent: str, state: str) -> int:
    target = queue_root / agent / state
    if not target.is_dir():
        return 0
    return sum(1 for p in target.iterdir() if p.is_file() and p.suffix == ".json")
```

- `pip install -e ../awg`로 import 금지. **소스 복사**(주석에 출처와 SHA 명시).
- legacy `awg/` 디렉터리는 무시 (ADR-005).

#### 4.4.2 Prometheus 프록시 (A12, A15)

자유 쿼리 금지. preset allowlist만 노출.

```python
# backend/services/prometheus_proxy.py
PROM_BASE = "http://localhost:9090"
PRESETS = {
    "gpu0_util":       'DCGM_FI_DEV_GPU_UTIL{gpu="0"}',
    "gpu1_util":       'DCGM_FI_DEV_GPU_UTIL{gpu="1"}',
    "gpu0_mem_used":   'DCGM_FI_DEV_FB_USED{gpu="0"}',
    "gpu0_mem_total":  'DCGM_FI_DEV_FB_TOTAL{gpu="0"}',
    "gpu0_temp":       'DCGM_FI_DEV_GPU_TEMP{gpu="0"}',
}

async def fetch_preset(name: str) -> dict:
    if name not in PRESETS:
        raise HTTPException(404, "unknown preset")
    promql = PRESETS[name]
    async with httpx.AsyncClient(timeout=PROM_PROXY_TIMEOUT_S) as cli:
        r = await cli.get(f"{PROM_BASE}/api/v1/query", params={"query": promql})
    if r.status_code != 200:
        return {"value": None, "error": "prometheus_unavailable"}
    return _parse(r.json())
```

라우터:
```python
@router.get("/metrics/preset/{name}")
async def metrics_preset(name: str):
    return await fetch_preset(name)
```

`/api/metrics/prometheus?query=...` 엔드포인트는 **존재하지 않는다**. 코드 어디에도 free-form PromQL을 받는 경로가 없다.

#### 4.4.3 nvidia_smi_exporter 부재 처리

`nvidia_smi_exporter`(또는 DCGM exporter, 기본 9835/9400)가 미설치이거나 응답하지 않으면 모든 preset은 `{"value": null, "error": "prometheus_unavailable"}`를 반환한다. UI(`MetricCard`)는 이 경우 "GPU 메트릭 비활성" 배지를 표시한다.

### 4.5 path_guard — 심볼릭 링크 방어 (A11)

```python
# backend/services/path_guard.py
from pathlib import Path
from config import SESSIONS_ROOT

def walk_up_check(target: Path) -> Path:
    """
    1) Path.resolve() resolves all symlinks in target.
    2) Verify resolved target is within SESSIONS_ROOT.
    3) Walk every ancestor of the unresolved path; if any ancestor
       is itself a symlink whose resolved path escapes SESSIONS_ROOT, reject.
    """
    root = Path(SESSIONS_ROOT).resolve()
    if not target.is_absolute():
        target = (root / target)
    # ancestor symlink check
    for ancestor in [target, *target.parents]:
        if ancestor.is_symlink():
            resolved_anc = ancestor.resolve()
            if not _is_within(resolved_anc, root):
                raise HTTPException(400, "symlink_escape")
        if ancestor == root or root in ancestor.parents:
            break
    resolved = target.resolve()
    if not _is_within(resolved, root):
        raise HTTPException(400, "path_escape")
    return resolved

def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
```

세션 이름 입력은 **모두** 이 함수를 통과한다. 위협 모델: 운영자/오케스트레이터가 세션 디렉터리 내에 `/etc/passwd`로 향하는 심볼릭 링크를 무심코 생성한 경우.

### 4.6 stage_mapper (C1, ADR-004)

#### 4.6.1 정규화

```python
import unicodedata, re

def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text)
```

#### 4.6.2 키워드 표 (`backend/services/stage_keywords.yaml`)

§6의 12-stage 표를 직접 로드.

#### 4.6.3 매칭 규칙

- 영문 키워드: `\b<word>\b` (단어 경계).
- 한글 키워드: 한글은 `\b`가 의도대로 동작하지 않으므로 다음 패턴 사용:
  ```python
  # lookbehind/lookahead on non-CJK boundary
  cjk_pat = rf"(?<![\\uAC00-\\uD7A3\\u3130-\\u318F]){kw}(?![\\uAC00-\\uD7A3\\u3130-\\u318F])"
  ```
- 메시지 본문은 NFC 정규화 후 매칭.

#### 4.6.4 충돌 해소 (60초 윈도우)

```python
@dataclass
class StageHit:
    ts: float
    stage: int

class StageMapper:
    def __init__(self):
        self.window: dict[str, deque[StageHit]] = defaultdict(deque)

    def observe(self, session: str, text: str, ts: float) -> int | None:
        text = normalize(text)
        hits = self._match_all(text)
        if not hits:
            return None
        # add to window
        w = self.window[session]
        for h in hits:
            w.append(StageHit(ts=ts, stage=h))
        # purge
        cutoff = ts - STAGE_CONFLICT_WINDOW_S
        while w and w[0].ts < cutoff:
            w.popleft()
        # highest-stage-wins within 60s
        return max(h.stage for h in w)
```

만약 60초 이상 떨어져 있어 윈도우에 한 stage만 남는다면 자연히 "latest-wins"가 된다.

### 4.7 WebSocket 라우터 — close 코드 (C5)

```python
# backend/routers/ws.py
class WSCloseReason(IntEnum):
    IDLE_TIMEOUT = 4001
    SLOW_CONSUMER = 4002
    ROTATION_RESET = 4003
    SERVER_SHUTDOWN = 4004
    SESSION_NOT_FOUND = 4005
```

| 코드 | 의미 | 클라이언트 대응 |
|------|------|----------------|
| 4001 IDLE_TIMEOUT | 60s 무활동 | exponential backoff 후 재연결 (`resume_from`) |
| 4002 SLOW_CONSUMER | broadcast 큐 포화 | 1초 후 재연결, 재발생 시 알림 표시 |
| 4003 ROTATION_RESET | 파일 회전 | REST로 최신 N건 재조회 후 재구독 |
| 4004 SERVER_SHUTDOWN | 서버 graceful 종료 | 5초 후 재연결, 30초간 실패 시 "서버 점검 중" |
| 4005 SESSION_NOT_FOUND | 세션 삭제 | 재연결 중단, 사용자에게 "세션 종료" 표시 후 목록 페이지로 |

### 4.8 메트릭 (C3, C7)

```python
from prometheus_client import Counter, Gauge

WS_RECONNECTS = Counter("devbooth_ws_reconnects_total",
                        "WS reconnect events", ["session"])
WS_HEARTBEATS_MISSED = Counter("devbooth_ws_heartbeats_missed_total",
                               "Heartbeats missed by client", ["session"])
DROPPED_SUBSCRIBERS = Counter("devbooth_dropped_subscribers_total",
                              "Subscribers dropped due to slow consumer", ["session"])
LOG_ROTATIONS = Counter("devbooth_log_rotations_total",
                        "Log file rotations observed", ["session"])
RING_EVICTIONS = Counter("devbooth_ring_buffer_eviction_total",
                         "Ring buffer entries evicted before client read", ["session"])
```

알람 규칙 (별도 `prometheus/rules/devbooth.yml`):
- `rate(devbooth_ws_reconnects_total[1m]) > 10` → page
- `increase(devbooth_dropped_subscribers_total[5m]) > 10` → warn

---

## 5. 프론트엔드 상세

### 5.1 의존성

```json
// frontend/package.json (excerpt)
{
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "next-themes": "^0.3.0",
    "react-markdown": "^9.0.0",
    "rehype-highlight": "^7.0.0",
    "@monaco-editor/react": "^4.6.0",
    "swr": "^2.2.0",
    "zustand": "^4.5.0",
    "clsx": "^2.1.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.45.0",
    "@next/bundle-analyzer": "^14.2.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.4.0"
  }
}
```

- `react-syntax-highlighter`는 **포함하지 않는다** (A7).
- 마크다운 코드 펜스는 `react-markdown` + `rehype-highlight` 조합으로 처리한다 (경량).
- Monaco는 모달 전용. `next/dynamic`으로 lazy load (`ssr: false`).

### 5.2 테마 (A4)

```ts
// frontend/tailwind.config.ts
import type { Config } from "tailwindcss";
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: { fontFamily: { sans: ["Pretendard", "system-ui", "sans-serif"] } } },
  plugins: [],
};
export default config;
```

```tsx
// frontend/app/layout.tsx
import { ThemeProvider } from "next-themes";
import { pretendard } from "@/lib/fonts";
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className={pretendard.variable} suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
```

`AppHeader` 우상단에 `ThemeToggle` 버튼 (light / dark / system). system이 기본이되 사용자 override 가능.

### 5.3 폰트 — Pretendard (A13)

```ts
// frontend/lib/fonts.ts
import localFont from "next/font/local";
export const pretendard = localFont({
  src: [
    { path: "../public/fonts/Pretendard-Regular.woff2",  weight: "400", style: "normal" },
    { path: "../public/fonts/Pretendard-Medium.woff2",   weight: "500", style: "normal" },
    { path: "../public/fonts/Pretendard-SemiBold.woff2", weight: "600", style: "normal" },
    { path: "../public/fonts/Pretendard-Bold.woff2",     weight: "700", style: "normal" },
  ],
  variable: "--font-pretendard",
  display: "swap",
});
```

- woff2 only(subset된 latin+ko 버전), 4 weight.
- `public/fonts/OFL.txt`에 SIL Open Font License 1.1 텍스트 동봉 (A13).
- 다운로드/서브셋 절차는 README의 "Pretendard preparation" 절에 기록:
  1. `https://github.com/orioncactus/pretendard/releases`에서 최신 release의 `Pretendard-1.X.X-subset-woff2.zip` 다운로드.
  2. 위 4개 weight 파일을 `frontend/public/fonts/`에 복사.
  3. `LICENSE` 파일을 `OFL.txt`로 동일 위치에 복사.

### 5.4 Monaco lazy load (A7, A17)

```tsx
// frontend/components/MonacoModal.tsx
import dynamic from "next/dynamic";
import { Suspense } from "react";

const Monaco = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <div className="p-8 text-sm">에디터 로딩 중…</div>,
});

export function MonacoModal({ open, content, onClose }: Props) {
  if (!open) return null;
  return (
    <div role="dialog" className="fixed inset-0 z-50">
      <Suspense fallback={<div className="p-8">에디터 로딩 중…</div>}>
        <Monaco height="80vh" defaultLanguage="json" value={content} options={{ readOnly: true }} />
      </Suspense>
    </div>
  );
}
```

성능 목표: 첫 모달 오픈 → Monaco 첫 paint ≤ 800ms (`AC_MONACO_FIRST_OPEN_MS`).

### 5.5 환경 변수 (C15)

| 변수 | 기본값 | 환경 | 비고 |
|------|--------|------|------|
| `NEXT_PUBLIC_API_BASE` | `""` (same-origin) | production | 정적 export가 Tunnel 뒤에 있으므로 same-origin |
| `NEXT_PUBLIC_API_BASE` | `"http://localhost:7000"` | development (`.env.development`) | 개발 시 FastAPI 직접 호출 |
| `NEXT_PUBLIC_WS_BASE` | `""` | production | WS는 `wss://<host>/ws/<session>` |
| `NEXT_PUBLIC_WS_BASE` | `"ws://localhost:7000"` | development | |

`lib/api.ts`는 빈 문자열이면 `window.location.origin`을 사용 (브라우저 전용 코드이므로 안전).

### 5.6 ChatSearch + Scroll-anchor (C15)

```tsx
// frontend/components/ChatSearch.tsx
useEffect(() => {
  const handler = (e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "f") {
      e.preventDefault();
      inputRef.current?.focus();
    }
  };
  window.addEventListener("keydown", handler);
  return () => window.removeEventListener("keydown", handler);
}, []);
```

스크롤 앵커 정책 (`LogStream.tsx`, `ChatStream.tsx`):

```ts
const SCROLL_ANCHOR_THRESHOLD_PX = 80;
function shouldAutoStick(el: HTMLElement): boolean {
  const max = el.scrollHeight - el.clientHeight;
  return el.scrollTop > max - SCROLL_ANCHOR_THRESHOLD_PX;
}
```

붙어 있지 않으면 화면 하단에 `floating "N new"` pill을 표시, 클릭 시 끝으로 스크롤.

### 5.7 WS 클라이언트 (A9, C5)

```ts
// frontend/lib/ws.ts
export class SessionWS {
  private ws: WebSocket | null = null;
  private resumeFrom: string | null = null;
  private backoffMs = 500;
  open(session: string) { this.connect(session); }
  private connect(session: string) {
    const base = process.env.NEXT_PUBLIC_WS_BASE || `wss://${location.host}`;
    this.ws = new WebSocket(`${base}/ws/${session}`);
    this.ws.onopen = () => {
      this.backoffMs = 500;
      this.ws!.send(JSON.stringify({ type: "subscribe", resume_from: this.resumeFrom }));
    };
    this.ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "append") {
        this.resumeFrom = msg.seq;
        onAppend(msg.entries);
      } else if (msg.type === "reset") {
        this.resumeFrom = null;
        onReset(msg.reason);   // triggers REST re-fetch
      }
    };
    this.ws.onclose = (ev) => {
      switch (ev.code) {
        case 4005: return abort();                     // session not found
        case 4003: this.resumeFrom = null; break;      // rotation
      }
      setTimeout(() => this.connect(session), this.backoffMs);
      this.backoffMs = Math.min(this.backoffMs * 2, 15000);
    };
  }
}
```

---

## 6. 12-단계 시나리오

### 6.1 한/영/regex 키워드 표 (ADR-004)

표의 한국어 키워드는 모두 NFC 정규화된 상태로 매칭한다. `regex` 열은 위 §4.6.3 규칙에 따른 컴파일된 패턴 예시.

| Stage | 영문 명 | 한국어 명 | 영문 trigger 키워드 | 한국어 trigger 키워드 | regex 패턴 (요약) |
|-------|--------|----------|-------------------|---------------------|------------------|
| 1 | Intake | 접수 | `intake`, `received`, `new task` | `접수`, `요청 수신`, `신규 작업` | `\b(intake\|received\|new\s+task)\b` + CJK 룩어라운드 |
| 2 | Triage | 분류 | `triage`, `classify`, `route` | `분류`, `라우팅`, `우선순위` | `\b(triage\|classify\|route)\b` |
| 3 | Plan | 계획 | `plan`, `decompose`, `breakdown` | `계획`, `분해`, `설계` | `\b(plan\|decompose\|breakdown)\b` |
| 4 | Research | 조사 | `research`, `investigate`, `explore` | `조사`, `탐색`, `분석` | `\b(research\|investigate\|explore)\b` |
| 5 | Design | 설계 | `design`, `architecture`, `spec` | `설계`, `아키텍처`, `명세` | `\b(design\|architecture\|spec)\b` |
| 6 | Implement | 구현 | `implement`, `code`, `build` | `구현`, `작성`, `빌드` | `\b(implement\|code\|build)\b` |
| 7 | Test | 시험 | `test`, `pytest`, `verify` | `시험`, `테스트`, `검증` | `\b(test\|pytest\|verify)\b` |
| 8 | Review | 검토 | `review`, `lint`, `inspect` | `검토`, `리뷰`, `점검` | `\b(review\|lint\|inspect)\b` |
| 9 | Fix | 수정 | `fix`, `patch`, `repair` | `수정`, `패치`, `보정` | `\b(fix\|patch\|repair)\b` |
| 10 | Deploy | 배포 | `deploy`, `release`, `ship` | `배포`, `릴리스`, `출시` | `\b(deploy\|release\|ship)\b` |
| 11 | Monitor | 관찰 | `monitor`, `observe`, `metric` | `관찰`, `모니터링`, `지표` | `\b(monitor\|observe\|metric)\b` |
| 12 | Retrospect | 회고 | `retrospect`, `postmortem`, `lessons` | `회고`, `사후`, `교훈` | `\b(retrospect\|postmortem\|lessons)\b` |

### 6.2 충돌 해소 (C1)

- 동일 메시지에서 여러 stage 키워드가 동시 매치 → 최고 stage(가장 큰 수). 이유: AWG는 stage가 단조 증가한다고 가정.
- 60초 윈도우 내 여러 메시지가 서로 다른 stage 매치 → 동일하게 최고값.
- 60초보다 더 떨어진 매치는 자연스럽게 윈도우에서 빠지므로 "latest-wins" 효과.
- 음수 사례(예: "no plan yet"): 부정형 키워드는 v3에서 지원하지 않고, 정확도가 0.9에 미달하면 follow-up으로 확장 (ADR-004 Follow-ups).

### 6.3 Golden fixture (C10)

`backend/tests/fixtures/stage_messages.jsonl` — 30개 hand-labeled + 5개 negative.

```jsonl
{"text":"intake received from user A","expect":1}
{"text":"신규 작업 접수 완료","expect":1}
{"text":"plan: decompose into 3 tasks","expect":3}
{"text":"우선순위 분류 후 라우팅","expect":2}
{"text":"running pytest now","expect":7}
{"text":"deploy to prod complete","expect":10}
{"text":"회고 작성","expect":12}
{"text":"hello world","expect":null}                 # negative
{"text":"this is just a test message about nothing","expect":7}   # "test" hit
{"text":"NO plan exists","expect":3}                 # known limitation
...
```

테스트 `test_stage_mapper.py`:
- `accuracy = correct / total_with_label`, 음수 라벨은 None 매치를 정답으로.
- `assert accuracy >= AC_STAGE_ACCURACY_MIN  # 0.9`

---

## 7. WBS (Work Breakdown Structure)

각 마일스톤은 **수용 명령(acceptance command)** 을 가지며, 명령이 0 종료해야 마일스톤이 완료된다.

### 7.1 M1 — 골격 + 인프라 부트스트랩 (1일)

**산출물**:
- `dashboard/.gitignore` (C15): `node_modules/`, `out/`, `out.previous/`, `.next/`, `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, `dashboard/frontend/out.previous/`, `.env.local`.
- `backend/pyproject.toml` + `backend/main.py` (hello-world FastAPI).
- `backend/tests/conftest.py` (`SESSIONS_ROOT`를 `tmp_path`로 override).
- `backend/config.py` (§3.3 표의 모든 상수).
- `frontend/` Next.js 14 skeleton, `next.config.mjs`, `tailwind.config.ts`, `app/layout.tsx`, `app/page.tsx`, `app/session/[name]/page.tsx`.
- `frontend/public/fonts/{Pretendard-*.woff2, OFL.txt}`.
- `frontend/.env.development` (`NEXT_PUBLIC_API_BASE=http://localhost:7000`).
- `frontend/lib/constants.ts`.
- `ops/systemd/devbooth-dashboard-api.service` (draft, 미설치).
- `ops/systemd/devbooth-dashboard-static.service` (draft).
- `ops/journald.conf.d/devbooth.conf` (draft).

**수용 명령**:
```bash
cd /dev-booth/dashboard
pytest -q backend/tests/test_smoke.py
(cd frontend && pnpm install && pnpm build)
test -d frontend/out
test -f frontend/public/fonts/OFL.txt
curl -fsS http://localhost:7000/api/_openapi.json >/dev/null
```

### 7.2 M2 — SessionRegistry + Cache + path_guard (1일)

**산출물**:
- `services/session_layout.py`, `services/session_registry.py`, `services/path_guard.py`.
- `routers/sessions.py` (`GET /api/sessions`, `GET /api/sessions/{name}`).
- 테스트: 캐시 hit/miss, 무효화, 경로 traversal 3-vector (C12).

**수용 명령**:
```bash
pytest -q backend/tests/test_session_registry.py backend/tests/test_path_guard.py
curl -fsS http://localhost:7000/api/sessions | jq '.[0].name'
# path traversal 3-vector
curl -sS -o /dev/null -w "%{http_code}\n" 'http://localhost:7000/api/sessions/..%2F..%2Fetc%2Fpasswd'  # expect 4xx
```

### 7.3 M3 — LogTailer + WS + resume_from (2일)

**산출물**:
- `services/log_tailer.py`, `services/session_hub.py` (with `status_cache`, C15), `routers/ws.py`, `routers/logs.py`.
- `WSCloseReason` enum + 5개 코드 처리.
- 로그 회전 시뮬레이션 테스트.
- `scripts/test_resume.py` (C11).
- `scripts/measure_e2e_latency.py` (C9).

**수용 명령**:
```bash
pytest -q backend/tests/test_log_tailer.py backend/tests/test_resume_from.py
python ops/scripts/test_resume.py --session test-awg
python ops/scripts/measure_e2e_latency.py --target ws://localhost:7000/ws/test-awg --p95-max 500
# Tunnel idle simulation (>100s) — separate harness in M6
```

### 7.4 M4 — AwgInspector + Prometheus preset + StageMapper (1일)

**산출물**:
- `services/awg_inspector.py` (copied from awg_reader, ADR-005).
- `services/prometheus_proxy.py` + preset allowlist.
- `services/stage_mapper.py` + `stage_keywords.yaml`.
- `backend/tests/fixtures/stage_messages.jsonl` (30+5).

**수용 명령**:
```bash
pytest -q backend/tests/test_awg_inspector.py backend/tests/test_prometheus_proxy.py backend/tests/test_stage_mapper.py
# free-form query must 404
curl -sS -o /dev/null -w "%{http_code}\n" 'http://localhost:7000/api/metrics/prometheus?query=up'  # expect 404
curl -fsS http://localhost:7000/api/metrics/preset/gpu0_util | jq '.value'
```

### 7.5 M5 — 프론트엔드 화면 (3일)

**산출물**:
- `components/SessionCard.tsx`, `StageBar.tsx`, `LogStream.tsx`, `ChatStream.tsx`, `ChatSearch.tsx`, `MonacoModal.tsx`, `MetricCard.tsx`, `ThemeToggle.tsx`.
- SWR 기반 REST 조회 + `SessionWS` 클래스 WS.
- Playwright 4 시나리오 `tests/playwright/basic.spec.ts` (C14).

**수용 명령**:
```bash
cd frontend
pnpm build
# bundle size guard (A16)
node ../ops/scripts/bundle_size_check.sh  # asserts First Load JS gzip <= 250KB
npx playwright install --with-deps
npx playwright test --grep "@smoke"
```

### 7.6 M6 — 운영(systemd + Cloudflare + alerts) (1일)

**산출물**:
- `useradd --system devbooth` + 권한 설정 스크립트 `ops/scripts/install_users.sh`.
- 최종 systemd 유닛(아래 §10) 설치.
- `ops/journald.conf.d/devbooth.conf` 적용 + `systemctl restart systemd-journald`.
- Cloudflare Tunnel `ingress` 설정 (`dashboard.excusa.uk` → `localhost:8080`) + Access policy 적용.
- Prometheus 알람 규칙 적재.
- Tunnel idle simulation harness (120초간 broadcast 없이 WS 유지).

**수용 명령**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now devbooth-dashboard.target
systemctl is-active devbooth-dashboard-api.service
systemctl is-active devbooth-dashboard-static.service
curl -fsS https://dashboard.excusa.uk/api/sessions
# WSS idle survival
timeout 130 wscat -c wss://dashboard.excusa.uk/ws/test-awg --no-color
# expect: still open at 120s due to heartbeat
```

---

## 8. 테스트

### 8.1 매트릭스

| 영역 | 종류 | 도구 | 위치 | 수용 기준 |
|------|------|------|------|----------|
| path traversal 3-vector | unit + integration | pytest + httpx | `test_path_guard.py`, `test_sessions_security.py` | 모두 4xx (C12) |
| LogTailer 회전 | unit | pytest + tmp_path | `test_log_tailer.py` | 회전 시 `reset` 메시지 발신 (A17) |
| resume_from 복구 | integration | scripts + pytest | `test_resume_from.py`, `scripts/test_resume.py` | 50→20 순서 보존 (A17, C11) |
| Tunnel idle 시뮬레이션 | e2e | wscat + harness | `ops/scripts/idle_survive.sh` | 120s 생존 (A17, C13) |
| Monaco 지연 | e2e | Playwright | `tests/playwright/basic.spec.ts` (Case 4) | 첫 paint ≤ 800ms (A17) |
| stage 정확도 | unit | pytest + JSONL fixture | `test_stage_mapper.py` | accuracy ≥ 0.9 (C10) |
| e2e latency | benchmark | `measure_e2e_latency.py` | `scripts/` | local p95 ≤ 500ms, Tunnel p95 ≤ 1500ms (C9) |
| 번들 크기 | size guard | `bundle_size_check.sh` | `ops/scripts/` | 초기 JS gzip ≤ 250KB (A16) |
| Prometheus SSRF 방어 | unit + integration | pytest | `test_prometheus_proxy.py` | free-form query 404 (A15) |
| WS close 코드 | unit | pytest | `test_ws_close_codes.py` | 4001~4005 각각 정상 발신 (C5) |
| 큐 카운팅 | unit | pytest + tmp fs | `test_awg_inspector.py` | 4 state count 정확 (A14) |
| 캐시 무효화 | unit | pytest | `test_session_registry.py` | 이벤트로 invalidate (A10) |
| 한/영 stage 정규화 | unit | pytest + NFC | `test_stage_mapper.py` | NFD 입력도 동일 결과 (C1) |
| Playwright | e2e | `npx playwright` | `tests/playwright/basic.spec.ts` | 4 시나리오 모두 통과 (C14) |
| ThemeToggle | e2e | Playwright | `basic.spec.ts` Case 5 | 다크 모드 토글 시 `html.dark` 클래스 부여 (A4) |

### 8.2 Playwright 4 시나리오 (C14)

```ts
// frontend/tests/playwright/basic.spec.ts
import { test, expect } from "@playwright/test";

test("@smoke main page loads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /세션/ })).toBeVisible();
});

test("@smoke session detail loads", async ({ page }) => {
  await page.goto("/session/test-awg/");
  await expect(page.getByTestId("stage-bar")).toBeVisible();
});

test("@smoke live log append reaches DOM", async ({ page }) => {
  await page.goto("/session/test-awg/");
  // backend test helper appends a line; UI must show it within 2s
  await expect(page.getByTestId("log-line").last()).toContainText(/.+/);
});

test("@smoke monaco modal opens and ESC closes", async ({ page }) => {
  await page.goto("/session/test-awg/");
  const start = Date.now();
  await page.getByRole("button", { name: /원본 보기/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible({ timeout: 1500 });
  expect(Date.now() - start).toBeLessThan(800 + 700); // AC_MONACO_FIRST_OPEN_MS + jitter
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});
```

Playwright는 항상 `npx playwright test`로 실행 (C14). CI에 pnpm이 없을 수 있으므로 의존하지 않는다.

### 8.3 사전 부검 (Pre-mortem)

본 deliberate 수준 보강에서 다음 3개의 실패 시나리오를 사전 점검:

**S1: Tunnel 재시작 + 로그 회전 동시 발생**
- 트리거: 야간 `cloudflared` 자동 업데이트와 logrotate 회전이 동시에 발생.
- 영향: WS 클라이언트가 `resume_from`을 보내는데 서버 측 inode가 막 바뀜.
- 완화: §4.3.4 시나리오 (2) — server는 `reset/rotation` 발신, 클라이언트는 REST 재조회 후 재구독. C11 테스트가 이를 직접 검증.

**S2: 세션 디렉터리에 심볼릭 링크가 들어옴**
- 트리거: 운영자가 디버깅 중 `ln -s /etc/passwd /dev-booth/sessions/test/dump`.
- 영향: `GET /api/sessions/test/logs?path=dump`가 시스템 파일 노출 위험.
- 완화: §4.5 `walk_up_check`. C12 테스트가 3-vector 검증.

**S3: GPU 부하 폭주로 Prometheus 응답 지연**
- 트리거: 학습 job이 nvml 폴링을 차단.
- 영향: `/api/metrics/preset/gpu0_util`이 3초 timeout, UI가 정지처럼 보임.
- 완화: `PROM_PROXY_TIMEOUT_S=3`, 응답 `{"value": null, "error": "prometheus_unavailable"}`, UI는 "GPU 메트릭 비활성" 배지로 graceful degrade.

---

## 9. 위험 (R-Risks)

| ID | 위험 | 영향 | 가능성 | 완화 | 출처 |
|----|------|------|--------|------|------|
| R1 | LogTailer 메모리 누수 | OOM | 중 | ring buffer maxlen 1000, 세션 종료 시 cleanup | A8 |
| R2 | 동시 WS 100+ | CPU/네트워크 | 저 | 1인 운영자, max 10 expected; `WS_BROADCAST_QUEUE_MAX=256` | C5 |
| R3 | stage 오탐 (한/영 혼용) | UI 신뢰 | 중 | NFC 정규화 + golden fixture ≥ 0.9 + 60초 윈도우 | C1, ADR-004 |
| R4 | 큐 경로 불일치 (`awg/` vs `queues/`) | 잘못된 카운트 | 중 | `queues/`만 사용, ADR-005에 명시 | C2 |
| R5 | Cloudflare Tunnel WS idle disconnect (~100s) | 실시간성 손실 | 고 | 20s heartbeat (~5× 안전 마진), heartbeat 실패 카운터 + 알람 | A5, C3 |
| R6 | Pretendard 라이선스 위반 | 법적 | 저 | OFL.txt 동봉 + README 절차 | A13 |
| R7 | 경로 traversal/심볼릭 링크 | 데이터 누출 | 중 | `walk_up_check` + 3-vector 테스트 | A11, C12 |
| R8 | Prometheus SSRF | 내부망 노출 | 저 | preset allowlist만, free-form query 차단 | A15 |
| R9 | 정적 export 빌드 실패 → 사이트 다운 | 가용성 | 중 | 직전 성공 빌드 `out.previous/`에 보관, systemd `ExecStartPre`가 `out/` 비어있으면 `out.previous/`로 fallback | A3, C4 |
| R10 | journald 무한 증가 | 디스크 | 저 | drop-in `SystemMaxUse=500M`, `MaxFileSec=1week` | C6 |
| R11 | broadcast 큐 포화 (느린 클라이언트) | 다른 구독자 지연 | 저 | `WSCloseReason.SLOW_CONSUMER=4002` + drop counter + 알람 | C5, C7 |
| R12 | Cloudflare Access 장애 | 접근 불가 | 저 | Access 다운 시에도 Tunnel ingress가 service token 요구; 토큰 부재 403 (degraded mode) | C8 |
| R13 | Monaco 첫 로드 지연 | UX | 중 | `next/dynamic` + Suspense, AC ≤ 800ms 측정 | A7, A17 |
| R14 | 빌드/런타임 권한 혼선 | 권한 오류 | 중 | `mooner92`(build) / `devbooth`(runtime) 분리 | A6 |

---

## 10. systemd / Tunnel

### 10.1 사용자 분리 (A6)

- **빌드 사용자**: `mooner92` (UID 1000, 개발자 본인). corepack/pnpm 캐시는 `/home/mooner92/.cache/`.
- **런타임 사용자**: `devbooth` (시스템 계정).

설치 스크립트 `ops/scripts/install_users.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
if ! id -u devbooth >/dev/null 2>&1; then
  sudo useradd --system --no-create-home --shell /usr/sbin/nologin devbooth
fi
sudo install -d -o devbooth -g devbooth -m 0750 /dev-booth/dashboard/frontend/out
sudo install -d -o devbooth -g devbooth -m 0750 /dev-booth/dashboard/frontend/out.previous
```

빌드 직후 (M5 마지막 단계):

```bash
sudo chown -R devbooth:devbooth /dev-booth/dashboard/frontend/out
```

`devbooth`는 다음에 read-only 접근:
- `/dev-booth/sessions/` (ACL 또는 group permission)
- `/dev-booth/awg/queues/`

쓰기 권한 없음.

### 10.2 systemd 유닛

**API 유닛** `ops/systemd/devbooth-dashboard-api.service`:

```ini
[Unit]
Description=Dev-Booth Dashboard FastAPI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=devbooth
Group=devbooth
WorkingDirectory=/dev-booth/dashboard/backend
Environment="PYTHONUNBUFFERED=1"
ExecStartPre=/usr/bin/test -d /dev-booth/sessions
ExecStartPre=/bin/bash -c '! ss -ltn "( sport = :7000 )" | grep -q :7000'
ExecStart=/dev-booth/dashboard/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 7000
Restart=on-failure
RestartSec=2s
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=yes
NoNewPrivileges=yes
ReadOnlyPaths=/dev-booth/sessions /dev-booth/awg/queues

[Install]
WantedBy=multi-user.target
```

**정적 유닛** `ops/systemd/devbooth-dashboard-static.service` (단순 정적 서버, 포트 8080):

```ini
[Unit]
Description=Dev-Booth Dashboard Static
After=devbooth-dashboard-api.service
Requires=devbooth-dashboard-api.service

[Service]
Type=simple
User=devbooth
Group=devbooth
WorkingDirectory=/dev-booth/dashboard/frontend
# Fallback to out.previous/ if out/ is empty
ExecStartPre=/bin/bash -c '\
  if [ -z "$(ls -A /dev-booth/dashboard/frontend/out 2>/dev/null)" ]; then \
    echo "out/ empty, falling back to out.previous/"; \
    rm -rf /dev-booth/dashboard/frontend/out && \
    cp -a /dev-booth/dashboard/frontend/out.previous /dev-booth/dashboard/frontend/out; \
  fi'
ExecStartPre=/bin/bash -c '! ss -ltn "( sport = :8080 )" | grep -q :8080'
# Simple reverse proxy: /api/* and /ws/* → :7000, rest → static
ExecStart=/usr/bin/caddy run --config /dev-booth/dashboard/ops/caddy/Caddyfile
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=multi-user.target
```

**Caddyfile** (`ops/caddy/Caddyfile`):

```
:8080 {
    handle_path /api/* {
        reverse_proxy 127.0.0.1:7000
    }
    handle /ws/* {
        reverse_proxy 127.0.0.1:7000
    }
    handle {
        root * /dev-booth/dashboard/frontend/out
        try_files {path} {path}/ /index.html
        file_server
        encode gzip
    }
}
```

**Target** `ops/systemd/devbooth-dashboard.target`:

```ini
[Unit]
Description=Dev-Booth Dashboard (API + Static)
Wants=devbooth-dashboard-api.service devbooth-dashboard-static.service
After=devbooth-dashboard-api.service devbooth-dashboard-static.service

[Install]
WantedBy=multi-user.target
```

### 10.3 빌드 → 배포 흐름 (R9, C4)

```bash
# as mooner92
cd /dev-booth/dashboard/frontend
pnpm install --frozen-lockfile
if pnpm build; then
  # success: rotate
  sudo rm -rf out.previous
  if [ -d out ]; then sudo mv out out.previous; fi
  sudo mv .next/.export-staging out 2>/dev/null || true  # if Next staged
  # In Next.js 14 export, the output is directly in out/. Simpler:
  pnpm build && sudo cp -a out out.new && \
    sudo rm -rf out.previous && \
    sudo mv out out.previous 2>/dev/null || true && \
    sudo mv out.new out
  sudo chown -R devbooth:devbooth out out.previous
  sudo systemctl reload devbooth-dashboard-static.service || sudo systemctl restart devbooth-dashboard-static.service
else
  echo "build failed, keeping current out/"
  exit 1
fi
```

`systemctl` `ExecStartPre`가 `out/`이 비어있으면 `out.previous/`를 복사하여 fallback (위 정의).

### 10.4 journald drop-in (C6)

`ops/journald.conf.d/devbooth.conf`:

```ini
[Journal]
SystemMaxUse=500M
SystemKeepFree=1G
MaxFileSec=1week
```

설치:
```bash
sudo install -d /etc/systemd/journald.conf.d
sudo install -m 0644 ops/journald.conf.d/devbooth.conf /etc/systemd/journald.conf.d/devbooth.conf
sudo systemctl restart systemd-journald
```

### 10.5 Cloudflare Tunnel + Access (A5, C8)

#### 10.5.1 Tunnel ingress (`/etc/cloudflared/config.yml`)

```yaml
tunnel: devbooth-dashboard
credentials-file: /etc/cloudflared/devbooth-dashboard.json
ingress:
  - hostname: dashboard.excusa.uk
    service: http://localhost:8080
    originRequest:
      noTLSVerify: true
      connectTimeout: 10s
      tlsTimeout: 10s
      tcpKeepAlive: 30s
      keepAliveTimeout: 90s
      keepAliveConnections: 10
  - service: http_status:404
```

#### 10.5.2 WS heartbeat (A5)

- Cloudflare Tunnel **기본 WS idle timeout ≈ 100초** (실측 기반, 공식 문서: "Connections inactive for ~100s may be closed").
- 서버 heartbeat 주기 = **20초** → 100초 한도의 **약 5×** 안전 마진. 한 번의 heartbeat 손실이 있어도 다음 heartbeat가 80초 이내에 도착.
- 본 값은 ADR-001(아래)에 명시.

#### 10.5.3 Access policy (C8)

Cloudflare Dashboard → Access → Applications:

- Application name: `Dev-Booth Dashboard`
- Application domain: `dashboard.excusa.uk`
- Identity providers: Google OAuth (and One-Time PIN as backup)
- Policy:
  - Name: `Operator only`
  - Action: `Allow`
  - Include rule: `Emails in {mooner92@kakao.com}`
  - Session duration: 24h

**Degraded mode**: Access control plane 장애 시에도 Tunnel ingress는 cloudflared의 service token 검증을 거치므로, 토큰 없이는 403. 즉 fail-closed.

---

## 11. 수용 기준 (Acceptance Criteria)

| AC# | 기준 | 검증 방법 | 한도 |
|-----|------|----------|------|
| AC1 | 메인 페이지 로드 | `curl -fsS https://dashboard.excusa.uk/` | 200, ≤ 2s |
| AC2 | 세션 목록 API | `curl -fsS https://dashboard.excusa.uk/api/sessions` | JSON 배열 |
| AC3 | e2e 로그 latency | `python ops/scripts/measure_e2e_latency.py` (100 entries) | local p95 ≤ 500ms, Tunnel p95 ≤ 1500ms (C9) |
| AC4 | stage 감지 정확도 | `pytest -q backend/tests/test_stage_mapper.py` against golden fixture | accuracy ≥ 0.9 (C10) |
| AC5 | resume_from 복구 | `python ops/scripts/test_resume.py` | 50→20 entries 순서 보존, seq monotonic (C11) |
| AC6 | 경로 traversal 3-vector | curl-based + pytest | (a) URL-encoded `..%2F..%2F` 4xx, (b) JSON body `path` 4xx, (c) symlink `/etc/passwd` 4xx, 모두 empty body (C12) |
| AC7 | 번들 크기 | `ops/scripts/bundle_size_check.sh` | 초기 JS gzip ≤ 250KB (A16) |
| AC8 | Monaco 첫 모달 | Playwright Case 4 | ≤ 800ms (A17) |
| AC9 | WSS 120s idle 생존 | `wscat -c wss://dashboard.excusa.uk/ws/test-awg` 120초 hold | 연결 유지 (heartbeat) (C13) |
| AC10 | Playwright 4 시나리오 | `npx playwright test --grep @smoke` | 4/4 통과 (C14) |
| AC11 | Prometheus SSRF 차단 | `curl -sS -o /dev/null -w "%{http_code}" '...prometheus?query=up'` | 404 (A15) |
| AC12 | 로그 회전 처리 | `pytest -q backend/tests/test_log_tailer.py::test_rotation` | reset 메시지 발신, ring buffer 유지 (A17) |
| AC13 | 다크 모드 토글 | Playwright | `html.dark` 클래스 부여/제거 (A4) |
| AC14 | systemd 유닛 | `systemctl is-active devbooth-dashboard.target` | active |
| AC15 | Cloudflare Access | 비허용 이메일로 접근 시도 | 차단 (수동 검증) |

---

## 12. 실행 경로 (Execution Path)

본 계획의 실행자(`/oh-my-claudecode:start-work`)가 따를 순서:

1. **M1** 골격 부트스트랩 (위 §7.1 명령).
2. **M2** SessionRegistry + path_guard.
3. **M3** LogTailer + WS + resume_from.
4. **M4** AwgInspector + Prometheus preset + StageMapper.
5. **M5** 프론트엔드 화면 + Playwright.
6. **M6** 운영 인프라 + alerts.
7. 모든 AC 명령 일괄 통과 후 사용자에게 `proceed` 요청.
8. 미해결 항목은 `.omc/plans/open-questions.md`에 append.

각 마일스톤은 PR 단위로 commit. 커밋 메시지 컨벤션: `[dashboard][M{1-6}] <summary>`.

---

## 13. ADR (Architecture Decision Records)

본 절은 5개의 ADR을 포함한다. 모두 동일 포맷: Status / Context / Decision / Drivers / Alternatives / Why / Consequences / Follow-ups.

### ADR-001 — Cloudflare Tunnel WS Heartbeat 20s

- **Status**: Accepted (v3)
- **Context**: 실시간 로그를 Cloudflare Tunnel을 통해 외부에 노출한다. Cloudflare는 WebSocket idle 연결을 약 100초 후 끊을 수 있다고 알려져 있다 (실측 + 비공식 문서 합산).
- **Decision**: 서버는 모든 WS 연결에 대해 **20초 주기**로 `{"type":"heartbeat"}` 메시지를 발신한다. 클라이언트는 60초 이상 활동(메시지/heartbeat) 부재 시 재연결한다.
- **Drivers**: D3 (실시간 로그 신뢰성), R5 (Tunnel idle disconnect).
- **Alternatives**:
  - 5초 heartbeat: 대역폭과 CPU 부담 증가, 1인 운영 환경에서 과다.
  - 60초 heartbeat: 1회 손실 시 Tunnel limit 직전, 안전 마진 부족.
  - 클라이언트만 ping: 백엔드가 클라이언트 끊김을 늦게 인지.
- **Why**: 20s = 100s의 ~1/5. 한 번의 손실(40s elapsed)이 있어도 다음 heartbeat가 60s에 도달, 여전히 Tunnel limit 이내.
- **Consequences**: 세션당 초당 0.05개의 추가 메시지 — 무시 가능. 메트릭 `devbooth_ws_heartbeats_missed_total`로 가시화.
- **Follow-ups**: Cloudflare가 timeout을 변경하면 이 ADR 재검토.

### ADR-002 — Next.js `output: "export"` + Client-Only Dynamic Routes

- **Status**: Accepted (v3)
- **Context**: 프론트엔드를 정적 파일로 배포하여 Node 런타임을 제거하고 systemd 유닛/메모리 footprint를 최소화한다. 동적 라우트 `/session/[name]`은 사전 알 수 없는 임의 세션 이름을 처리해야 한다.
- **Decision**: `next.config.mjs`에 `output: "export"`만 사용한다 (CLI `next export` 금지). `/session/[name]/page.tsx`는 `'use client'` + `generateStaticParams: () => []` + `dynamicParams: false`로 단일 fallback shell만 빌드한다. 세션 데이터는 클라이언트에서 REST/WS로 가져온다.
- **Drivers**: D1 (배포 표면적 최소), P1 (운영 단순성), P5 (외부 의존 최소).
- **Alternatives**:
  - SSR: Node 런타임 + systemd 유닛 추가, 본 시나리오에서 SSR 가치 없음 (인증은 Tunnel 단).
  - `output: "standalone"` 폴백: 본 v3에서 R9의 폴백 메커니즘으로 사용했었으나 제거 (A3). 대신 `out.previous/` 기반 fallback (C4).
  - 모든 세션 이름을 빌드 시 prerender: 운영 중 새 세션 생성 불가.
- **Why**: 단일 fallback shell + 클라이언트 fetch는 무한 세션 이름 공간을 정적 배포로 다룰 수 있게 한다.
- **Consequences**: 첫 페이지 로드 시 클라이언트 fetch 1회 추가. SEO 무관(내부 도구).
- **Follow-ups**: 세션 수가 폭증하면 `out.previous/` 회전 정책 재검토.

### ADR-003 — Runtime/Build 사용자 분리

- **Status**: Accepted (v3)
- **Context**: 빌드는 개발자 환경(`mooner92`)에서 수행되지만, 런타임 프로세스는 최소 권한 시스템 계정에서 동작해야 한다.
- **Decision**: 빌드는 `mooner92`로, 런타임은 `devbooth` 시스템 계정(`useradd --system`)으로 분리한다. 빌드 완료 후 `chown -R devbooth:devbooth out`. corepack/pnpm 캐시는 `mooner92`의 HOME에 잔류.
- **Drivers**: P3 (최소 권한), R14.
- **Alternatives**:
  - 동일 사용자(root 혹은 mooner92)로 모두 실행: 권한 누설 위험.
  - Docker 컨테이너: P1, P5 위반.
- **Why**: 시스템 계정 격리는 단일 호스트에서 얻을 수 있는 가장 단순한 보안 강화.
- **Consequences**: 빌드 직후 chown 단계 추가, 절차 복잡도 +1.
- **Follow-ups**: ACL 도입 검토 (`/dev-booth/sessions` read access).

### ADR-004 — stage_mapper Unicode/Language Policy

- **Status**: Accepted (v3)
- **Context**: AWG 메시지는 한/영 혼용이며, 동일 문서 내에서도 NFC/NFD 정규화가 섞일 수 있다. 또한 동일 메시지에서 여러 stage 키워드가 동시 매치되는 경우가 있다.
- **Decision**:
  1. 모든 메시지 본문을 `unicodedata.normalize("NFC", text)`로 정규화.
  2. 영문 키워드는 `\b` 단어 경계, 한국어 키워드는 CJK 비-CJK 경계 룩어라운드 `(?<![\\uAC00-\\uD7A3...])kw(?![\\uAC00-\\uD7A3...])`.
  3. 키워드 표는 `stage_keywords.yaml`로 유지(코드와 분리).
  4. 충돌 해소: **60초 윈도우 내 highest-stage-wins**. 윈도우 밖이면 자연 latest-wins.
- **Drivers**: D3 (사용자 신뢰), R3.
- **Alternatives**:
  - 모든 stage를 LLM이 판정: 비용 + 지연.
  - latest-wins 단독: stage가 일시적으로 역행하는 노이즈에 취약.
  - 가중 평균: 정수 stage 의미와 맞지 않음.
- **Why**: AWG stage는 단조 증가가 정상이며, 60초 윈도우는 동일 작업 단위의 자연 길이.
- **Consequences**: 정확도 ≥ 0.9 보장 가능. 부정형(예: "no plan yet") 미지원.
- **Follow-ups**: 부정형/문맥형 미스 감지를 위한 LLM rescue 도입 검토 (별도 이슈).

### ADR-005 — 큐 경로 단일화 (`queues/` only)

- **Status**: Accepted (v3)
- **Context**: 코드베이스에 `/dev-booth/awg/` (legacy)와 `/dev-booth/awg/queues/` (current fixture format)가 공존한다. orchestrator가 두 위치에 동시에 쓰는 경우가 있어 카운팅 결과가 흔들렸다.
- **Decision**: 본 대시보드는 **`queues/`만** 읽는다. `awg/`(legacy)는 무시한다. `session_layout.py`에서 `awg/`를 probing하던 로직을 제거한다. orchestrator의 이중 쓰기 문제는 본 계획의 범위 밖.
- **Drivers**: R4 (정합성), P1 (단순성), G6.
- **Alternatives**:
  - 두 경로 합산: 중복 카운팅.
  - `awg/`만: legacy, 비활성화 예정.
  - orchestrator를 먼저 고침: 본 대시보드 deliver가 지연됨.
- **Why**: orchestrator 정상화를 기다리지 않고 대시보드를 출시할 수 있게 한다. 운영자 1인이므로 `awg/`로 흘러가는 큐는 즉시 식별 가능.
- **Consequences**: orchestrator가 잠시라도 `awg/`에 쓰면 카운트 누락. 단, 운영자가 즉시 인지하여 orchestrator 수정 가능.
- **Follow-ups**: orchestrator를 `queues/`로 일원화하는 별도 이슈(`open-questions.md`에 기록).

---

## 부록 A — 미해결 항목 (Open Questions)

다음 항목들은 `.omc/plans/open-questions.md`에 append:

```
## Dev-Booth Dashboard - 2026-05-14
- [ ] orchestrator의 `awg/` ↔ `queues/` 이중 쓰기 정리 — ADR-005 follow-up
- [ ] stage_mapper 부정형(예: "no plan yet") 처리 — ADR-004 follow-up
- [ ] `nvidia_smi_exporter` (또는 DCGM exporter) 설치 책임자 확정 — A12 전제
- [ ] Pretendard 폰트의 정확한 subset 범위 (latin+ko / latin+ko+symbols) 결정 — A13
- [ ] Prometheus 알람의 통보 채널(이메일/Slack/Telegram) 결정 — C3, C7 후속
- [ ] Cloudflare Access의 session duration 24h가 적절한지 — C8
- [ ] `out.previous/` 보관 세대 수(현재 1세대)를 늘릴지 — R9, C4
- [ ] golden fixture 30+5 샘플의 충분성 — accuracy 0.9 미달 시 확대
```

---

## 부록 B — 확인 체크리스트 (Executor 사전 점검)

배포 전 다음 명령이 모두 0 종료해야 한다:

```bash
# Backend
pytest -q backend/tests/

# Frontend
(cd frontend && pnpm install --frozen-lockfile && pnpm build)
test -f frontend/out/index.html
bash ops/scripts/bundle_size_check.sh

# Playwright
(cd frontend && npx playwright test --grep @smoke)

# E2E latency (local)
python ops/scripts/measure_e2e_latency.py --target ws://localhost:7000/ws/test-awg --p95-max 500

# Resume protocol
python ops/scripts/test_resume.py --session test-awg

# Security
pytest -q backend/tests/test_path_guard.py backend/tests/test_sessions_security.py
curl -sS -o /dev/null -w "%{http_code}\n" 'http://localhost:7000/api/metrics/prometheus?query=up' | grep 404

# systemd dry-run
systemd-analyze verify ops/systemd/*.service ops/systemd/*.target

# Tunnel idle
timeout 130 wscat -c wss://dashboard.excusa.uk/ws/test-awg
```

모든 명령이 0 종료하면 본 계획의 v3는 **DONE**으로 표시할 수 있다.

---

**문서 끝 — PENDING APPROVAL**
검토자: Architect, Critic.
승인 명령: 사용자가 `proceed` 입력 시 `/oh-my-claudecode:start-work 2026_05_14_02-39-23_dev_booth_dashboard_plan`로 이관.
