# Dev-Booth 시스템 아키텍처

> 브랜치: `feat/kanban-redesign-2026-05-14` | 버전: Hermes Kanban 재플랫폼 (v2)
> 작성일: 2026-05-15

---

## 1. 전체 시스템 구성도

```
┌─────────────────────────────────────────────────────────────────────────┐
│  운영자 (mooner92)                                                        │
│                                                                         │
│  $ ./run.sh start <세션명> <레포URL> [목표] [dryrun|live]                  │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  run.sh  (gateway 진입점 + 세션 진입점)                                    │
│  - gateway_start(): dryrun env (env -u GITHUB_TOKEN -u GH_TOKEN)        │
│    PATH="$DRYRUN_BIN:$PATH" → hermes gateway run (B1 foreground,        │
│    setsid + disown, PID 3378382)                                        │
│  - core.session 호출 → 12단계 DAG 를 named Kanban board 에 seed          │
└────────────────┬────────────────────────────────┬───────────────────────┘
                 │                                │
                 ▼                                ▼
┌───────────────────────────┐     ┌───────────────────────────────────────┐
│  core/session.py           │     │  ~/.hermes/kanban/boards/             │
│  DevBoothSession           │     │    <board-slug>/                      │
│  .setup()  → boards create │────▶│       kanban.db  ◀──────────────────┐│
│  .seed()   → 12× kanban   │     │                                      ││
│    --board <slug> create   │     │  (SQLite, 6-table schema,            ││
│    --parent <id>           │     │   timestamps = seconds epoch)        ││
│    --idempotency-key ...   │     └──────────────┬───────────────────────┘│
│  → sessions/<name>/        │                    │                        │
│    status.json             │                    │                        │
│    stage_task_map.json     │                    │                        │
└───────────────────────────┘                    │                        │
                                                 │                        │
                    ┌────────────────────────────┘                        │
                    │  hermes gateway (dispatcher)                         │
                    │  폴링 주기: ~60 s (kanban.interval)                  │
                    │  ready 태스크 클레임 → assignee 기준으로              │
                    │  에이전트 프로파일 스폰                               │
                    │                                                      │
                    │  HERMES_KANBAN_TASK / DB / BOARD / WORKSPACE 주입    │
                    │  kanban-worker skill 자동 로드                        │
                    │                                                      │
                    │  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
                    │  │  conductor  │  │  architect   │  │  executor  │  │
                    │  │  지휘자     │  │  분석/설계   │  │  구현/실행 │  │
                    │  │             │  │              │  │            │  │
                    │  │ 오케스트레이│  │ 코드 분석    │  │ 구현/테스트│  │
                    │  │ 터: fork,   │  │ 리뷰, 계획   │  │ 커밋, PR   │  │
                    │  │ 요약, PR    │  │ 검토         │  │ 초안       │  │
                    │  └──────┬──────┘  └──────┬───────┘  └─────┬──────┘  │
                    │         │                │                 │         │
                    │         └────────────────┴─────────────────┘         │
                    │                          │                           │
                    │         vLLM (Qwen2.5-Coder-32B @ :8003)            │
                    │         NVIDIA A40 × 2 (각 46 GB VRAM)               │
                    │                          │                           │
                    │                kanban.db 에 상태/결과 기록 ──────────┘
                    │
                    │  (read-only)
┌───────────────────┴──────────────────────────────────────────────────────┐
│  Dashboard (A3-lite)                                                     │
│                                                                          │
│  FastAPI uvicorn :7000                   Next.js (SSR)                  │
│  dashboard/backend/                      dashboard/frontend/             │
│    routers/kanban.py                       components/KanbanBoard.tsx    │
│    services/kanban_reader.py               hooks/useKanban.ts            │
│    (CLI --json 우선, SQLite 폴백)          (WS + REST prefetch + backoff)│
│                                                                          │
│  GET  /api/kanban/boards                                                 │
│  GET  /api/kanban/boards/{slug}/tasks                                    │
│  GET  /api/kanban/boards/{slug}/stats                                    │
│  GET  /api/kanban/boards/{slug}/tasks/{id}/comments                     │
│  WS   /api/kanban/ws/kanban/{slug}   (2 s mtime 폴링)                   │
└───────────────────────────────────────────────────────────────────────┬──┘
                                                                        │
                              Cloudflare Tunnel                          │
                              dashboard.excusa.uk ◀─────────────────────┘
                              (port 7000, 기존 터널 유지)
```

