# Dev-Booth 운영자 매뉴얼

> **버전:** 2.0 (Hermes Kanban 재플랫폼 이후)
> **최종 수정:** 2026-05-15
> **대상 서버:** data05lx (Ubuntu 24.04) — NVIDIA A40 × 2 (각 46 GB)

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [사전 준비](#2-사전-준비)
3. [세션 시작](#3-세션-시작)
4. [진행 상황 모니터링](#4-진행-상황-모니터링)
5. [Kanban 명령어 모음](#5-kanban-명령어-모음)
6. [트러블슈팅](#6-트러블슈팅)
7. [에이전트 프로필 관리](#7-에이전트-프로필-관리)
8. [세션 데이터 경로](#8-세션-데이터-경로)
9. [dryrun vs live 모드](#9-dryrun-vs-live-모드)

---

## 1. 시스템 개요

### Dev-Booth란?

Dev-Booth는 자율 소프트웨어 개발 시스템이다. GitHub 레포지토리 URL과 목표 문자열을 입력하면, 에이전트 3개가 협력하여 코드 분석 → 개선 계획 수립 → 구현 → 테스트 → PR 제출까지의 전 과정을 자동으로 수행한다.

### Hermes Kanban이 어떻게 동작하는가

Dev-Booth v2의 협조 레이어는 **Hermes v0.13.0 네이티브 Kanban** 위에서 동작한다.

```
./run.sh start <세션명> <레포URL> "목표"
        │
        ▼
core/session.py ──── named Kanban board 생성 (SQLite, ~/.hermes/kanban/boards/<slug>/kanban.db)
        │            + 12단계 DAG를 태스크로 seed (--parent 의존성 링크 포함)
        │
        ▼
hermes gateway (dispatcher) ─── 항상 실행 중인 데몬
        │  보드를 폴링하여 ready 상태인 태스크를 자동으로 claim
        │  태스크의 assignee 프로필을 워커로 spawn
        │
        ├── conductor  워커 → 태스크 실행 → kanban_complete() 호출
        │               ↓ 완료 시 의존 하위 태스크가 todo → ready로 자동 승격
        ├── architect  워커 → 태스크 실행 → kanban_complete()
        └── executor   워커 → 태스크 실행 → kanban_complete()
```

핵심 설계 원칙:
- `run.sh start`는 에이전트를 직접 실행하지 않는다. 보드에 태스크를 심는(seed) 것만 한다.
- `hermes gateway` 디스패처가 태스크를 자율적으로 claim하고 프로필을 워커로 spawn한다.
- 부모 태스크가 완료되면 자식 태스크가 자동으로 `ready`로 승격된다 (의존성 엣지 기반).
- 에이전트 간 통신은 `kanban_comment()` / `kanban_create()` / `kanban_show()`를 통해 이루어진다.

### 에이전트 3개의 역할

| 에이전트 | Hermes 프로필 | 역할 |
|---|---|---|
| **conductor** | `conductor` | 오케스트레이터. fork/clone, 분석 태스크 분배, 취합, 계획 수립, 브랜치/커밋/PR 관리 (stage 1, 2, 5, 6, 7, 10, 11, 12) |
| **architect** | `architect` | 코드 구조 분석 및 코드 리뷰 (stage 3, 9) |
| **executor** | `executor` | 의존성 분석 및 실제 코드 구현 (stage 4, 8) |

> **주의:** 이 세 이름 이외의 명칭(이전 명칭 포함)은 사용하지 않는다. Kanban 보드의 `assignee` 필드에는 `conductor`, `architect`, `executor` 만 유효하다. 알 수 없는 assignee가 지정된 태스크는 dispatcher가 영구히 claim하지 않는다.

### 12단계 시나리오 요약

| 단계 | 태스크 | 담당 | 설명 |
|---|---|---|---|
| 1 | fork & clone | conductor | 레포 포킹 및 클론, dryrun 훅 설치 |
| 2 | initial project scan | conductor | 초기 스캔, 분석 태스크 분배 |
| 3 | code structure analysis | architect | 디렉터리 구조/모듈/품질 이슈 분석 |
| 4 | dependency & tech stack analysis | executor | 의존성/보안 취약점/CI 분석 |
| 5 | analysis summary | conductor | 분석 결과 취합, summary_v1.0.0.md 작성 |
| 6 | improvements plan | conductor | 개선방안 계획, improvements_v0.0.1.md 작성 |
| 7 | create feature branch | conductor | feature/devbooth-{세션}-improvements 브랜치 생성 |
| 8 | implement TASK-N | executor | 실제 코드 구현 + 자동 테스트 실행 |
| 9 | code review TASK-N | architect | 구현 리뷰 게이트 (blocked는 정상 종료 상태) |
| 10 | commit approved changes | conductor | 리뷰 통과 변경사항 커밋 |
| 11 | draft PR | conductor | PR 초안 작성 (dryrun 시 pr_draft.json 저장) |
| 12 | submit PR | conductor | PR 제출 (dryrun 시 url: "DRYRUN://no-pr" 기록) |

단계 3과 4는 단계 2에 동시 의존(병렬 실행). 단계 5는 3과 4 모두 완료 후 승격된다.

---

## 2. 사전 준비

세션을 시작하기 전에 아래 세 가지 서비스가 모두 정상 동작 중인지 확인한다.

### 2-1. vLLM (Qwen2.5-Coder-32B-Instruct, 포트 8003)

에이전트가 사용하는 LLM 백엔드이다. A40 GPU 2장에서 Qwen2.5-Coder-32B-Instruct를 서빙한다.

```bash
# 상태 확인
curl http://localhost:8003/health

# 정상 응답 예시: {"status":"ok"}

# 시작 (서비스가 내려가 있을 때)
sudo systemctl start vllm-qwen25-coder-32b

# 로그 확인
sudo journalctl -u vllm-qwen25-coder-32b -f
```

### 2-2. Hermes Gateway (디스패처 데몬)

보드를 폴링하여 ready 태스크를 claim하고 에이전트를 spawn하는 핵심 데몬이다.

```bash
# 상태 확인
hermes gateway status

# systemd로 시작 (부팅 지속, OT1 완료 후)
sudo systemctl start hermes-gateway

# 또는 run.sh 래퍼로 시작 (B1 foreground-detached 방식)
./run.sh gateway start

# 상태/로그
./run.sh gateway status
sudo journalctl -u hermes-gateway -f
```

> `./run.sh start`는 게이트웨이가 실행 중이 아닐 경우 자동으로 B1 방식으로 시작한다.

### 2-3. 대시보드 (포트 7000)

세션 카드, 에이전트 대화 스트리밍, Kanban 뷰를 제공하는 웹 UI이다.

```bash
# 상태 확인
curl http://localhost:7000/api/health

# 시작
sudo systemctl start dev-booth-dashboard

# 재시작
sudo systemctl restart dev-booth-dashboard

# 로그
sudo journalctl -u dev-booth-dashboard -f
```

외부 접속: https://dashboard.excusa.uk (Cloudflare Tunnel 경유, 포트 7000과 동일)

### 2-4. GPU 메모리 확인

```bash
nvidia-smi | grep MiB
```

두 GPU 모두 충분한 여유 메모리가 있어야 한다. 두 A40은 각 46 GB이며, vLLM이 32B 모델을 텐서 병렬로 양쪽 GPU에 걸쳐 서빙한다.

---

## 3. 세션 시작

### 기본 명령어

```bash
cd /dev-booth
./run.sh start <세션명> <레포URL> "목표" [dryrun|live]
```

| 인자 | 설명 | 기본값 |
|---|---|---|
| `<세션명>` | 세션 식별자 (보드 slug로 변환됨) | 필수 |
| `<레포URL>` | 대상 GitHub 레포 URL | 필수 |
| `"목표"` | 자연어 목표 설명 | `"코드 품질 개선 및 버그 수정"` |
| `dryrun\|live` | 실행 모드 | `dryrun` |

### 실제 예시

```bash
# dryrun 모드 (기본) — git push / PR이 실제로 실행되지 않음
./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정 및 성능 개선"

# live 모드 — 실제 PR이 생성됨 (확인 프롬프트 있음)
./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정" live
```

### 시작 시 내부 동작 순서

1. live 모드인 경우 확인 프롬프트 출력 (`yes` 입력 필요)
2. `hermes gateway`가 실행 중이 아니면 B1 방식으로 자동 시작
3. `core/session.py`가 named Kanban 보드를 생성 (이미 존재하면 스킵)
4. 12개 태스크를 `--parent` 의존성 링크와 함께 보드에 seed
5. stage 1이 `ready`, 나머지 2–12는 `todo` 상태로 시작
6. 디스패처가 stage 1을 자동 claim → conductor 워커 spawn

```
OK setup: session=demo board=demo dryrun=True
  stage  1 [conductor ] [firebase-chat-exp] fork & clone         -> task_abc123
  stage  2 [conductor ] [firebase-chat-exp] initial project scan -> task_def456
  ...
  stage 12 [conductor ] [firebase-chat-exp] submit PR            -> task_xyz999
OK seed: 12 tasks on board demo
  dashboard: http://localhost:7000/session/demo
  kanban:    hermes kanban --board demo watch
```

### dryrun이 차단하는 것

dryrun 모드(기본값)에서는 세 겹의 레이어가 실제 git push / PR 생성을 차단한다. 자세한 내용은 [9. dryrun vs live 모드](#9-dryrun-vs-live-모드) 참조.

---

## 4. 진행 상황 모니터링

### run.sh 서브커맨드

```bash
# Kanban 태스크 실시간 이벤트 스트림 (Ctrl+C로 종료)
./run.sh watch <세션명>

# 현재 보드 태스크 목록 (상태 스냅샷)
./run.sh board <세션명>

# status.json 출력 (세션 메타 정보)
./run.sh status <세션명>

# 에이전트 메시지 로그 실시간 tail
./run.sh logs <세션명>

# 보드 전체 목록 + 세션 디렉터리 목록
./run.sh list
```

### 대시보드 웹 UI

https://dashboard.excusa.uk 에 접속한 뒤:

- 세션 카드를 클릭하면 세션 상세 페이지로 이동한다.
- 페이지 내 Kanban 패널에서 12개 태스크의 현재 상태(todo / ready / running / done / blocked)를 확인할 수 있다.
- 각 태스크 카드를 클릭하면 해당 에이전트의 대화 내용을 실시간으로 스트리밍한다 (WebSocket `/api/kanban/ws/kanban/{slug}` 사용).

### 태스크 상태 의미

| 상태 | 의미 |
|---|---|
| `todo` | 아직 부모 태스크가 완료되지 않아 대기 중 |
| `ready` | 부모 태스크 완료, 디스패처가 claim 대기 중 |
| `running` | 에이전트 워커가 실행 중 |
| `done` | 에이전트가 `kanban_complete()` 호출 완료 |
| `blocked` | 에이전트가 `kanban_block()` 호출 (리뷰 필요 또는 오류) |

> stage 9(코드 리뷰 게이트)의 `blocked`는 정상적인 종료 상태이다. 리뷰어가 피드백을 확인한 뒤 `unblock`으로 재시도할 수 있다.

---

## 5. Kanban 명령어 모음

> **중요:** `--board <slug>` 플래그는 `hermes kanban` 레벨의 플래그이며, **반드시 서브커맨드 앞에** 위치해야 한다.
>
> 올바른 예: `hermes kanban --board demo list`
> 틀린 예: `hermes kanban list --board demo`

### 보드 관리 (slug를 positional로 전달, `--board` 불필요)

```bash
# 모든 보드 목록
hermes kanban boards list

# 보드 생성 (session.py가 자동 호출하므로 수동 필요 없음)
hermes kanban boards create <slug> --name "보드 이름" --description "설명"
```

### 보드 조회 및 모니터링

```bash
# 보드 통계 (태스크 수, 상태별 분포)
hermes kanban --board <slug> stats

# 태스크 목록 (상태별 표시)
hermes kanban --board <slug> list

# 실시간 이벤트 스트림 (Ctrl+C로 종료)
hermes kanban --board <slug> watch
```

### 태스크 상세 조회

```bash
# 태스크 상세 정보 (본문, 상태, 담당자 등)
hermes kanban --board <slug> show <task_id>

# 태스크의 실행 이력 (runs 목록, outcome, summary)
hermes kanban --board <slug> runs <task_id>

# blocked 태스크 해제 및 재시도 (재시도 횟수가 남아 있으면 자동 재시도)
hermes kanban --board <slug> unblock <task_id>

# 태스크의 컨텍스트 (부모/자식 관계, kanban_comment 이력)
hermes kanban --board <slug> context <task_id>
```

### 보드 진단

```bash
# 보드 전체 진단 (stuck 태스크, 의존성 루프 감지 등)
hermes kanban --board <slug> diag

# 현재 assignee 목록 (어떤 프로필이 태스크를 보유 중인지)
hermes kanban --board <slug> assignees
```

### 전체 예시 (세션명 `demo`)

```bash
hermes kanban boards list
hermes kanban --board demo stats
hermes kanban --board demo list
hermes kanban --board demo watch
hermes kanban --board demo show task_abc123
hermes kanban --board demo runs task_abc123
hermes kanban --board demo unblock task_abc123
hermes kanban --board demo context task_abc123
hermes kanban --board demo diag
hermes kanban --board demo assignees
```

---

## 6. 트러블슈팅

### 문제 1 — `protocol_violation`: 에이전트가 `kanban_complete` 없이 종료

**원인:** 에이전트 워커가 태스크를 완료하지 않고 비정상 종료했거나, `kanban_complete()`를 호출하지 않았다. 해당 태스크는 `blocked` 또는 `running` 상태로 멈춘다.

**확인:**
```bash
hermes kanban --board <slug> diag
hermes kanban --board <slug> runs <task_id>
```

**해결:**
```bash
# 태스크를 unblock하면 재시도 횟수가 남아 있는 경우 디스패처가 자동 재시도한다
hermes kanban --board <slug> unblock <task_id>
```

재시도 횟수가 소진된 경우 `hermes kanban --board <slug> show <task_id>`로 본문을 확인하고 원인을 파악한 뒤, 필요하면 태스크를 수동으로 재생성한다.

---

### 문제 2 — 대시보드 접속 불가

**원인:** `dev-booth-dashboard` systemd 서비스가 내려갔거나, uvicorn 프로세스가 종료되었다.

**확인:**
```bash
sudo systemctl status dev-booth-dashboard
curl http://localhost:7000/api/health
```

**해결:**
```bash
sudo systemctl restart dev-booth-dashboard
# 재시작 후 확인
curl http://localhost:7000/api/health
```

---

### 문제 3 — Gateway 미실행 (에이전트가 아무것도 하지 않음)

**원인:** `hermes gateway` 디스패처가 실행 중이지 않으면 ready 태스크를 claim하는 주체가 없으므로 보드가 움직이지 않는다.

**확인:**
```bash
hermes gateway status
```

**해결:**
```bash
# systemd 서비스로 재시작 (OT1 완료 후)
sudo systemctl restart hermes-gateway

# 또는 run.sh 래퍼 사용
./run.sh gateway start
```

---

### 문제 4 — vLLM 응답 없음

**원인:** vLLM 서비스가 크래시했거나, GPU 초기화에 실패했다. 에이전트가 LLM 호출에서 타임아웃된다.

**확인:**
```bash
curl http://localhost:8003/health
sudo systemctl status vllm-qwen25-coder-32b
```

**해결:**
```bash
sudo systemctl start vllm-qwen25-coder-32b
# GPU 메모리 해제까지 1–2분 대기 후 재확인
curl http://localhost:8003/health
```

---

### 문제 5 — GPU 메모리 부족 (vLLM OOM)

**원인:** 다른 프로세스가 GPU 메모리를 점유하고 있거나, 이전 vLLM 인스턴스가 정상 종료되지 않아 메모리가 남아 있다.

**확인:**
```bash
nvidia-smi | grep MiB
```

각 GPU의 사용 중(Used) MiB가 비정상적으로 높으면 OOM 위험이 있다.

**해결:**
```bash
# 불필요한 vLLM 서비스 중지
sudo systemctl stop vllm-qwen25-coder-32b

# 잔류 프로세스 확인 및 종료
nvidia-smi | grep MiB
# 메모리가 해제된 후 재시작
sudo systemctl start vllm-qwen25-coder-32b
```

---

## 7. 에이전트 프로필 관리

### 프로필 목록 확인

```bash
hermes profile list
```

Dev-Booth에서 사용하는 세 프로필: `conductor`, `architect`, `executor`

### SOUL.md 위치

| 경로 | 설명 |
|---|---|
| `~/.hermes/profiles/conductor/SOUL.md` | conductor 프로필 활성 SOUL (게이트웨이가 읽는 파일) |
| `~/.hermes/profiles/architect/SOUL.md` | architect 프로필 활성 SOUL |
| `~/.hermes/profiles/executor/SOUL.md` | executor 프로필 활성 SOUL |
| `/dev-booth/core/souls/conductor.SOUL.md` | 버전 관리 원본 |
| `/dev-booth/core/souls/architect.SOUL.md` | 버전 관리 원본 |
| `/dev-booth/core/souls/executor.SOUL.md` | 버전 관리 원본 |

SOUL.md를 수정할 때는 `/dev-booth/core/souls/` 아래의 원본을 편집한 뒤 `~/.hermes/profiles/` 로 복사하는 것을 권장한다.

```bash
cp /dev-booth/core/souls/conductor.SOUL.md ~/.hermes/profiles/conductor/SOUL.md
cp /dev-booth/core/souls/architect.SOUL.md ~/.hermes/profiles/architect/SOUL.md
cp /dev-booth/core/souls/executor.SOUL.md  ~/.hermes/profiles/executor/SOUL.md
```

**SOUL.md 수정 후 반드시 게이트웨이를 재시작해야 변경사항이 반영된다.**

```bash
sudo systemctl restart hermes-gateway
# 또는
./run.sh gateway stop
./run.sh gateway start
```

### 프로필 단독 테스트

프로필이 올바르게 동작하는지 게이트웨이 없이 단독 테스트할 수 있다.

```bash
HERMES_PROFILE=conductor hermes -z "안녕, 자기소개 해줘" --yolo
HERMES_PROFILE=architect hermes -z "이 코드를 리뷰해줘" --yolo
HERMES_PROFILE=executor  hermes -z "간단한 Python 함수 작성해줘" --yolo
```

---

## 8. 세션 데이터 경로

### 디렉터리 구조

```
/dev-booth/sessions/{세션명}/
├── status.json              # 세션 메타 정보 (보드 slug, dryrun 여부, 현재 단계 등)
├── stage_task_map.json      # 단계 번호 → Kanban task_id 매핑
├── log/
│   └── messages.jsonl       # 에이전트 메시지 로그 (run.sh logs로 tail)
├── analysis_architect.md    # architect의 코드 구조 분석 결과 (stage 3)
├── analysis_executor.md     # executor의 의존성 분석 결과 (stage 4)
├── summary_v1.0.0.md        # conductor의 분석 취합 요약 (stage 5)
├── improvements_v0.0.1.md   # 개선방안 계획서 (stage 6)
└── pr_draft.json            # dryrun 모드의 PR 초안 (stage 11)

/dev-booth/.worktrees/{task_id}/
└── ...                      # 각 태스크의 git worktree (에이전트 작업 공간)

~/.hermes/kanban/boards/{slug}/
└── kanban.db                # 보드의 SQLite DB (태스크, 실행 이력, 코멘트 등)
```

### 주요 파일 설명

**`status.json`** — `./run.sh status <세션명>`이 출력하는 파일이다. 세션 시작 시 seed 단계에서 기록되며, 보드 slug, dryrun 여부, 시작 시각이 포함된다.

**`stage_task_map.json`** — 단계 번호(1–12)와 Kanban task_id의 매핑이다. 특정 단계의 task_id를 조회할 때 사용한다.

**`kanban.db`** — 보드의 단일 진실 소스(single source of truth)이다. `hermes kanban` CLI는 이 DB를 읽고 쓴다. 직접 읽어야 할 때는 Python `sqlite3` 모듈을 사용한다 (시스템에 `sqlite3` CLI가 없을 수 있음).

```bash
python3 -c "
import sqlite3, json
conn = sqlite3.connect('/root/.hermes/kanban/boards/demo/kanban.db')
rows = conn.execute('SELECT id, title, status FROM tasks').fetchall()
for r in rows: print(r)
"
```

---

## 9. dryrun vs live 모드

### 비교표

| 항목 | dryrun (기본) | live |
|---|---|---|
| 활성화 방법 | 기본값 (4번째 인자 생략 또는 `dryrun`) | 4번째 인자에 `live` 입력 |
| 확인 프롬프트 | 없음 | `yes` 입력 필요 |
| `git push` | `--dry-run` 옵션으로 실행 (실제 push 없음) | 실제 push 실행 |
| `gh pr create` | `DRYRUN://no-pr` 로 대체 | 실제 PR 생성 |
| PR 초안 | `sessions/{세션명}/pr_draft.json` 에 저장 | GitHub에 실제 PR 생성됨 |
| `GITHUB_TOKEN` | 스크럽됨 (gateway 환경변수에서 제거) | 유지됨 |
| `DEV_BOOTH_DRYRUN` | `1` | `0` |

### dryrun 3중 레이어 (차단 메커니즘)

dryrun 모드는 세 겹의 독립적인 레이어로 실제 push/PR을 차단한다:

**Layer 1 — pre-push 훅 (per-clone, best-effort)**

stage 1 태스크에서 conductor가 레포를 clone한 직후 `install_hooks.sh`를 실행하여 해당 워킹 디렉터리에 `pre-push` 훅을 설치한다. 이 훅은 `DEV_BOOTH_DRYRUN=1` 환경에서 `git push`를 차단한다.

```bash
bash /dev-booth/core/dryrun/install_hooks.sh <clone_path>
```

**Layer 2 — git/gh PATH 래퍼 (defense-in-depth)**

`/dev-booth/core/dryrun/` 디렉터리가 게이트웨이 환경의 `PATH` 맨 앞에 추가된다. 이 디렉터리에는 `git`과 `gh` 래퍼 스크립트가 있어 실제 명령 대신 dryrun 동작을 수행한다:
- `gh pr create` → `DRYRUN://no-pr` 반환
- `git push` → `--dry-run` 플래그 추가

에이전트가 절대 경로로 `git`을 호출하면 우회될 수 있으므로 Layer 2만으로는 완전하지 않다.

**Layer 3 — GITHUB_TOKEN 스크럽 (mechanically enforced backstop)**

게이트웨이 시작 시 `env -u GITHUB_TOKEN -u GH_TOKEN`으로 인증 토큰을 환경에서 완전히 제거한다. 에이전트 워커는 토큰 자체가 없으므로 어떤 경로(gh, curl, API 직접 호출)로도 실제 push나 PR을 생성할 수 없다. 이 레이어는 per-repo 설치가 필요 없고 우회할 수 없다.

### live 모드 실행 절차

```bash
cd /dev-booth

# 1. live 모드로 세션 시작
./run.sh start <세션명> <레포URL> "목표" live

# 2. 확인 프롬프트에 yes 입력
# ⚠️  LIVE 모드: 실제 git push / gh pr create 가 실행됩니다.
# 계속하려면 'yes' 입력: yes

# 3. 진행 모니터링
./run.sh watch <세션명>
```

live 모드는 실제 GitHub PR을 생성하므로, 실행 전 대상 레포와 Bot 계정(`CrownClownCrowd`)의 권한을 확인한다.
