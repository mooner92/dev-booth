# Dev-Booth — 기술 개요 (Technical Overview)

> 작성일: 2026-06-01 · 브랜치: `feat/kanban-redesign-2026-05-14`
> 본 문서는 저장소의 **실제 소스 코드**(`core/`, `dashboard/`, `run.sh`, `tests/`, `config/`)를 직접 검토하여 작성되었으며, 스테이지 수·실행 모드·엔드포인트 등 모든 기술적 주장은 코드와 대조해 검증되었다.
> 기존 `docs/ARCHITECTURE.md`(v2, 2026-05-15)는 **12단계 / dryrun 기본** 모델을 기술하고 있어 현재 코드(21단계 / always-live)와 어긋난다. 그 불일치 목록과 권고는 [개선 보고서](../reports/results/)에 정리되어 있다.

---

## Abstract

### English

**Dev-Booth** is a fully-local autonomous software-development system. Three local-LLM agents — `conductor`, `architect`, and `executor` — collaborate **exclusively through a Hermes Kanban board** (a SQLite-backed task queue); they never message each other directly. A separately-running `hermes gateway` dispatcher polls the board, claims any task whose parents are all `done`, and spawns the assigned agent profile as a worker backed by a local vLLM instance. Each agent's behaviour is shaped by a `SOUL.md` persona and a `MEMORY.md` operating note. The current scenario is a **21-stage v6 micro-task DAG** (`core/scenario.py`) that walks a target repository from fork → analysis → planning → two implement/test/review lanes → commit → pull request. A FastAPI (`:7000`) + Next.js 14 dashboard, published at `dashboard.excusa.uk` through a Cloudflare Tunnel, visualises the board, agent transcripts, and a pixel-office "Village" view. It is **read-only** apart from two write actions: starting a new session (`POST /api/sessions/start`, wired to the New-Session modal) and unblocking a task (`POST …/unblock`). Code changes are submitted as pull requests from the bot account **CrownClownCrowd**; final merge authority rests with the human operator.

### 한국어

**Dev-Booth**는 완전 로컬에서 구동되는 자율 소프트웨어 개발 시스템이다. 세 개의 로컬 LLM 에이전트(`conductor`·`architect`·`executor`)가 서로 직접 대화하지 않고 **오직 Hermes Kanban 보드(SQLite 태스크 큐)를 통해서만** 협업한다. 별도로 상주하는 `hermes gateway` 디스패처가 보드를 폴링하여 부모 태스크가 모두 `done`인 태스크를 클레임하고, 담당 에이전트 프로파일을 로컬 vLLM 백엔드 워커로 스폰한다. 각 에이전트의 행동은 `SOUL.md`(인격)와 `MEMORY.md`(운영 노트)로 규정된다. 현재 시나리오는 fork → 분석 → 계획 → 2개의 구현/테스트/리뷰 레인 → 커밋 → PR로 이어지는 **21단계 v6 마이크로 태스크 DAG**(`core/scenario.py`)이다. FastAPI(`:7000`) + Next.js 14 대시보드가 Cloudflare Tunnel을 통해 `dashboard.excusa.uk`로 공개되며, 보드·에이전트 대화·픽셀 오피스 "Village" 뷰를 보여 준다. 기본은 **읽기 전용**이며 상태를 바꾸는 동작은 두 가지뿐이다 — 새 세션 시작(`POST /api/sessions/start`, New-Session 모달과 연결)과 태스크 unblock(`POST …/unblock`). 코드 변경은 봇 계정 **CrownClownCrowd**가 PR로 제출하고, 최종 머지 권한은 운영자에게 있다.

---

## 1. 시스템 한눈에 보기