**핵심 원칙:** `run.sh` 와 `core/session.py` 는 에이전트를 직접 스폰하지 않는다. 보드 시드(seed) 만 담당하며, 에이전트 스폰은 오직 `hermes gateway` 디스패처가 한다.

---

## 2. Hermes Kanban 동작 원리

### Named Board — 기본 보드와의 격리

에이전트들이 좌표하는 Kanban DB 경로:

```
~/.hermes/kanban/boards/{board-slug}/kanban.db
```

- 기본 보드(`~/.hermes/kanban.db`)와 **완전히 분리**된 named board 를 사용한다.
- 자율 git-action 시스템이 운영자의 공유 기본 보드를 오염시키지 않도록 격리한다.
- `board-slug` 는 세션명을 소문자/하이픈 형식으로 변환한 값이다 (`session_name.lower().replace("_", "-")`).

### CLI 명령 형식 (Phase 0 에서 검증)

```
hermes kanban --board <slug> create "<title>" --assignee conductor ...
```

`--board <slug>` 플래그는 **`hermes kanban` 레벨 플래그**이며 반드시 서브커맨드 앞에 위치해야 한다. 보드 관리 동사(`boards create`, `boards list`)는 슬러그를 위치 인자로 받으며 `--board` 를 사용하지 않는다.

### 12단계 DAG 시딩

`DevBoothSession.seed()` 가 `STAGE_DAG`(core/scenario.py) 를 순회하며 12개 태스크를 생성한다:

```
stage 1  [conductor]   fork & clone              --parent (없음)
stage 2  [conductor]   initial project scan       --parent stage-1-id
stage 3  [architect]   code structure analysis    --parent stage-2-id
stage 4  [executor]    dependency analysis         --parent stage-2-id  ┐ 병렬
stage 5  [conductor]   analysis summary            --parent stage-3-id, stage-4-id
stage 6  [conductor]   improvements plan           --parent stage-5-id
stage 7  [conductor]   create feature branch       --parent stage-6-id
stage 8  [executor]    implement TASK-{n}          --parent stage-7-id
stage 9  [architect]   code review                 --parent stage-8-id  ← 리뷰 게이트
stage 10 [conductor]   commit approved changes     --parent stage-9-id
stage 11 [conductor]   draft PR                    --parent stage-10-id
stage 12 [conductor]   submit PR                   --parent stage-11-id
```

각 태스크는 `--idempotency-key devbooth-{slug}-stage{n}` 으로 생성되므로 `seed()` 를 재실행해도 중복 태스크가 만들어지지 않는다 (멱등성 보장).

### 태스크 상태 생명 주기

```
triage ──▶ todo ──▶ ready ──▶ running ──▶ done
                                  │
                               blocked  (터미널 — 리뷰 게이트가
                                          정상적으로 도달할 수 있는 상태)
```

- `triage`: 생성 직후 초기 상태
- `todo`: 디스패처가 인식한 대기 상태
- `ready`: 모든 부모 태스크가 `done` 인 경우 디스패처가 자동 승격
- `running`: 디스패처가 클레임하여 워커가 실행 중
- `done`: `kanban_complete()` 호출 완료
- `blocked`: `kanban_block(reason)` 호출 — **터미널 상태**. 리뷰 게이트(stage 9)가 정당하게 여기서 종료될 수 있다

디스패처는 **모든 부모 태스크가 `done` 상태일 때만** 자식 태스크를 `ready` 로 승격한다.

---

## 3. 에이전트 간 통신 흐름

### 직접 통신 없음 — 보드를 통한 간접 협업

에이전트들은 서로 직접 메시지를 주고받지 않는다. **모든 협업은 Kanban 보드를 통해 이루어진다.**

### 디스패처가 주입하는 환경 변수

