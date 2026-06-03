# Dev-Booth 🤖

> 완전 로컬 자율 소프트웨어 개발 시스템 / Fully-local autonomous software development system

---

## Abstract

### 한국어

Dev-Booth는 세 개의 LLM 에이전트(conductor, architect, executor)가 Hermes Kanban(SQLite 기반 태스크 보드)을 통해 협력하며, 완전히 로컬에서 구동되는 자율 소프트웨어 개발 시스템이다. 에이전트들은 서로 직접 대화하지 않고 **오직 보드를 통해서만** 협업한다. 추론은 모두 로컬 vLLM(`localhost:8003`, Qwen2.5-Coder-32B 계열)에서 서빙된다. 에이전트들은 fork → 분석 → 계획 → 구현/테스트/리뷰(2 레인) → 커밋 → PR로 이어지는 **21단계 v6 마이크로 태스크 DAG**(`core/scenario.py`)를 자율 실행한다. 진행 상황은 FastAPI + Next.js 14 대시보드(`dashboard.excusa.uk`, Cloudflare Tunnel)에서 실시간으로 모니터링된다. 대시보드는 **기본적으로 읽기 전용**이며 상태를 바꾸는 동작은 두 가지뿐이다 — 새 세션 시작(`POST /api/sessions/start`)과 태스크 unblock. 실제 코드 변경은 봇 계정 **CrownClownCrowd**가 PR로 제출하고, 최종 머지 권한은 운영자(mooner92)가 보유한다.

> ⚠️ **실행 모드 전환 중:** 이 시스템은 dryrun 기본 → **always-live**로 전환하는 중이다. 현재 에이전트 시나리오(`core/scenario.py`)와 conductor 인격은 dryrun 로직을 모두 제거했지만, `run.sh`와 systemd 유닛은 **아직 dryrun을 기본값으로** 두고 `GITHUB_TOKEN`을 스크럽한다. 따라서 인자 없는 기본 호출은 깨질 수 있다 — 실제 실행 시 반드시 `live` 인자를 사용하고, 마이그레이션 완료 전까지는 [개선 보고서](reports/results/)의 권고를 따를 것.

### English

Dev-Booth is a fully-local autonomous software-development system in which three LLM agents — conductor, architect, and executor — coordinate **only through a Hermes Kanban board** (a SQLite-backed task queue); they never message each other directly. All inference is served locally by a vLLM instance (`localhost:8003`, Qwen2.5-Coder-32B family). The agents autonomously execute a **21-stage v6 micro-task DAG** (`core/scenario.py`): fork → analysis → planning → two implement/test/review lanes → commit → pull request. Progress is visible in real time on a FastAPI + Next.js 14 dashboard at `dashboard.excusa.uk` (Cloudflare Tunnel). The dashboard is **read-only** apart from two write actions — starting a new session (`POST /api/sessions/start`) and unblocking a task. Code changes are submitted as pull requests from the bot account **CrownClownCrowd**; final merge authority belongs to the human operator (mooner92).