```
┌────────────────────────────────────────────────────────────────────────┐
│ 운영자 (operator)                                                       │
│   $ ./run.sh start <세션명> <레포URL> [목표] [dryrun|live]              │
│   또는 대시보드  POST /api/sessions/start                               │
└───────────────┬────────────────────────────────────────────────────────┘
                │
                ▼  ① 보드 시드 (board seed) — 에이전트는 스폰하지 않음
┌────────────────────────────────────────────────────────────────────────┐
│ core/session.py  DevBoothSession.setup()/seed()                         │
│   · 세션명 → board-slug (소문자, _·공백 → -)                            │
│   · core/scenario.py 의 21-stage STAGE_DAG 를 순회하며                  │
│     hermes kanban --board <slug> create ... --parent <부모태스크id>     │
│     --idempotency-key devbooth-<slug>-stage<N>                          │
│   · sessions/<name>/{status.json, stage_task_map.json, log/} 기록       │
└───────────────┬────────────────────────────────────────────────────────┘
                │ 태스크 생성
                ▼
┌────────────────────────────────────────────────────────────────────────┐
│ ~/.hermes/kanban/boards/<slug>/kanban.db   (SQLite, named board)        │
└───────────────┬───────────────────────────────────────▲────────────────┘
                │ ready 태스크 클레임                       │ 상태/결과 기록
                ▼                                          │
┌────────────────────────────────────────────────────────┴────────────────┐
│ hermes gateway (dispatcher, 상주)                                        │
│   · 부모가 모두 done 인 태스크를 ready 로 승격 → claim                   │
│   · assignee 기준 프로파일 스폰; 환경변수 주입                            │
│     HERMES_KANBAN_TASK / DB / BOARD / WORKSPACE + kanban-worker 스킬     │
│                                                                          │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐                            │
│   │conductor │   │architect │   │executor  │   ← SOUL.md + MEMORY.md     │
│   │ 지휘·PR   │   │ 분석·리뷰 │   │ 구현·테스트│                            │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘                            │
│        └──────────────┴──────────────┘                                  │
│        vLLM (Qwen2.5-Coder-32B @ localhost:8003, NVIDIA A40 × 2)        │
│        kanban_complete() / kanban_block() / kanban_comment() 로만 협업   │
└───────────────┬──────────────────────────────────────────────────────────┘
                │ (read-only)
                ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Dashboard — FastAPI :7000  +  Next.js 14 (static export)                │
│   routers: health · sessions · github · metrics · ws · kanban           │
│            · village · village_proxy                                     │
│   services: kanban_reader(CLI→SQLite fallback) · stage_mapper            │
│             · log_tailer · session_hub · village_status · path_guard …   │
│   frontend: / (세션 목록) · /session/[name] (보드+채팅) · /village       │
│                                                                          │
│   Cloudflare Tunnel → dashboard.excusa.uk (port 7000)                   │
└────────────────────────────────────────────────────────────────────────┘
```

**핵심 원칙:** `run.sh`와 `core/session.py`는 **에이전트를 직접 스폰하지 않는다.** 보드 시드만 담당하고, 에이전트 스폰은 오직 `hermes gateway` 디스패처가 한다. 이는 v1(`archive/v1-stateless-orchestrator/`)의 in-process 상태 머신과 대비되는 v2의 결정적 차이다(§9 참고).

---

## 2. 저장소 구조 — 두 개의 하위 시스템

이 저장소에는 사실상 **두 개의 독립 프로젝트**가 한 트리에 공존한다.

| 경로 | 무엇인가 | git 추적 |
|---|---|---|
| `core/` `dashboard/` `run.sh` `tests/` `config/` `docs/` `reports/` `archive/` | **Dev-Booth** 본체 (이 문서의 대상) | 추적됨 (총 176개 파일) |
| `agent-working-group/` | **AWG** — 독립적인 파일 기반 메시지 큐 라이브러리. 자체 `pyproject.toml`·`.git`·대시보드·테스트를 가진 별도 프로젝트 | **`.gitignore`에 등재 → 추적 안 됨** (§8) |

```
/dev-booth/
├── run.sh                       # 운영자 진입점 (start/stop/watch/board/gateway …)
├── core/
│   ├── scenario.py              # 21-stage v6 마이크로 DAG (STAGE_DAG, STAGE_NARRATION)
│   ├── session.py               # DevBoothSession — 보드 생성 + DAG 시드 (에이전트 미실행)
│   ├── watchdog.py              # protocol_violation 리퍼 (stuck 태스크 → block)
│   ├── souls/                   # 에이전트 인격: conductor/architect/executor.SOUL.md
│   ├── memories/                # 에이전트 지속 메모리: *.MEMORY.md
│   └── dryrun/                  # git/gh/pre-push/install_hooks.sh — ⚠ 현재 dead code (§5)
├── dashboard/
│   ├── backend/                 # FastAPI :7000 — routers/ services/ scripts/ tests/
│   ├── frontend/                # Next.js 14 (output: export) — app/ components/ hooks/ lib/
│   └── ops/                     # systemd unit, cloudflared ingress, access policy
├── tests/                       # v2 라이브 테스트 (144개) + e2e/ 셸 스크립트
├── archive/
│   ├── v1-stateless-orchestrator/  # 구버전(v1) in-process 오케스트레이터 + 테스트 (dead)
│   └── bots/                       # 최초 프로토타입: Discord 봇 (hermes.py, openclaw.py)
├── reports/{plans,results}/     # 설계 계획서 / 구현·분석 결과 보고서
├── docs/                        # ARCHITECTURE / MANUAL / QUICKSTART / village_operator_setup
├── config/                      # hermes-gateway.service(추적) + .env(gitignored)
├── sessions/                    # 런타임 세션 산출물 (gitignored)
└── agent-working-group/         # 벤더링된 별도 프로젝트 (gitignored, §8)
```

---

## 3. 핵심 엔진 — `core/`

### 3.1 `scenario.py` — 21단계 v6 마이크로 DAG

순수 데이터 + 포매팅 모듈이다. 에이전트를 실행하지 않는다. `STAGE_DAG`는 21개의 `StageTask`로 이루어진 정적 DAG이며, 각 노드는 `stage / title / assignee / workspace / tag / body_template / parent_stages / is_review_gate / skills`를 가진다.