워커 스폰 시 디스패처가 다음 환경 변수를 주입한다:

| 환경 변수 | 내용 |
|---|---|
| `HERMES_KANBAN_TASK` | 현재 태스크 ID |
| `HERMES_KANBAN_DB` | kanban.db 경로 |
| `HERMES_KANBAN_BOARD` | 보드 슬러그 |
| `HERMES_KANBAN_WORKSPACE` | 워크스페이스 경로 |

`KANBAN_GUIDANCE` 는 디스패처가 자동 주입하며, `kanban-worker` 스킬도 자동 로드된다.

### 에이전트 간 협업 API

| 함수 | 용도 |
|---|---|
| `kanban_create(title, body, assignee, ...)` | 서브태스크 분해 (conductor 가 architect/executor 에게 태스크 생성) |
| `kanban_complete(summary, metadata)` | 태스크 완료 및 핸드오프 (다음 단계로 결과 전달) |
| `kanban_block(reason)` | 불확실할 때 중단 — 추측하지 않고 블로킹 |
| `kanban_comment("@architect: ...")` | 에이전트 간 토론 (개선안 합의, 리뷰 피드백) |

### 구체적 흐름 예시

```
1. conductor (stage 1)
   └─ 레포 fork/clone 수행
   └─ install_hooks.sh 실행 (dryrun Layer 1 설치)
   └─ kanban_complete(summary="clone 완료", metadata={clone_path, branch})

2. conductor (stage 2)  ← stage-1 done → ready 승격
   └─ 초기 스캔
   └─ kanban_create() → architect 에게 stage-3 (코드 구조 분석) 태스크 생성
   └─ kanban_create() → executor 에게 stage-4 (의존성 분석) 태스크 생성
   └─ kanban_complete()

3. architect (stage 3) + executor (stage 4)  ← 병렬 실행
   └─ 각자 분석 후 analysis_hermes_a.md / analysis_hermes_b.md 저장
   └─ kanban_complete(metadata={issues_found: N})

4. conductor (stage 5)  ← stage-3, stage-4 모두 done → ready 승격
   └─ kanban_show() 로 부모 태스크 findings 읽기
   └─ summary_v1.0.0.md 작성
   └─ kanban_complete()

5. conductor (stage 6)
   └─ kanban_comment("@architect: 개선 우선순위 의견?")
   └─ architect 응답 후 improvements_v0.0.1.md 확정
   └─ kanban_complete()

6. executor (stage 8)  ← stage-7 done → ready 승격
   └─ TASK 구현 + 자동 테스트
   └─ kanban_complete() 또는 kanban_block("review-required: ...")

7. architect (stage 9 — 리뷰 게이트)
   └─ 구현 검토
   └─ 통과: kanban_complete(summary="LGTM: ...")
   └─ 미통과: kanban_block("review-required: 구체적 피드백")

8. conductor (stage 10 → 11 → 12)
   └─ 커밋 → PR 초안 → PR 제출
   └─ dryrun=1: pr_draft.json 에 url="DRYRUN://no-pr" 기록
```

---

## 4. dryrun 3중 레이어 보호 구조

Dev-Booth 는 자율 에이전트가 실제 git push / PR 생성을 하지 못하도록 3중 방어 레이어를 구현한다.

### Layer 1 — per-clone git hook (best-effort)

- **위치:** 각 클론된 레포의 `.git/hooks/pre-push`
- **설치:** `core/dryrun/install_hooks.sh <clone_path>` — stage-1 conductor 가 `git clone` 직후 실행
- **동작:** `DEV_BOOTH_DRYRUN=1` 환경에서 `git push` 를 중단시킴
- **한계:** 각 클론에 개별 설치 필요. 절대 경로 `git` 사용 시 우회 불가능하지 않지만, 훅은 git 바이너리 경유 시 항상 실행됨

### Layer 2 — PATH wrapper (defense-in-depth)

