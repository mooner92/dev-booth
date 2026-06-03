# Dev-Booth Village v2 — Star-Office-UI 원본 레포 기반 재구현

**Date:** 2026-05-16
**Branch:** `feat/kanban-redesign-2026-05-14`
**Outcome:** ✅ 라이브 (사용자 systemd 모드)

이전 React+Canvas 자체 구현을 폐기하고 **Star-Office-UI 원본 레포**
(https://github.com/ringhyacinth/Star-Office-UI)를 그대로 띄운 뒤,
Hermes Kanban → `agents-state.json` 동기화 데몬을 추가하는 방식으로 재구현했다.

---

## 0. 변경 결정 사항

- **설치 경로:** `/opt/star-office-ui` → `/home/mooner92/star-office-ui`
  (sudo 미사용 환경. operator가 원하면 setup 문서대로 `/opt` 로 승격 가능)
- **systemd:** 시스템 유닛 → 사용자 유닛 (`~/.config/systemd/user/`).
  운영 환경에서는 `loginctl enable-linger mooner92` 또는
  `/etc/systemd/system/` 로 승격 필요 (문서화 완료)
- **Star-Office-UI 백엔드 수정:** 없음. 멀티에이전트는 이미 `/agents`
  엔드포인트로 네이티브 지원하므로 동기화 데몬이 `agents-state.json` 만
  주기적으로 덮어쓰면 됨. **원본 코드 단 한 줄도 수정하지 않음.**

---

## 1. 설치된 컴포넌트

```
~/star-office-ui/                       # Star-Office-UI v2 원본 (.git 제거)
├── backend/app.py                      # 원본 Flask (미수정)
├── frontend/                           # Phaser.js 원본 (미수정)
├── state.json                          # 시작 시 sync가 conductor 뷰로 갱신
├── agents-state.json                   # sync가 2초마다 전체 덮어씀
├── join-keys.json                      # 샘플 그대로 (멀티에이전트 인증 미사용)
└── devbooth_sync.py                    # 신규: Kanban → agents-state.json

~/.config/systemd/user/
├── star-office-ui.service              # Flask :19000
└── star-office-sync.service            # devbooth_sync.py 데몬

/dev-booth/
├── dashboard/frontend/app/village/page.tsx  # 캔버스 → iframe 교체
└── docs/village_operator_setup.md           # sudo 후속 작업 가이드
```

---

## 2. 동작 검증 (curl 캡처)

### `/health`
```json
{"service":"star-office-ui","status":"ok","timestamp":"2026-05-16T16:08:53.885669"}
```

### `/status`
```json
{
  "board":"agent-working-group-20260517",
  "detail":"initial project scan",
  "progress":0,
  "state":"executing",
  "updated_at":"2026-05-16T16:08:52.485039"
}
```

### `/agents` (요약)
```json
[
  {"agentId":"devbooth-conductor","name":"Conductor","state":"executing","area":"writing",
   "detail":"initial project scan","task_status":"running"},
  {"agentId":"devbooth-architect","name":"Architect","state":"idle","area":"breakroom",
   "detail":"[agent-working-group-20260517] 대기 중","task_status":"idle"},
  {"agentId":"devbooth-executor","name":"Executor","state":"idle","area":"breakroom",
   "detail":"[agent-working-group-20260517] 대기 중","task_status":"idle"}
]
```

### Star-Office-UI 픽셀 오피스 응답
```
HTTP 200, 246704 bytes, content-type: text/html; charset=utf-8
<title>Star 의 像素办公室</title>
```

### Next.js `/village` (FastAPI 정적 서빙, port 7000)
```
HTTP 200
<h1>🏢 Dev-Booth Village</h1> ... powered by Star-Office-UI ...
<iframe src="https://village.excusa.uk" title="Dev-Booth Village (Star-Office-UI)" ...>
```

> iframe `src` 는 클라이언트에서 hostname 으로 자동 분기:
> localhost / 127.0.0.1 / 192.168.x.x / 10.x.x.x → `http://<host>:19000`,
> 그 외 → `https://village.excusa.uk`

### Boards API
```json
{"boards":["agent-working-group-20260517","e2e-kanban-001","firebase-001","firebase-003","globalteamproject-20260515"]}
```

### 서비스 상태
```
star-office-ui.service     Active: active (running) since 16:06:38
star-office-sync.service   Active: active (running) since 16:06:40
agents-state.json mtime    2026-05-16 16:08:53  (2초 간격으로 갱신 중)
```

---

## 3. 상태 매핑 (Hermes Kanban → Star-Office)

`devbooth_sync.py` 의 `KANBAN_TO_STAR`:

| Hermes Kanban status | Star-Office state | 사무실 위치 |
|----------------------|-------------------|-------------|
| `running`            | `executing`       | 책상 (writing) |
| `blocked`            | `error`           | 버그 영역 (error) |
| `ready`              | `syncing`         | 책상 |
| `done` / `todo` / `triage` / `archived` | `idle` | 휴식 영역 (breakroom) |

에이전트별 우선순위: `running > blocked > idle` (가장 최근 활동 task 1개 선택).

`VALID_AGENT_STATES = {idle, writing, researching, executing, syncing, error}` —
Star-Office 원본의 `normalize_agent_state` 가 검증.

---

## 4. 빌드 결과

```
✓ Compiled successfully
✓ Generating static pages (6/6)
○ /village                              1.42 kB        95.5 kB
```

TypeScript / ESLint 에러 0개.

---

## 5. 운영자 후속 작업 (sudo 필요 — 문서화됨)

자세한 절차는 `/dev-booth/docs/village_operator_setup.md` 참고.

1. **(선택) `/opt/star-office-ui` 로 승격** — rsync + 유닛 경로 갱신
2. **사용자 → 시스템 systemd 승격** —
   `sudo loginctl enable-linger mooner92` 또는 `/etc/systemd/system/` 로 복사
3. **Cloudflare Tunnel ingress 추가** — `/etc/cloudflared/config.yml` 에
   `hostname: village.excusa.uk` → `http://localhost:19000` 룰 추가 후
   `sudo cloudflared tunnel route dns <tunnel> village.excusa.uk` +
   `sudo systemctl restart cloudflared`
4. **프로덕션 시크릿 설정** — `FLASK_SECRET_KEY`, `ASSET_DRAWER_PASS`
   (현재 dev 모드라 기본 1234 사용 중)

---

## 6. 완료 체크리스트

| 항목 | 상태 |
|------|------|
| `~/star-office-ui` 원본 레포 설치 (목표 `/opt/star-office-ui`) | ✅ (경로 변경) |
| star-office-ui 사용자 systemd active (running) | ✅ |
| star-office-sync 사용자 systemd active (running) | ✅ |
| http://localhost:19000 → 픽셀 오피스 (246 KB HTML) | ✅ |
| `agents-state.json` 이 Kanban 상태와 2초 주기 동기화 | ✅ |
| /village 페이지가 iframe 으로 Star-Office-UI 임베드 | ✅ |
| running → `executing` (책상) | ✅ |
| blocked → `error` (버그 영역) | ✅ (mapping 검증, blocked task 없는 보드라 라이브 capture 불가) |
| idle/done → `idle` (휴식 영역) | ✅ |
| Cloudflare Tunnel village.excusa.uk 설정 문서화 | ✅ (operator TODO) |
| git commit | (다음 단계) |

---

## 7. 금지 사항 준수

- ✅ Star-Office-UI 원본 frontend HTML/JS/CSS 미수정
- ✅ Star-Office-UI backend/app.py 미수정 (멀티에이전트는 네이티브 지원)
- ✅ 기존 /dev-booth 백엔드 API 미수정 (`/api/village/*` 는 보드 목록만
  iframe header에서 사용; 라우터 자체는 미변경)
- ✅ Canvas 기반 구현 폐기 (page.tsx 완전 교체)
- ✅ main 브랜치 미수정 (`feat/kanban-redesign-2026-05-14` 유지)
- ✅ sudo 필요 작업은 operator TODO 로 문서화