v6(마이크로 태스크) 설계 의도(`scenario.py:1-17`): 모든 스테이지는 **5턴·~28K 컨텍스트** 예산에 맞춰져 있고, 각 body는 (a) 2,000자 미만, (b) `cat` 금지·`head -n N`만 허용하는 파일 읽기 규칙(`_FILE_READING_RULE`)을 머리에 붙이며, (c) 읽을 파일 최대 3개·쓸 파일 1개를 명시하고, (d) 리터럴 `kanban_complete(...)`(필요 시 `kanban_block(...)`)로 끝나 `protocol_violation` 실패를 0으로 유지한다.

**21-stage DAG (담당 / 부모 / 리뷰게이트):**

| # | 담당 | 부모 | 게이트 | 단계 |
|---|------|------|:--:|------|
| 1 | conductor | — | | fork & clone (`gh repo fork` → clone → `git checkout -b develop`) |
| 2 | conductor | 1 | | 디렉터리 구조 파악 |
| 3 | conductor | 2 | | README + 패키지 파일 분석 (기술 스택) |
| 4 | architect | 3 | | 진입점 파일 분석 |
| 5 | architect | 4 | | 컴포넌트/모듈 분석 1/2 |
| 6 | architect | 5 | | 컴포넌트/모듈 분석 2/2 |
| 7 | architect | 3 | | API/라우터 분석 |
| 8 | executor | 3 | | 설정/환경 분석 (`.env`는 읽지 않음) |
| 9 | executor | 3 | | 의존성/취약점 분석 |
| 10 | conductor | 6,7,8,9 | | 분석 결과 취합 → `summary_v1.0.0.md` (**fan-in**) |
| 11 | conductor | 10 | | 개선방안 TASK 목록 → `improvements_v0.0.1.md` (TASK-1, TASK-2) |
| 12 | conductor | 11 | | feature 브랜치 생성 (`feature/devbooth-{session}-improvements`) |
| 13 | executor | 12 | | **TASK-1** 구현 |
| 14 | executor | 13 | | TASK-1 테스트 |
| 15 | architect | 14 | ✅ | TASK-1 코드 리뷰 (review gate) |
| 16 | executor | 15 | | **TASK-2** 구현 |
| 17 | executor | 16 | | TASK-2 테스트 |
| 18 | architect | 17 | ✅ | TASK-2 코드 리뷰 (review gate) |
| 19 | conductor | 18 | | 변경사항 커밋 + push |
| 20 | conductor | 19 | | PR 초안 작성 (`pr_draft.json`) |
| 21 | conductor | 20 | | PR 제출 (`gh pr create --repo {repo_owner}/{repo} --base main --head CrownClownCrowd:…`) |

- **DAG 형태:** 대부분 선형이며 stage 3에서 한 번 **fan-out**(자식 4·7·8·9), stage 10에서 한 번 **fan-in**(부모 6·7·8·9). architect의 컴포넌트 분석은 5→6 체인으로 직렬화된다.
- **리뷰 게이트:** stage 15·18 두 곳뿐(`is_review_gate=True`). 리뷰 미통과 시 `kanban_block("review-required: …")`가 정당한 종료다.
- **담당 분포:** conductor [1,2,3,10,11,12,19,20,21] · architect [4,5,6,7,15,18] · executor [8,9,13,14,16,17]. `ALLOWED_ASSIGNEES = {conductor, architect, executor}`이며, 시드 시 다른 assignee가 있으면 `ValueError`를 던진다.
- **`STAGE_NARRATION`** (`dict[int,str]`, 1..21): 대시보드 `stage_mapper.detect_stage()`가 **단조 비감소**가 되도록 키워드를 맞춘 표현용 메타데이터다. 대시보드는 의도적으로 21개 DAG 스테이지를 12개 표시 스테이지로 **접어서**(collapse) 보여 준다(§6.3, `test_stage_narration_crossseam.py`가 이 접힘을 강제).
- **`format_task(stage, **kwargs)`**: body_template을 `str.format`으로 렌더링한 뒤 스킬 풋터를 붙여 `hermes kanban create` 파라미터(`title/assignee/workspace/tag/body`)를 만든다. body 안의 리터럴 `{`·`}`는 `{{`·`}}`로 이스케이프되어 있다.

### 3.2 `session.py` — `DevBoothSession` (시드 전용)

- `setup()`: 세션 디렉터리 + `log/` 생성 → 기존 보드 목록 조회 후 **slug가 없을 때만** 보드 생성(멱등) → `status.json`(step=0) 기록 → `seed()` 호출.
- `seed()`: `STAGE_DAG`를 순회하며 `hermes kanban --board <slug> create <title> --assignee … --workspace worktree --body … --priority 1 --idempotency-key devbooth-<slug>-stage<N> --json`을 실행하고, 각 부모 스테이지의 task_id를 `--parent`로 연결한다. `stage_task_map.json`(stage_no → task_id)을 기록한다.
- **멱등성:** `--idempotency-key devbooth-{slug}-stage{N}`가 Hermes 레벨에서 재시드를 무해하게 만든다(중복 태스크 생성 안 됨).
- **CLI 규약:** `--board <slug>`는 `hermes kanban` **레벨 플래그**이므로 서브커맨드 앞에 와야 한다. `boards create/list`는 슬러그를 위치 인자로 받고 `--board`를 쓰지 않는다.
- **산출물:** `status.json`(운영자용 아티팩트 — 대시보드는 보드를 직접 읽지 이 파일을 읽지 않는다), `stage_task_map.json`.