- **위치:** `core/dryrun/git`, `core/dryrun/gh` — 실행 가능한 쉘 래퍼 스크립트
- **적용:** gateway 실행 시 `PATH="$DRYRUN_BIN:$PATH"` 로 래퍼를 시스템 git/gh 앞에 삽입
- **동작:**
  - `gh pr create` → `DRYRUN://no-pr` 출력 후 종료 (PR 생성 차단)
  - `git push` → `--dry-run` 플래그 추가 (실제 push 없이 시뮬레이션)
- **한계:** `/usr/bin/git` 같은 절대 경로로 호출하면 우회 가능 — 완전한 백스톱이 아닌 심층 방어

### Layer 3 — 토큰 스크럽 (기계적으로 강제되는 백스톱)

```bash
# run.sh gateway_start() dryrun 모드
env -u GITHUB_TOKEN -u GH_TOKEN DEV_BOOTH_DRYRUN=1 PATH="$DRYRUN_BIN:$PATH" \
  setsid "$HERMES" gateway run ...
```

- **동작:** `GITHUB_TOKEN` / `GH_TOKEN` 을 게이트웨이 환경에서 완전히 제거
- **효과:** 어떤 경로로도 (gh CLI, raw API, curl, 절대 경로) 인증 불가능 — **크리덴셜 자체가 없으므로 push/PR 생성 불가**
- **왜 Layer 3 가 진짜 보장인가:**
  - Layer 1 은 클론별 설치가 필요하고 누락될 수 있다
  - Layer 2 는 절대 경로 우회가 가능하다
  - Layer 3 은 **per-repo 설치 불필요, 우회 불가** — 게이트웨이 자식 프로세스 전체가 상속하는 환경에 토큰이 존재하지 않으므로 어떤 인증도 성립하지 않는다
  - 이것이 "기계적으로 강제(mechanically-enforced)"라는 의미다

live 모드 (`./run.sh start ... live`) 에서는 토큰을 스크럽하지 않아 실제 push/PR 이 가능해진다.

---

## 5. vLLM 설정

### 모델 및 하드웨어

| 항목 | 값 |
|---|---|
| 모델 | Qwen2.5-Coder-32B-Instruct |
| 서비스 포트 | 8003 |
| GPU | NVIDIA A40 × 2 (각 46 GB VRAM, 총 92 GB) |
| systemd 서비스명 | `vllm-qwen25-coder-32b` |

### Hermes 프로파일 연결

세 에이전트 프로파일(conductor / architect / executor)은 모두 `base_url` 을 vLLM 엔드포인트로 설정한다:

```
http://localhost:8003/v1
```

프로파일 설정:
- `max_turns: 40`
- `toolsets: [hermes-cli]` — code_execution / file / terminal / todo / memory 번들 포함
- kanban 도구는 toolset 이 아닌 **디스패처가 `HERMES_KANBAN_TASK` 주입 시 `kanban-worker` 스킬로 자동 로드**

Phase 0 검증 당시 프로파일은 Qwen2.5-Coder-14B 로 설정되어 있었으나, 실제 하드웨어는 32B 모델을 서비스하는 A40 × 2 구성이다. 프로파일의 `base_url` 포트 `:8003` 은 동일하게 유지된다.

---

## 6. Cloudflare Tunnel 구성

### 구성 개요

```
브라우저 (외부)
      │
      ▼
https://dashboard.excusa.uk
      │  Cloudflare Tunnel (기존 설정 유지)
      ▼
localhost:7000  (FastAPI uvicorn, PID 3391459)
      │
      ▼
dashboard/backend/main.py
  ├── (기존 라우터들)
  └── routers/kanban.py  (A3-lite 추가)
```

### Kanban 재플랫폼과의 관계

- Kanban 재플랫폼(A3-lite 결정)은 기존 대시보드를 **교체하지 않고 확장**했다.
- 포트 7000 유지, 터널 설정 변경 없음.
- `routers/kanban.py` 가 `main.py` 에 추가 등록되어 `/api/kanban/*` 엔드포인트가 기존 경로와 나란히 동작한다.
- `uvicorn` 을 재시작(`PID 3391459`)하여 새 라우터를 로드했으며, 그 외 인프라는 변경 없다.

### 노출 엔드포인트