> ⚠️ **Execution mode in transition:** the system is migrating from a dryrun-default to an **always-live** model. The agent scenario (`core/scenario.py`) and the conductor persona have dropped all dryrun logic, but `run.sh` and the systemd unit still **default to dryrun** and scrub `GITHUB_TOKEN`, so the bare default invocation can fail. Pass the `live` argument for real runs and follow the [improvements report](reports/results/) until the migration is finished.

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│  mooner92 (최종 머지 권한)                                    │
│       ▲  Pull Request (GitHub)                                │
│  CrownClownCrowd (봇 계정)                                   │
│       ▲  gh pr create                                         │
│  ┌────┴────────────────────────────────────────────────────┐  │
│  │  Dev-Booth (자율 개발 시스템)                            │  │
│  │  ┌─────────────────────────────────────────────────┐    │  │
│  │  │  hermes gateway (dispatcher, 상주)              │    │  │
│  │  │  ready 태스크 claim → assignee 프로파일 spawn    │    │  │
│  │  └──────────┬──────────────────────────────────────┘    │  │
│  │   통신: Hermes Kanban (SQLite named board)              │  │
│  │    ┌────────┼────────────────┐                          │  │
│  │    ▼        ▼                ▼                          │  │
│  │  ┌──────┐ ┌──────────┐ ┌──────────┐                    │  │
│  │  │Cond- │ │Architect │ │Executor  │  ← SOUL + MEMORY    │  │
│  │  │uctor │ │분석·리뷰 │ │구현·테스트│                    │  │
│  │  │지휘·PR│ │          │ │로컬 커밋 │                    │  │
│  │  └──────┘ └──────────┘ └──────────┘                    │  │
│  │  모델: vLLM Qwen2.5-Coder-32B (완전 로컬, :8003)        │  │
│  └─────────────┼────────────────────────────────────────────┘  │
│  모니터링(읽기 위주): dashboard.excusa.uk (FastAPI + Next.js 14)│
│            Cloudflare Tunnel → :7000                          │
└──────────────────────────────────────────────────────────────┘
```

> `run.sh`와 `core/session.py`는 **에이전트를 직접 스폰하지 않는다.** 보드 시드만 담당하고, 에이전트 스폰은 오직 `hermes gateway` 디스패처가 한다.

---

## 21단계 개발 시나리오

`core/scenario.py`의 `STAGE_DAG`에 정의된 정적 마이크로 태스크 DAG(v6). 모든 스테이지는 5턴·~28K 컨텍스트 예산에 맞춰져 있다. 부모 태스크가 모두 `done`이면 디스패처가 자식을 `todo → ready`로 자동 승격한다.

| # | 담당 | 부모 | 단계 |
|---|------|------|------|
| 1 | conductor | — | fork & clone (→ `develop` 브랜치) |
| 2 | conductor | 1 | 디렉터리 구조 파악 |
| 3 | conductor | 2 | README + 패키지 파일 분석 |
| 4 | architect | 3 | 진입점 파일 분석 |
| 5 | architect | 4 | 컴포넌트/모듈 분석 1/2 |
| 6 | architect | 5 | 컴포넌트/모듈 분석 2/2 |
| 7 | architect | 3 | API/라우터 분석 |
| 8 | executor | 3 | 설정/환경 분석 |
| 9 | executor | 3 | 의존성/취약점 분석 |
| 10 | conductor | 6,7,8,9 | 분석 결과 취합 (fan-in) → `summary_v1.0.0.md` |
| 11 | conductor | 10 | 개선방안 TASK 목록 → `improvements_v0.0.1.md` |
| 12 | conductor | 11 | feature 브랜치 생성 |
| 13–15 | executor / executor / **architect** | 체인 | **TASK-1** 구현 → 테스트 → 리뷰(게이트) |
| 16–18 | executor / executor / **architect** | 체인 | **TASK-2** 구현 → 테스트 → 리뷰(게이트) |
| 19 | conductor | 18 | 변경사항 커밋 + push |
| 20 | conductor | 19 | PR 초안 작성 (`pr_draft.json`) |
| 21 | conductor | 20 | PR 제출 (`gh pr create --repo {repo_owner}/{repo}`) |

> stage 3에서 한 번 fan-out(4·7·8·9), stage 10에서 한 번 fan-in. 리뷰 게이트는 stage **15·18** 두 곳이며, 리뷰 미통과 시 `kanban_block("review-required: …")`가 정당한 종료 상태다. PR 대상 upstream owner는 매 세션 `repo_url`에서 추출되는 `{repo_owner}`이다(하드코딩된 단일 소유자가 아님).

---

## 빠른 시작

```bash
# 1. Hermes Gateway 시작 (최초 1회 또는 재부팅 후)
./run.sh gateway start

# 2. 새 세션 시작 — 보드에 21단계 태스크 seed
#    실제 fork/push/PR 이 필요하면 'live' 인자를 붙인다 (위 ⚠️ 참고)
./run.sh start <세션명> <레포URL> "목표 설명" live

# 예시
./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정 및 코드 품질 개선" live

# 3. Kanban 보드 실시간 관찰
./run.sh watch <세션명>      # 이벤트 스트림
./run.sh board <세션명>      # 태스크 목록 스냅샷
./run.sh status <세션명>     # sessions/<세션명>/status.json