### 3.3 `watchdog.py` — protocol-violation 리퍼

Hermes v0.13.0의 자체 재시도가 아직 처리하지 못한 틈을 메우는 **out-of-band** 도구다. `status='running'`인데 최신 run의 outcome이 `{completed, blocked}`도 아니고 `running`도 아닌 태스크(=비정상 종료, 사실상 stuck)를 찾아 `hermes kanban block --reason "protocol_violation: …"`으로 터미널·재시도 가능 상태로 만든다. `python3 -m core.watchdog --board <slug> [--dry-run]`로 실행하며, **자체 스케줄링하지 않는다**(운영자가 systemd 타이머로 연결해야 함).

### 3.4 에이전트 인격 — `souls/` + `memories/`

세 SOUL.md는 거의 동일한 프리앰블(약 46–47줄, conductor만 단계 전환 `kanban_comment` 한 줄을 추가로 가짐)을 공유한다: (a) **2-call 생명주기 규칙**(`kanban_complete` 또는 `kanban_block` 중 하나로 끝내야 하며, 아니면 `protocol_violation`으로 자동 `blocked`), (b) **파일 읽기 규칙**(28K 컨텍스트, `cat` 금지, `head -n 100`, 최대 3파일), (c) **팀 공지 규칙**(상태 전이 시에만 `kanban_comment`).

| 에이전트 | 역할 | 주요 동사 | 제약 |
|---|---|---|---|
| **conductor** | 수석 지휘자 — 보드 관찰, `kanban_create`로 분해, 최종 리뷰 승인·커밋·PR | create / complete / block / comment | **직접 구현하지 않고 분해만** 한다. 봇=CrownClownCrowd, upstream owner는 매 세션 `{repo_owner}`로 추출 |
| **architect** | 분석·설계·코드 리뷰 | show / complete / block / comment | git remote 작업(push/PR) **안 함**. 리뷰 통과 시 `LGTM`, 미통과 시 `review-required` block |
| **executor** | 구현·테스트·**로컬** 커밋 | show / complete / block / comment | push는 conductor가 함. ⚠ 현재 SOUL/MEMORY에 stale한 "Dryrun 규칙" 절이 남아 있음(§5) |

`MEMORY.md`(에이전트당 ~1.4–1.6KB, 2200자 캡)는 서버 환경(vLLM `localhost:8003`, max_model_len 32K), 클론/워크스페이스 경로, GitHub 봇 설정, kanban 규칙, 컨텍스트 예산(max_turns·context 28000)을 담는다.

---

## 4. Hermes Kanban 협업 메커니즘

### 4.1 Named board — 운영자 기본 보드와의 격리

에이전트가 좌표하는 DB는 `~/.hermes/kanban/boards/<slug>/kanban.db`로, 운영자의 공유 기본 보드(`~/.hermes/kanban.db`)와 **완전히 분리**된다. 자율 git-action 시스템이 운영자 보드를 오염시키지 않도록 하기 위함이다. `slug = session_name.lower().replace("_","-").replace(" ","-")`.

### 4.2 태스크 상태 생명주기

```
triage ──▶ todo ──▶ ready ──▶ running ──▶ done
                                 │
                              blocked  (터미널 — 리뷰 게이트가 정당하게 도달 가능)
```

디스패처는 **모든 부모가 `done`일 때만** 자식을 `ready`로 승격한다. `blocked`는 리뷰 게이트(stage 15·18)나 불확실 상황에서 정당하게 도달하는 터미널 상태다.

### 4.3 디스패처 환경변수 주입 + 협업 API

| 환경변수 | 내용 |  | 협업 함수 | 용도 |
|---|---|---|---|---|
| `HERMES_KANBAN_TASK` | 현재 태스크 ID |  | `kanban_create(...)` | 서브태스크 분해(conductor) |
| `HERMES_KANBAN_DB` | kanban.db 경로 |  | `kanban_complete(summary, metadata)` | 완료 + 핸드오프 |
| `HERMES_KANBAN_BOARD` | 보드 슬러그 |  | `kanban_block(reason)` | 추측 대신 중단 |
| `HERMES_KANBAN_WORKSPACE` | 워크스페이스 경로 |  | `kanban_comment("@architect: …")` | 상태 전이 공지 |

`kanban-worker` 스킬과 `KANBAN_GUIDANCE`는 디스패처가 자동 주입·로드한다.

---

## 5. 실행 모드 — always-live 전환 (그리고 현재의 불일치)

