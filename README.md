# Dev-Booth 🤖

> 완전 로컬 자율 소프트웨어 개발 시스템 / Fully-local autonomous software development system

---

## Abstract

### 한국어

Dev-Booth는 세 개의 LLM 에이전트(conductor, architect, executor)가 Hermes Kanban(SQLite 기반 태스크 보드)을 통해 협력하며, 완전히 로컬에서 구동되는 자율 소프트웨어 개발 시스템이다. 에이전트들은 로컬 vLLM 서버에서 서빙되는 Qwen2.5-Coder-32B 모델을 사용하며, fork → 분석 → 구현 → 리뷰 → PR 제출로 이어지는 12단계 시나리오를 자율적으로 실행한다. 모든 진행 상황은 FastAPI + Next.js 14로 구축된 실시간 대시보드(dashboard.excusa.uk)에서 모니터링된다. 실제 코드 변경은 봇 계정 CrownClownCrowd를 통해 PR로 제출되고, 최종 머지 권한은 운영자(mooner92)가 보유한다. 기본 모드는 dryrun으로, `GITHUB_TOKEN`이 환경에서 제거되어 실수에 의한 push/PR을 원천 차단한다.

### English

Dev-Booth is a fully-local autonomous software development system in which three LLM agents — conductor, architect, and executor — coordinate through a Hermes Kanban board (SQLite-backed task queue). All inference is served locally by a vLLM instance running Qwen2.5-Coder-32B. The agents execute a deterministic 12-stage scenario: fork & clone → code analysis → dependency analysis → planning → implementation → code review → commit → PR. Progress is visible in real time on a FastAPI + Next.js 14 dashboard at dashboard.excusa.uk. Code changes are submitted as pull requests from the bot account CrownClownCrowd; final merge authority belongs to the human operator (mooner92). The default mode is dryrun — `GITHUB_TOKEN` is scrubbed from the gateway environment, making accidental pushes or PR creation mechanically impossible.

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│  mooner92 (최종 머지 권한)                                    │
│       ▲                                                       │
│       │  Pull Request (GitHub)                                │
│       │                                                       │
│  CrownClownCrowd (봇 계정)                                   │
│       ▲                                                       │
│       │  gh pr create                                         │
│       │                                                       │
│  ┌────┴────────────────────────────────────────────────────┐  │
│  │  Dev-Booth (자율 개발 시스템)                            │  │
│  │                                                          │  │
│  │  ┌─────────────────────────────────────────────────┐    │  │
│  │  │  Hermes Gateway (dispatcher)                    │    │  │
│  │  │  태스크 자동 claim → 에이전트 프로파일 spawn     │    │  │
│  │  └──────────┬──────────────────────────────────────┘    │  │
│  │             │  통신: Hermes Kanban (SQLite 태스크 보드)   │  │
│  │    ┌────────┼────────────────┐                           │  │
│  │    ▼        ▼                ▼                           │  │
│  │  ┌──────┐ ┌──────────┐ ┌──────────┐                     │  │
│  │  │Cond- │ │Architect │ │Executor  │                     │  │
│  │  │uctor │ │          │ │          │                     │  │
│  │  │지휘자│ │분석·설계 │ │구현·커밋 │                     │  │
│  │  │태스크│ │코드 리뷰 │ │테스트    │                     │  │
│  │  │분배  │ │아키텍처  │ │          │                     │  │
│  │  │PR승인│ │          │ │          │                     │  │
│  │  └──────┘ └──────────┘ └──────────┘                     │  │
│  │             │                                            │  │
│  │  모델: Qwen2.5-Coder-32B (vLLM, 완전 로컬, :8003)       │  │
│  └─────────────┼────────────────────────────────────────────┘  │
│                │                                               │
│  모니터링: dashboard.excusa.uk (FastAPI + Next.js 14)         │
│            Cloudflare Tunnel → :7000                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 12단계 개발 시나리오

`core/scenario.py`의 `STAGE_DAG`에 정의된 정적 DAG. 의존성 엣지가 충족되면 Hermes Kanban dispatcher가 다음 단계를 자동으로 `todo → ready`로 승격한다.

| # | 단계 | 담당 에이전트 | 설명 |
|---|------|--------------|------|
| 1 | **fork & clone** | conductor | 레포지토리를 fork하고 clone; dryrun pre-push 훅 설치 |
| 2 | **initial project scan** | conductor | 프로젝트 초기 스캔; architect·executor에게 분석 태스크 생성 |
| 3 | **code structure analysis** | architect | 디렉터리 구조, 핵심 클래스/함수, 코드 품질 이슈 분석 |
| 4 | **dependency & tech stack analysis** | executor | 패키지 의존성, 보안 취약점, 테스트 커버리지, CI/CD 분석 |
| 5 | **analysis summary** | conductor | architect·executor 분석 결과 취합 → `summary_v1.0.0.md` 작성 |
| 6 | **improvements plan** | conductor | 개선방안 목록 작성 → `improvements_v0.0.1.md` (TASK 단위) |
| 7 | **create feature branch** | conductor | `feature/devbooth-{session}-improvements` 브랜치 생성 |
| 8 | **implement TASK** | executor | 개선 태스크 구현; 자동 테스트 실행; 실패 시 최대 3회 재시도 |
| 9 | **code review** | architect | 구현 리뷰 (스타일·커버리지·성능·보안); LGTM 또는 block |
| 10 | **commit approved changes** | conductor | 리뷰 통과 변경사항 커밋 (`feat: ... [devbooth/{session}]`) |
| 11 | **draft PR** | conductor | PR 본문 작성; dryrun 시 `pr_draft.json` 저장 |
| 12 | **submit PR** | conductor | `gh pr create --repo mooner92/{repo}`; dryrun 시 `DRYRUN://no-pr` |