| 경로 | 설명 |
|---|---|
| `https://dashboard.excusa.uk/` | 기존 Dev-Booth 대시보드 (Next.js) |
| `https://dashboard.excusa.uk/api/kanban/boards` | 보드 목록 |
| `https://dashboard.excusa.uk/api/kanban/boards/{slug}/tasks` | 태스크 목록 |
| `https://dashboard.excusa.uk/api/kanban/ws/kanban/{slug}` | WebSocket 실시간 피드 |

---

## 7. 데이터 흐름도

```
운영자
  │
  │  ./run.sh start <세션명> <레포URL>
  ▼
run.sh
  │  1) gateway_start() — hermes gateway run (dryrun env, B1)
  │  2) python -m core.session <세션명> <레포URL>
  ▼
session.py  (DevBoothSession.setup + .seed)
  │
  │  hermes kanban boards create <slug>
  │  hermes kanban --board <slug> create "stage-1 title"
  │    --assignee conductor --parent (없음) --idempotency-key ...
  │  hermes kanban --board <slug> create "stage-2 title"
  │    --assignee conductor --parent <stage-1-id>
  │  ... (12개 태스크, --parent 의존 링크 포함)
  │
  ▼
kanban.db  (~/.hermes/kanban/boards/<slug>/kanban.db)
  │
  │◀─────────────────────────────────────────────────────────────┐
  │                                                              │
  ▼                                                              │
hermes gateway dispatcher                                        │
  │  폴링: ready 태스크 존재 여부 확인 (~60 s 주기)               │
  │  ready 태스크 클레임 → assignee 기준 프로파일 스폰            │
  │  HERMES_KANBAN_TASK/DB/BOARD/WORKSPACE 주입                  │
  │  kanban-worker skill 자동 로드                               │
  │                                                              │
  ▼                                                              │
conductor / architect / executor (vLLM @ :8003)                  │
  │  태스크 본문 실행 (git, 분석, 구현, 리뷰, PR)                 │
  │  kanban_complete(summary, metadata)  ─────────────────────── ┤ (상태/결과 기록)
  │  kanban_block(reason)  ─────────────────────────────────────┤
  │  kanban_comment("@architect: ...")  ────────────────────────┘
  │
  │  완료 시: 디스패처가 자식 태스크 todo → ready 자동 승격
  │
  ▼
kanban.db  (tasks 테이블: status/result/comments/task_runs 갱신)
  │
  │  (read-only)
  ▼
kanban_reader.py  (KanbanReader)
  │  1차: hermes kanban --board <slug> list --json  (CLI 우선)
  │  2차: sqlite3 read-only fallback
  │       (file:{path}?mode=ro, sqlite3.Row)
  │
  ▼
routers/kanban.py  (FastAPI)
  │  REST: GET /api/kanban/boards/{slug}/tasks
  │  REST: GET /api/kanban/boards/{slug}/stats
  │  REST: GET /api/kanban/boards/{slug}/tasks/{id}/comments
  │  WS:   /api/kanban/ws/kanban/{slug}
  │        └─ db_path.stat().st_mtime 2초 폴링
  │           변경 감지 시 tasks + comments 전송
  │
  ▼
Next.js KanbanBoard (dashboard/frontend)
  │  hooks/useKanban.ts
  │    WS 연결 + REST prefetch + 지수 백오프 재연결
  │  components/KanbanBoard.tsx
  │    status-grouped 컬럼 (triage/todo/ready/running/blocked/done)
  │    running 태스크 애니메이션 인디케이터
  │    Seed 토큰 표시
  │
  ▼
브라우저 (https://dashboard.excusa.uk)
  실시간 Kanban 보드 뷰
```

---

*이 문서는 `feat/kanban-redesign-2026-05-14` 브랜치의 구현 결과 보고서(`reports/results/2026_05_14_23-58-41_devbooth_kanban_replatform.md`) 및 실제 소스 코드(`core/session.py`, `core/scenario.py`, `run.sh`, `dashboard/backend/routers/kanban.py`, `dashboard/backend/services/kanban_reader.py`)를 직접 참조하여 작성되었습니다.*