Dev-Booth는 **dryrun 기본 → always-live**로 전환 중이며, 현재 소스 트리는 **내부적으로 모순된 상태**다. 이 점은 본 문서가 가장 분명히 짚는 사실이다.

- **에이전트 시나리오는 always-live.** 워킹 트리(미커밋)의 `core/scenario.py`·`core/session.py`·`core/souls/conductor.SOUL.md`는 dryrun 분기·`install_hooks.sh` 호출·`DRYRUN://no-pr`를 모두 제거했다. stage 1은 실제 `gh repo fork`, stage 12/19는 실제 `git push`, stage 21은 무조건 `gh pr create`를 한다. `grep -in dryrun core/scenario.py` → 결과 없음.
- **그러나 `run.sh`(커밋됨)는 여전히 dryrun을 기본값으로** 둔다: `cmd_start`의 `MODE="${4:-dryrun}"`, `gateway_start`의 기본 `dryrun`, 그리고 dryrun 분기에서 `env -u GITHUB_TOKEN -u GH_TOKEN DEV_BOOTH_DRYRUN=1 PATH="$DRYRUN_BIN:$PATH"`로 **토큰을 스크럽**한다. `config/hermes-gateway.service`도 `DEV_BOOTH_DRYRUN=1` + 토큰 스크럽을 baked-in 한다. (덤: `run.sh`의 **live 분기**(`run.sh:52`)조차 `PATH="$DRYRUN_BIN:$PATH"`로 dryrun 셰임 디렉터리를 PATH 앞에 둔다 — `DEV_BOOTH_DRYRUN=0`이라 셰임은 passthrough지만, 이제 dead인 디렉터리가 양쪽 경로 모두에 남아 있다.)
- **결과(critical):** 기본 호출 `./run.sh start <s> <repo>`(live 인자 없이)는 토큰이 제거된 게이트웨이를 띄우는데, always-live 시나리오는 토큰을 요구하므로 stage 1·12·19·21이 인증 오류로 실패한다. dryrun 폴백 코드 경로가 시나리오에서 사라졌으므로 실행이 도중에 죽는다.
- **dead code:** `core/dryrun/{git,gh,pre-push,install_hooks.sh}`는 더 이상 시나리오에서 호출되지 않는다(유일한 잔존 참조는 `run.sh`의 `DRYRUN_BIN` PATH 주입). `commit c663b5c "remove dryrun mode — always live"`는 session/dashboard에서만 dryrun을 제거하고 `run.sh`·`core/dryrun/`는 건드리지 않았다.

> **권고:** dryrun 제거를 원자적으로 완료할 것 — `run.sh` 기본값을 `live`로 바꾸고 `$DRYRUN_BIN` PATH 주입·토큰 스크럽·`core/dryrun/`를 삭제하거나, 반대로 dryrun을 유지하려면 시나리오/SOUL에 dryrun 분기를 복원할 것. 절반 상태로 두지 말 것. 상세는 [개선 보고서](../reports/results/) 참고.

---

## 6. 대시보드 — 백엔드 (FastAPI `:7000`)

### 6.1 앱 구성 (`main.py`)

- `lifespan`에서 `SessionListCache`(5초 TTL), `HubRegistry`(세션별 WS 허브), `PrometheusProxy`(프리셋 전용 PromQL)를 `app.state` 싱글턴으로 생성한다.
- **CORS:** `allow_origins`는 localhost/127.0.0.1(:3001·:7000), 메서드 `GET, POST`만 허용.
- **라우터 등록 순서:** `health · sessions · github · metrics · ws · kanban · village · village_proxy`.
- **단일 포트 SPA 서빙(프로덕션):** `DASHBOARD_STATIC_DIR`가 디렉터리면 `/session/{name:path}`를 next-export 플레이스홀더로 서빙하고 `/`에 정적 파일을 mount한다(mount는 마지막 — `/api/*`·`/ws/*`가 우선).

### 6.2 엔드포인트 표 (검증됨)