> **참고:** 단계 3·4는 단계 2에 병렬 의존하며, 단계 5는 3·4 모두 완료 후 시작된다.  
> 단계 9(code review)는 리뷰 게이트로, `blocked` 상태가 설계상 유효한 종료 상태이다.

---

## 빠른 시작

```bash
# 1. Hermes Gateway 시작 (최초 1회 또는 재부팅 후)
./run.sh gateway start

# 2. 새 세션 시작 — dryrun 기본값 (실제 push/PR 없음)
./run.sh start <세션명> <레포URL> "목표 설명"

# 예시
./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정 및 코드 품질 개선"

# 3. Kanban 보드 실시간 관찰
./run.sh watch <세션명>

# 4. 세션 보드 상태 확인
./run.sh board <세션명>

# 5. 대시보드 (브라우저)
# https://dashboard.excusa.uk

# ─── live 모드 (실제 PR 제출 — 확인 프롬프트 있음) ───
./run.sh start <세션명> <레포URL> "목표" live
```

> **dryrun (기본값):** `GITHUB_TOKEN`/`GH_TOKEN`이 게이트웨이 환경에서 제거됨.  
> `git push`는 `--dry-run`으로 리다이렉트, `gh pr create`는 차단됨.  
> live 모드 진입 시 `yes` 입력으로 명시적 확인이 필요하다.

---

## 기술 스택

| 구성요소 | 상세 |
|----------|------|
| LLM | Qwen2.5-Coder-32B-Instruct |
| 추론 엔진 | vLLM (로컬, `:8003`) |
| 에이전트 | Hermes Agent v0.13.0 |
| 조율 | Hermes Kanban (SQLite 기반 태스크 보드) |
| 대시보드 | FastAPI + Next.js 14 (App Router, `output: "export"`) |
| 인프라 | Ubuntu 24.04 / NVIDIA A40 × 2 |
| 터널 | Cloudflare Tunnel → `dashboard.excusa.uk` |

---

## 디렉터리 구조

```
/dev-booth/
├── run.sh                          # 운영자 진입점 (start/stop/watch/gateway 등)
├── core/
│   ├── scenario.py                 # 12단계 DAG 정의 (STAGE_DAG, STAGE_NARRATION)
│   ├── session.py                  # Kanban 보드 seed — DevBoothSession
│   ├── dryrun/                     # dryrun 보호 레이어
│   │   ├── git                     # git push → --dry-run 래퍼
│   │   ├── gh                      # gh pr create → DRYRUN://no-pr 래퍼
│   │   ├── pre-push                # pre-push 훅 (DEV_BOOTH_DRYRUN=1 시 차단)
│   │   └── install_hooks.sh        # clone 후 훅 설치 스크립트
│   └── souls/                      # 에이전트 SOUL.md 원본
│       ├── conductor.SOUL.md
│       ├── architect.SOUL.md
│       └── executor.SOUL.md
├── dashboard/
│   ├── backend/                    # FastAPI (Python) — :7000
│   │   ├── main.py
│   │   ├── routers/                # sessions, logs, metrics, ws, kanban
│   │   ├── services/               # stage_mapper, log_tailer, kanban_reader 등
│   │   └── tests/
│   └── frontend/                   # Next.js 14 — 정적 export → FastAPI 서빙
│       ├── app/
│       ├── components/
│       ├── hooks/
│       └── out/                    # 빌드 산출물
├── sessions/                       # 실행 중 세션 데이터 (status.json, log/, etc.)
├── tests/                          # orchestrator / scenario / session 단위 테스트
├── reports/
│   ├── plans/                      # 설계 계획서
│   └── results/                    # 구현 결과 보고서
├── docs/                           # 운영 문서 (예정)
├── archive/                        # 구버전 코드 (v1-stateless-orchestrator 등)
└── config/                         # .env (gitignored)
```

---

## 스크린샷

라이브 대시보드: **https://dashboard.excusa.uk**

- 세션 목록, 현재 단계, Kanban 보드 상태를 실시간으로 확인할 수 있다.
- 각 에이전트의 메시지 스트림, 파일 트리, 큐 깊이 카드를 포함한다.
- WebSocket 기반 실시간 업데이트 (로컬 p95 지연 185.9 ms).

---

## 문서

- [운영 매뉴얼](docs/MANUAL.md)
- [아키텍처 문서](docs/ARCHITECTURE.md)
- [빠른 시작 가이드](docs/QUICKSTART.md)

---

## 라이선스

내부 프로젝트 / Internal project — 외부 배포 라이선스 미적용.