# 4. 대시보드 (브라우저, 읽기 전용)
#    https://dashboard.excusa.uk
```

> `live` 인자를 붙이면 `run.sh`가 실행 전 `yes` 확인 입력을 요구한다(대화형). 인자 없이 호출하면 dryrun 기본값으로 토큰이 스크럽되어 always-live 시나리오가 인증 실패할 수 있다(위 ⚠️ 참고).
>
> 전체 명령 레퍼런스는 [`docs/MANUAL.md`](docs/MANUAL.md), 5분 시작은 [`docs/QUICKSTART.md`](docs/QUICKSTART.md). 두 문서의 일부 기술(12단계·dryrun 기본)은 갱신 대상이다 — [개선 보고서](reports/results/) 참고.

---

## 기술 스택

| 구성요소 | 상세 |
|----------|------|
| LLM | Qwen2.5-Coder-32B (vLLM, systemd 유닛 `vllm-qwen25-coder-32b`) |
| 추론 엔진 | vLLM (로컬, `:8003`) |
| 에이전트 조율 | Hermes Kanban (SQLite named board) + 상주 `hermes gateway` 디스패처 |
| 대시보드 | FastAPI(`:7000`) + Next.js 14 (App Router, `output: "export"`) |
| 인프라 | Ubuntu 24.04 / NVIDIA A40 × 2 |
| 터널 | Cloudflare Tunnel → `dashboard.excusa.uk` |
| 봇 / 권한 | git·gh = CrownClownCrowd; 최종 머지 = 운영자 |

---

## 디렉터리 구조

```
/dev-booth/
├── run.sh                       # 운영자 진입점 (start/stop/watch/board/gateway 등)
├── core/
│   ├── scenario.py              # 21단계 v6 DAG (STAGE_DAG, STAGE_NARRATION)
│   ├── session.py               # DevBoothSession — 보드 생성 + DAG seed (에이전트 미실행)
│   ├── watchdog.py              # protocol_violation 리퍼 (stuck 태스크 → block)
│   ├── souls/                   # 에이전트 인격: conductor/architect/executor.SOUL.md
│   ├── memories/                # 에이전트 지속 메모리: *.MEMORY.md
│   └── dryrun/                  # git/gh/pre-push 래퍼 — ⚠ 시나리오에서 더 이상 호출 안 됨(단 run.sh가 PATH에 주입)
├── dashboard/
│   ├── backend/                 # FastAPI :7000 — routers(health/sessions/github/metrics/ws/
│   │                            #   kanban/village/village_proxy) · services · tests
│   └── frontend/                # Next.js 14 정적 export — app(/, /session/[name], /village)
├── tests/                       # v2 라이브 테스트 (144) + e2e/ 셸 스크립트
├── reports/{plans,results}/     # 설계 계획서 / 구현·분석 결과 보고서
├── docs/                        # TECHNICAL_OVERVIEW · ARCHITECTURE · MANUAL · QUICKSTART
├── archive/                     # 구버전: v1-stateless-orchestrator + bots (dead)
├── config/                      # hermes-gateway.service (추적) + .env (gitignored)
├── sessions/                    # 런타임 세션 산출물 (gitignored)
└── agent-working-group/         # 벤더링된 별도 프로젝트 (gitignored — 런타임 미사용)
```

---

## Village 뷰

대시보드의 `/village` 페이지는 보드 상태를 픽셀 오피스 형태(Star-Office-UI)로 시각화한다. SSR 시 iframe을 렌더하지 않고, 마운트 후 백엔드의 same-origin 리버스 프록시(`/api/village-iframe/` → `localhost:19000`)를 통해 임베드한다. 덕분에 브라우저는 내부 포트에 직접 닿지 않고 모든 트래픽이 대시보드 호스트를 경유한다. 운영자 셋업은 [`docs/village_operator_setup.md`](docs/village_operator_setup.md) 참고.

---

## 문서

- [📘 기술 개요 (Technical Overview)](docs/TECHNICAL_OVERVIEW.md) — 전 하위 시스템을 코드와 대조해 정리한 종합 기술 문서
- [아키텍처 문서](docs/ARCHITECTURE.md) — v2 재플랫폼 (일부 12단계/dryrun 기술은 갱신 대상)
- [운영 매뉴얼](docs/MANUAL.md)
- [빠른 시작 가이드](docs/QUICKSTART.md)
- [개선 보고서](reports/results/) — 코드 전수 검토에서 도출된 우선순위별 개선 항목

---

## 라이선스

내부 프로젝트 / Internal project — 외부 배포 라이선스 미적용.