| 라우터(prefix) | 메서드/경로 | 용도 |
|---|---|---|
| health (`/api`) | GET `/api/health` | liveness `{ok, version, sessions_root}` |
| sessions (`/api`) | POST `/api/sessions/start` | slug 검증 → BackgroundTasks로 `core.session` 시드 서브프로세스(409 dir exists) |
| | GET `/api/sessions` | 세션 목록(5초 캐시) |
| | GET `/api/sessions/{name}` | 세션 상세(status/agents) |
| | GET `/api/sessions/{name}/status` | 상태 스냅샷 (허브 캐시 우선) |
| | GET `/api/sessions/{name}/files` | 파일 트리(≤depth 6, symlink-escape 필터) |
| | GET `/api/sessions/{name}/file?path=` | 파일 내용(path_guard, 8MiB 절단) |
| | GET `/api/sessions/{name}/logs?after=&limit=` | 로그 페이지(`inode:offset` 시퀀스 페이징) |
| | GET `/api/sessions/{name}/queues` | AWG 형식 큐 깊이(데모/레거시) |
| github (`/api/github`) | GET `/api/github/status` | `gh auth status` → CrownClownCrowd 로그인 여부 |
| metrics (`/api/metrics`) | GET `/api/metrics/preset/{name}` | 명명 프리셋 Prometheus 쿼리 |
| | GET `/api/metrics/internal` | 드롭 구독/WS 재연결/누락 하트비트 카운터 |
| ws | WS `/ws/{session}` | 실시간 로그 fan-out (hello/subscribe/resume_from/reset, 20초 하트비트, 60초 idle close) |
| kanban (`/api/kanban`) | GET `/api/kanban/boards` | 보드 목록 |
| | **POST** `/api/kanban/boards/{slug}/tasks/{id}/unblock` | **kanban 라우터 유일의 쓰기** — `hermes kanban unblock` (백엔드 전체로는 `POST /sessions/start`와 함께 2개의 쓰기) |
| | GET `…/tasks?status=` · `…/stats` · `…/tasks/{id}/comments` · `…/tasks/{id}/log` · `…/timeline` | 태스크/통계/코멘트/로그/타임라인 |
| | WS `/ws/kanban/{slug}` | kanban.db mtime 2초 폴링 → `kanban_update` |
| village (`/api/village`) | GET `/api/village/boards` · `…/{slug}/state` · WS `/api/village/ws/{slug}` | 픽셀 오피스 투영 + 2초 mtime 폴링 |
| village_proxy (`/api/village-iframe`) | GET/POST/PUT/DELETE/OPTIONS `/{path}` | Star-Office-UI(`localhost:19000`)로의 same-origin 리버스 프록시(§7) |

### 6.3 주요 서비스

- **`kanban_reader.py`** — Hermes 보드 읽기. **CLI 우선**(`hermes kanban --board <slug> list --json`) → 실패 시 **SQLite 폴백**(`file:…?mode=ro` 읽기 전용 연결). 일부 집계(`get_all_comments`/`get_status_change_events`/`get_board_stats`)는 CLI에 `--json`이 없어 SQLite 직접 조회만 한다.
- **`stage_mapper.py`** — KO+EN 키워드로 narration → 스테이지를 추정. **여전히 12 스테이지 모델**(1 repo_clone … 12 pr_merged)이며, 21개 DAG를 12개 표시 스테이지로 접는다. `test_stage_narration_crossseam.py`가 이 접힘(키 일치·단조성·시작/끝 매핑)을 강제하므로 버그가 아니라 의도된 seam이지만, mapper의 "12 stages" 표현은 v6 기준으로는 stale하다.
- **`log_tailer.py` / `session_hub.py`** — `messages.jsonl`을 200ms 폴링으로 tailing, 1000개 링버퍼, inode 변화=rotation·size<offset=truncation 감지, `seq="inode:offset"` 재개 지원. 느린 소비자(QueueFull)는 드롭+카운트.
- **`village_status.py`** — 보드를 픽셀 오피스 형태로 투영(에이전트별 가장 관련 태스크 선택, kanban 상태 → village 상태 매핑, 데스크 좌표·이모지 부착, `progress = round(done/total × 100)` 정수 퍼센트).
- **`path_guard.py`** — resolve + `is_relative_to(root)` + 조상 symlink 탈출 거부의 3중 방어.
- **`prometheus_proxy.py`** — 5개 명명 프리셋만 허용(자유 PromQL 거부 = SSRF 방어), 5초 캐시.
- **`awg_inspector.py`** — `<root>/queues/<agent>/<state>/`의 `*.json`을 카운트. AWG에서 **임포트가 아니라 패턴만 복사**(§8).

### 6.4 WebSocket 두 종류

- **`/ws/{session}`** — 풍부한 프로토콜(hello/subscribe/resume_from/reset/log/status/heartbeat), `SessionHub`의 200ms tailer가 구동.
- **`/ws/kanban/{slug}` · `/api/village/ws/{slug}`** — 동일한 **2초 mtime 폴링** 패턴(변경 시 `asyncio.to_thread`로 페이로드 재계산 후 push), 하트비트·idle 타임아웃 없음.

---

## 7. 대시보드 — 프론트엔드 (Next.js 14)

- **빌드:** Next 14.2.15, React 18.3, `output: "export"`(정적 HTML, 프로덕션에 Node 서버 없음). 개발 스크립트는 포트 **3001**, dev `rewrites()`는 `/api`·`/ws`를 `:7001`로 프록시(프로덕션은 FastAPI가 same-origin으로 `out/` 서빙). Tailwind "Seed Design" 토큰(brand orange `#FF6F0F`, agent별 색), Pretendard 폰트.
- **라우트 3개:** `/`(세션 목록 — 5초 폴링, StatCard·SessionCard·NewSessionModal), `/session/[name]`(`force-static` + 단일 플레이스홀더 페이지; 클라이언트가 `window.location.pathname`에서 실제 이름을 읽음 → FastAPI가 임의 `/session/<name>`에 같은 HTML 서빙), `/village`(Star-Office-UI iframe 호스트).
- **데이터 계층:** `lib/api.ts`(REST, `cache:"no-store"`), `lib/ws.ts`(`SessionSocket` — 지수 백오프 `[500,1000,2000,4000,8000]`ms+지터), `hooks/useKanban.ts`(REST prefetch tasks/stats/timeline + `/ws/kanban/<slug>` 구독).
- **주요 컴포넌트:** `SessionDetailClient`(좌 240px 칸반 + 우 채팅), `KanbanBoard`(상태 아이콘·GPU 푸터), `ChatStream`(팀 타임라인 / 태스크 로그 2탭, noise 필터·그룹핑·sticky autoscroll), `ChatMessage`(`\uXXXX` 언이스케이프·태그 strip·마크다운 렌더), `UnblockBanner`(unblock CTA + 일괄 `unblockAll()`), `NewSessionModal`.
- **village 통합(§7):** 아래 참조.

> ⚠ 프론트엔드에는 stale·dead 코드가 있다: `lib/constants.ts`·`StageBar`·`page.tsx`가 여전히 **12-stage 모델**을 사용(21-stage 세션의 진행바가 12에서 캡됨), `useKanban`이 세션 상세 페이지에서 **2번** 마운트되어 WS 2중 연결, `MonitoringPane`/`FileTreePane`/`recharts`/`@tanstack/react-virtual`가 dead/미사용 의존성. 상세는 개선 보고서 참고.

### Village — Star-Office-UI iframe + same-origin 리버스 프록시

`commit 00d2071 fix(village)`로 도입. 문제는 SSR iframe이 `village.excusa.uk`(Cloudflare Access, `X-Frame-Options: DENY`)를 가리켜 로드 거부되고, LAN에서는 포트 19000이 `ufw`로 막혔던 것. 해결: 프론트는 SSR 시 iframe을 렌더하지 않고(`origin=""`), 마운트 후 `/api/village-iframe/`(프록시 경로)로 설정한다. 백엔드 `village_proxy.py`가 `localhost:19000`으로 포워딩하며 Star-Office 절대 경로를 `/api/village-iframe` 접두로 재작성하고 `X-Frame-Options`/CSP를 제거해 임베딩을 가능케 한다. 결과적으로 브라우저는 포트 19000에 직접 닿지 않고 모든 트래픽이 same-origin으로 대시보드 호스트를 경유한다.

---

## 8. `agent-working-group` (AWG) — 독립적 벤더링 프로젝트

AWG는 Dev-Booth 트리 안에 있지만 **런타임에 사용되지 않는** 독립·별도 버전 프로젝트다.

- **무엇인가:** 소규모 에이전트 팀을 위한 **파일 기반 메시지 큐 라이브러리**(서버·DB·데몬 없음). `MessageQueue`(`inbox/processing/processed/dead` 4상태 디렉터리, fcntl flock atomic 전달), 우선순위(`blocker`99 > `question`70 > `answer`60 > `instruction`50 > `status`30 > `note`10), `awg` CLI, 훅/타임아웃/path-safety 모듈. 자체 `pyproject.toml`(MIT, stdlib-only), 자체 대시보드, ~134개 테스트, ~30개 docs를 갖는다.
- **Dev-Booth와의 관계 = 의존 아님.** `core/`·`dashboard/`·`run.sh` 어디에도 `agent_working_group` 임포트나 `awg` 호출이 없다(grep 0건). Dev-Booth의 실제 협업 계층은 **Hermes Kanban(SQLite)**이다. 유일한 연결은 대시보드가 AWG의 **큐 형태 패턴을 복사**(import 아님)한 것뿐이다 — `awg_inspector.py`(파일 카운팅)와 `models.py`(LogEntry 스키마 미러링).
- **추적 상태:** `.gitignore`에 `agent-working-group/`이 (중복으로) 등재되어 추적되지 않으며, **자체 `.git` 저장소**다(서브모듈/서브트리 아님 — `.gitmodules` 없음). Dev-Booth를 clone해도 AWG는 따라오지 않는다(버전 핀 없음).

---

## 9. 진화 이력 — v0 → v1 → v2

| 세대 | 위치 | 협업 방식 | 에이전트 |
|---|---|---|---|
| v0 (프로토타입) | `archive/bots/` | Discord 채널 + in-memory dict | Discord 봇(hermes-a/b, openclaw) |
| v1 (stateless orchestrator) | `archive/v1-stateless-orchestrator/` | **AWG 파일 큐** + in-process 12-stage 상태 머신. 매 턴이 stateless `hermes -z` 서브프로세스 | openclaw/hermes-a/hermes-b |
| **v2 (현재)** | `core/` | **Hermes Kanban(SQLite)** + 상주 gateway 디스패처. `session.py`는 보드만 시드 | conductor/architect/executor |

v1은 오케스트레이터가 in-process로 에이전트 턴을 구동했지만, v2는 협업을 SQLite 보드로 옮기고 에이전트 스폰을 별도 gateway에 위임했다. `archive/v1-stateless-orchestrator/tests/`의 13개 테스트는 더 이상 존재하지 않는 `core.orchestrator` 등을 import하므로 **dead**다(저장소 루트에서 `pytest`를 그냥 돌리면 18개 collection error 발생 — §10).

---

## 10. 테스트

- **라이브 v2 스위트:** `env/bin/python -m pytest tests/ -q` → **144 passed**. 구성:
  - `test_scenario.py`(12) — 21-stage DAG 정합성(스테이지 1..21, 비순환, 부모가 더 이른 스테이지, ≥1 리뷰 게이트, 시작/끝 conductor, 2개 TASK 레인).
  - `test_scenario_bodies.py`(115) — 스테이지별 body 골격(파일 읽기 규칙·`kanban_complete`·≤2000자·게이트/구현 스테이지의 `kanban_block` 경로·스킬 등록).
  - `test_session.py`(7) — 보드 setup + 21개 태스크 시드(CLI mocked, idempotency-key·`--parent`·`stage_task_map.json`).
  - `test_watchdog.py`(10) — protocol-violation 리퍼(sqlite/subprocess mocked).
- **대시보드 백엔드 테스트:** `dashboard/backend/tests/`에 별도 ~98개(kanban_reader·village·stage_mapper·path_guard·log_tailer·sessions_start·unblock 등).
- **e2e 셸(파이테스트 외):** `tests/e2e/{e2e_dryrun,e2e_live,verify_dashboard}.sh`. ⚠ `e2e_dryrun.sh`는 **보드 태스크가 정확히 12개**라고 하드 어서트하므로 21-stage 시드에서 깨진다(개선 보고서).
- **공백:** gateway가 태스크를 claim → 워커 스폰하는 **에이전트 런타임**을 검증하는 자동 테스트가 없다(긴 수동 e2e만 존재). 저장소 루트에서 `pytest`를 그냥 실행하면 archive/AWG 테스트까지 쓸어 담아 collection error가 난다 — `pytest tests/`로 스코프해야 한다.

---

## 11. 운영 (Operations)

| 구성요소 | 값 |
|---|---|
| LLM 추론 | vLLM @ `localhost:8003` — systemd 유닛 `vllm-qwen25-coder-32b.service` (문서상 Qwen2.5-Coder-32B). 단, 추적되는 권위 config(`config.yaml`)가 없고 `config/.env` 주석은 별도의 `:8000` 인스턴스를 설명하는 맥락에서 `Qwen3-Coder-Next` 이름을 언급한다 → 라이브 모델 식별자 정합성은 개선 보고서 참조 |
| 하드웨어 | NVIDIA A40 × 2 (각 ~46GB), Ubuntu 24.04 (호스트 data05lx) |
| 게이트웨이 | `config/hermes-gateway.service` — `hermes gateway run`, `After/Wants=vllm-qwen25-coder-32b.service` |
| 대시보드 | `dashboard/ops/dev-booth-dashboard.service` — uvicorn `:7000`, `DASHBOARD_STATIC_DIR=…/frontend/out` |
| 공개 | Cloudflare Tunnel(`cloudflared-ingress.yml`) → `dashboard.excusa.uk` (→ `127.0.0.1:7000`), Cloudflare Access 정책 |
| 봇 / 권한 | git/gh는 모두 **CrownClownCrowd**; 최종 머지는 운영자 |

운영자 진입점은 `./run.sh {start|stop|status|board|watch|logs|list|gateway}`. 상세 명령은 `docs/MANUAL.md`, 5분 시작은 `docs/QUICKSTART.md` 참고(단, 두 문서의 12-stage·dryrun 기술은 개선 보고서 기준으로 갱신 필요).

---

## 12. 알려진 불일치 (요약)

본 문서 작성 시점에 확인된 주요 불일치 — 전체 목록·증거·권고는 **[개선 보고서](../reports/results/)** 참조:

1. **(critical)** `run.sh`/systemd는 dryrun 기본 + 토큰 스크럽인데 시나리오는 always-live → 기본 호출이 인증 실패로 깨짐 (§5).
2. **(critical/doc)** README·ARCHITECTURE·QUICKSTART·MANUAL이 12-stage / dryrun-기본을 기술 — 코드는 21-stage / always-live.
3. **(high)** `core/dryrun/` dead code, `HERMES_BIN` 등 하드코딩 절대경로(`/home/mooner92`, `/dev-booth`), `DEV_BOOTH_PATH` 의미 충돌(repo root vs sessions root).
4. **(medium)** Village 기능이 핵심 문서에 미기재, 프론트 12-stage stale·dead 코드, `village_proxy` httpx 클라이언트 미정리, `/api/sessions/start` 무인증 + 전체 env 전달.
5. **(medium)** AWG 벤더링-but-untracked(버전 핀 없음), 대시보드의 copy-paste 결합.

---

*이 문서는 `core/scenario.py`·`core/session.py`·`core/watchdog.py`·`core/souls/*`·`dashboard/backend/*`·`dashboard/frontend/*`·`run.sh`·`tests/*`·`config/*`의 실제 소스를 직접 검토하여 작성되었다.*
