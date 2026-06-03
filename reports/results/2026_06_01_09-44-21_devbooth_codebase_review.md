# Dev-Booth 코드베이스 전수 검토 — 개선 보고서

> 작성일: 2026-06-01 · 브랜치: `feat/kanban-redesign-2026-05-14` · 추적 파일 176개
> 방법: `core/`·`dashboard/`(backend+frontend)·`agent-working-group/`·`archive/`·`tests/`·`docs/`·`run.sh`·`config/`를 7개 병렬 에이전트로 전수 매핑한 뒤, 모든 주장을 소스(file:line)·명령 출력과 대조해 독립 검증했다.
> 동반 산출물: [`docs/TECHNICAL_OVERVIEW.md`](../../docs/TECHNICAL_OVERVIEW.md)(기술 개요), 갱신된 [`README.md`](../../README.md).

## 요약 (우선순위별 카운트)

| 심각도 | 개수 | 핵심 |
|---|---|---|
| 🔴 Critical | 2 | always-live/dryrun 절반 마이그레이션으로 기본 실행 깨짐 · 전 문서 12단계/dryrun stale |
| 🟠 High | 6 | `core/dryrun/` dead code · 하드코딩 절대경로/인터프리터 · `DEV_BOOTH_PATH` 의미 충돌 · e2e 12-task 하드어서트 · **`core/config.py` 부재**(경로 산재 근본원인) · **평문 PAT in `.git/config`** · (H4 README PR owner ✅ 본 검토에서 해결) |
| 🟡 Medium | 7 | 무인증 세션 시작 + env 전달 · 침묵 실패(`_kanban_json`) · 레이어 역전 · 프론트 12-stage stale · 프론트 dead code · village_proxy 클라이언트 누수 · AWG 벤더링-untracked |
| 🟢 Low | 6 | 프론트 WS 2중 연결 · `.omc/` 미ignore · archive 사장 테스트 collection error · 모델 식별자 불일치 · stage_mapper "12 stages" 표현 stale · 기타 위생 |

가장 시급한 단일 작업: **C1(always-live 마이그레이션을 원자적으로 완료)**. 나머지 문서/위생 항목 다수가 이 결정에 종속된다.

---

## 🔴 Critical

### C1 — `run.sh`/systemd는 dryrun 기본 + 토큰 스크럽인데, 시나리오는 always-live → 기본 실행이 인증 실패로 깨짐

워킹 트리(미커밋)의 `core/scenario.py`·`core/session.py`·`core/souls/conductor.SOUL.md`는 dryrun 분기·`install_hooks.sh` 호출·`DRYRUN://no-pr`를 전부 제거했다(always-live). always-live 시나리오는 다음 단계에서 GitHub 토큰을 **요구**한다:

- `core/scenario.py:119` stage 1 `gh repo view … || gh repo fork {repo_url}`
- `core/scenario.py:120` stage 1 `gh repo clone CrownClownCrowd/{repo}`
- `core/scenario.py:425` stage 12 `git push -u origin feature/…`
- `core/scenario.py:613` stage 19 `git push origin feature/…`
- `core/scenario.py:665` stage 21 `gh pr create --repo {repo_owner}/{repo} …`

그러나 `run.sh`(커밋됨)는 여전히 dryrun을 기본값으로 두고 토큰을 제거한다:

- `run.sh:47` `local mode="${1:-dryrun}"` · `run.sh:66` `gateway_start "${2:-dryrun}"` · `run.sh:78` `local MODE="${4:-dryrun}"`
- `run.sh:56` `env -u GITHUB_TOKEN -u GH_TOKEN DEV_BOOTH_DRYRUN=1 PATH="$DRYRUN_BIN:$PATH" … hermes gateway run`
- `config/hermes-gateway.service:14-17`도 `DEV_BOOTH_DRYRUN=1` + `GITHUB_TOKEN=`/`GH_TOKEN=` 스크럽을 baked-in.

**구체적 breakage:** 인자 없는 `./run.sh start <s> <repo>`는 토큰이 제거된 게이트웨이를 띄운다. 게이트웨이가 스폰하는 에이전트는 토큰을 상속받지 못하지만, always-live 시나리오 body에는 dryrun 폴백이 남아 있지 않으므로 stage 1 fork/clone과 stage 12/19/21 push+PR이 인증 오류로 실패하고 실행이 도중에 죽는다. 게다가 `run.sh:56`은 여전히 `$DRYRUN_BIN`을 PATH 앞에 두어 이제는 dead인 `core/dryrun/gh`·`core/dryrun/git` 셰임이 실제 바이너리를 가린다.

> **권고:** 마이그레이션을 원자적으로 완료할 것. (a) `run.sh` 기본값을 `live`로 바꾸고 `$DRYRUN_BIN` PATH 주입 · 토큰 스크럽 · `core/dryrun/` · `hermes-gateway.service`의 dryrun env를 삭제하거나, (b) dryrun을 유지하려면 시나리오/SOUL에 dryrun 분기를 복원할 것. 미커밋 3개 파일을 **이에 대응하는 `run.sh`/서비스 변경과 함께** 커밋하라. 절반 상태로 두지 말 것.

### C2 — 모든 운영 문서가 12단계 / dryrun-기본을 기술 (코드는 21단계 / always-live)

전 문서가 가장 두드러진 아키텍처 주장에서 9단계 + 분해 구조 + 안전 모델이 어긋난다.

> **본 검토에서 `README.md`와 신규 `docs/TECHNICAL_OVERVIEW.md`는 21단계/always-live로 이미 갱신했다.** 아래 라인 인용은 **여전히 stale한** 문서만 가리킨다(README는 정정 완료).

- 스테이지 수: `docs/ARCHITECTURE.md:23,113,118-129` · `docs/MANUAL.md:38,67,69-82,509` · `docs/QUICKSTART.md:34`이 "12단계"를 명시(본 검토 전에는 README도 동일했음). 코드 `grep -c 'stage=' core/scenario.py` → **21**. 분해도 다름: 문서는 분석 3단계·단일 리뷰 게이트·단일 `implement TASK`이나, 코드는 분석 8 마이크로단계·**리뷰 게이트 2개(15·18)**·**TASK-1/TASK-2 2개 레인**.
- dryrun: `docs/ARCHITECTURE.md:226-260` · `docs/MANUAL.md:174,206-208,524-560` · `docs/QUICKSTART.md:33,69`이 "dryrun이 기본, GITHUB_TOKEN 스크럽으로 기계적으로 강제(mechanically impossible)"라고 단언. 그러나 시나리오는 always-live(C1) → "기계적으로 불가능"이 더 이상 보장되지 않는다(안전 관련 오류).

> **권고:** `docs/ARCHITECTURE.md`·`docs/MANUAL.md`·`docs/QUICKSTART.md`의 12단계 표·dryrun 절을 C1 결정에 맞춰 21단계/always-live로 재작성하라. `docs/TECHNICAL_OVERVIEW.md`가 정합 기준점이다.

---

## 🟠 High

### H1 — `core/dryrun/`는 더 이상 시나리오에서 호출되지 않는 dead code
`grep -rn install_hooks core/ run.sh` → `core/dryrun/` 내부 자기 참조뿐. 미커밋 scenario.py 편집이 stage-1의 `install_hooks.sh` 호출(Layer 1)을 삭제했고, `git`/`gh`/`pre-push` 셰임의 목적인 `DEV_BOOTH_DRYRUN` 게이팅도 시나리오/SOUL에서 제거됐다. 유일한 잔존 참조는 `run.sh:15`의 `DRYRUN_BIN`. **권고:** C1이 always-live로 결정되면 `core/dryrun/` 전체와 `DRYRUN_BIN` 라인을 삭제. (덤: `core/souls/executor.SOUL.md:66-67`와 `core/memories/executor.MEMORY.md:28-29` 두 곳에 stale한 "## Dryrun 규칙" 절이 커밋된 채 남아 있음 — 함께 정리.)

### H2 — 하드코딩 절대경로 다수, env 오버라이드 없음 → 비이식성
- `run.sh:12` `HERMES="/home/mooner92/.local/bin/hermes"`, `run.sh:13` `DEV_BOOTH_PATH="/dev-booth"`
- `core/session.py:25` `HERMES_BIN = "/home/mooner92/.local/bin/hermes"` (getenv 폴백 없음)
- `dashboard/backend/services/kanban_reader.py:18` 동일 하드코딩
- `dashboard/backend/routers/sessions.py:41` `/dev-booth/env/bin/python3`, `:43` `cwd="/dev-booth"`
- **인터프리터 경로 불일치:** 같은 `core.session` seed 진입점인데 `run.sh:91`은 `$VENV/bin/python3.11`, `dashboard/backend/routers/sessions.py:41`은 `/dev-booth/env/bin/python3`(`.11` 없음) — 한 진입점에 두 개의 서로 다른 하드코딩 인터프리터.
- SOUL/MEMORY/SKILL 템플릿에 `/dev-booth/sessions/…` 리터럴

특히 `HERMES_BIN`은 어디에도 env 오버라이드가 없어 `mooner92`가 아닌 사용자/CI는 소스 수정 없이 실행 불가. **권고:** `os.getenv("HERMES_BIN", shutil.which("hermes") or …)` 패턴, `DEV_BOOTH_PATH`·인터프리터 경로를 env로, 세션 경로 리터럴은 템플릿화.

### H3 — `DEV_BOOTH_PATH` 환경변수 의미 충돌 (repo root vs sessions root)
`run.sh:13`은 `DEV_BOOTH_PATH=/dev-booth`(repo root)로, `core/session.py:26`은 `SESSIONS_ROOT = Path(os.getenv("DEV_BOOTH_PATH", "/dev-booth/sessions"))`(sessions root)로 **같은 이름을 다른 의미**로 쓴다. 현재는 `run.sh`가 export하지 않아(`grep -n export run.sh` → 없음) 자식 파이썬이 unset으로 보고 기본값으로 떨어져 우연히 동작한다. 누군가 `DEV_BOOTH_PATH=/dev-booth`를 export하는 순간 모든 세션이 `/dev-booth/<name>`에 기록되어 대시보드(`DEVBOOTH_SESSIONS_ROOT`, `config.py:15`)와 어긋난다 — 세 이름·두 의미. **권고:** `session.py`의 변수를 대시보드와 동일한 `DEVBOOTH_SESSIONS_ROOT`로 통일하고 `DEV_BOOTH_PATH`는 repo root 전용으로.

### H4 — (✅ 본 검토에서 RESOLVED) README가 PR 대상 owner를 하드코딩 `mooner92`로 문서화했었음
본 검토 전 README 스테이지 표는 `gh pr create --repo mooner92/{repo}`를 명시했으나, 코드 `core/scenario.py:665`는 `--repo {repo_owner}/{repo} --base main --head CrownClownCrowd:…`로 upstream owner를 세션마다 `repo_url`에서 추출한다(`conductor.SOUL.md:68`, commit `3caba58`). 이 하드코딩은 **README에만** 있었고(grep 확인: `docs/ARCHITECTURE.md`·`docs/MANUAL.md`에는 `gh pr create --repo mooner92` 없음), **본 검토의 README 갱신에서 `{repo_owner}`로 정정 완료**. 잔존 작업 없음.

### H5 — `tests/e2e/e2e_dryrun.sh`가 보드 태스크 정확히 12개를 하드 어서트 → 21단계 시드에서 깨짐
`tests/e2e/e2e_dryrun.sh:53` `[ "$ntasks" -eq 12 ]`. `core.session.seed()`는 이제 21개 태스크를 만든다(`tests/test_session.py:61-88`가 `len(STAGE_DAG)`=21 어서트). 이 e2e는 v5→v6 스테이지 재설계로 이미 깨진 상태. 또한 `DEV_BOOTH_DRYRUN=1`을 세팅하지만 `core/session.py`는 이 플래그를 전혀 읽지 않아(`grep` 없음) seed 경로엔 무효. **권고:** e2e를 21-task로 갱신하고 C1의 dryrun 결정에 맞춰 dryrun 가정을 정리. 또한 **C1이 지적한 `run.sh`/시나리오 dryrun 분기 불일치(가장 시급한 breakage)를 검증하는 자동 테스트가 전혀 없다** — seed→인증→push 경로와 live/dryrun 분기에 대한 회귀 가드를 추가하라(현 스위트는 정적 DAG·시드·워치독만 커버).

### H6 — 계획된 중앙 설정 모듈 `core/config.py`가 실제로 존재하지 않음 (H2 하드코딩의 근본 원인)
`config/.env` 주석과 계획서(`reports/plans/…v3.md`)는 라이브 엔드포인트·`HERMES_BIN`·`SESSIONS_ROOT`·`EXPECTED_MODEL` 등을 담을 권위 모듈로 `core/config.py`를 가리키지만 실제로는 없다 — `find . -name config.py -not -path './env/*'` → `archive/v1-stateless-orchestrator/config.py`와 `dashboard/backend/config.py`만(코어엔 없음). 즉 v1에는 중앙 config가 있었으나 v2 `core/`에는 만들어지지 않았고, 그 결과 `HERMES_BIN`·경로·모델 식별자가 `run.sh`·`core/session.py`·`kanban_reader.py`·`sessions.py`에 제각기 하드코딩됐다(H2·L4의 근본 원인). **권고:** `core/config.py`(또는 동등 모듈)를 신설해 바이너리 경로·세션 루트·모델 식별자를 env 오버라이드 가능한 단일 출처로 모을 것.

### H7 — `origin` 리모트 URL에 평문 GitHub PAT 임베드 (보안/위생)
로컬 `.git/config`의 `origin` URL에 GitHub Personal Access Token이 평문으로 박혀 있다(`https://mooner92:<PAT>@github.com/…` 형태 — **토큰 값은 본 보고서에 기록하지 않음**). `.git/`은 커밋·push되지 않으므로 저장소 이력에 유출되진 않으나, (a) 디스크에 평문으로 상주하고, (b) `git remote -v`·셸 히스토리·로그·프로세스 목록으로 노출될 수 있으며, (c) credential helper/SSH 대신 인라인 PAT를 쓰는 것은 권장되지 않는다. **권고:** URL에서 토큰을 제거하고 git credential helper(또는 SSH 원격)로 전환; 노출 가능성이 있었다면 해당 PAT를 폐기·재발급. 어떤 경우에도 토큰 값을 추적되는 파일에 기록하지 말 것.

---

## 🟡 Medium

### M1 — `/api/sessions/start`가 무인증 + 임의 repo_url 클론 + 전체 env 전달
`dashboard/backend/routers/sessions.py:38-47`은 `python -m core.session <slug> <repo_url> --goal <goal>`를 `env=os.environ.copy()`로 스폰한다. seed 경로는 git/gh를 호출하지 않으므로 push는 없지만, (a) FastAPI가 토큰을 들고 떠 있으면 그 토큰이 불필요하게 자식 env로 새고, (b) 엔드포인트에 인앱 인증이 없어 Cloudflare 터널로 노출 시 누구나 임의 URL의 클론+시드를 트리거할 수 있다(`session_name`만 slug 검증, `repo_url` 미검증). 인증은 Cloudflare Access 레이어 가정. 추가 위험: (c) seed 서브프로세스가 **모든 실패를 삼킨다** — `sessions.py:46-47`이 `TimeoutExpired`/`OSError`를 잡고 `pass`하며 `check=False`라, repo_url 오류·kanban 실패로 seed가 깨져도 API는 success를 반환한다(호출자에게 실패가 전달되지 않음). (d) `repo_url`은 검증 없이 `core.session`으로 넘어가 시나리오 body의 `gh repo fork {repo_url}`·`gh repo clone` 셸 문자열로 에이전트 셸에서 실행된다 — 단순 "임의 클론"을 넘어 **명령/인자 주입 표면**. **권고:** 최소 env(PATH, DEVBOOTH_SESSIONS_ROOT)만 명시 전달, public 도달 가능하면 start 엔드포인트에 인증/레이트리밋, `repo_url`을 엄격 검증(허용 호스트·형식)하고 seed 실패를 표면화(`check=True` + 상태 반영).

### M2 — `_kanban_json`이 모든 오류를 `{}`로 삼킴 → 시드 중 침묵 실패
`core/session.py:137-147`이 `CalledProcessError`/`JSONDecodeError`를 잡아 `{}` 반환. 시드 루프(`:111-113`)는 `result.get("id","")` → 빈 task_id를 `stage_id_map`에 넣고, 부모 링크(`:107-109`)가 빈 `--parent`를 넘겨 **DAG가 조용히 손상**된다(유일 신호는 빈 id가 찍힌 `-> ` 출력). **권고:** "비어도 정상"(boards list)과 "id를 반드시 반환해야 함"(create)을 구분 — create가 id를 안 주면 raise하고 stderr를 로깅.

### M3 — 레이어 역전: `core/`가 `dashboard/`에 의존
`core/watchdog.py:33`이 `dashboard.backend.services.kanban_reader`에서 `HERMES_BIN, KanbanReader`를 import. 코어가 대시보드 패키지에 의존 → 워치독 실행에 대시보드가 PYTHONPATH에 있어야 함. 또한 그 `KanbanReader.KANBAN_BOARDS_ROOT = Path.home()/.hermes/kanban/boards`(`kanban_reader.py:19`)는 운영자의 **공유 글로벌** hermes 경로를 읽으므로 H2/H3의 비이식성을 가중시킨다. **권고:** `KanbanReader`를 공용 위치(예: H6의 `core/config.py` 인접)로 올리거나 워치독용 경량 리더를 분리하고, 보드 루트를 env로 오버라이드 가능하게 할 것.

### M4 — 프론트엔드가 여전히 12-stage 모델 사용 (21-stage DAG와 stale)
`dashboard/frontend/lib/constants.ts:45-58` `STAGE_ORDER`가 12개, `components/StageBar.tsx:7,12` `Math.min(12,stage)/12`, `app/page.tsx:113`에 "12단계" 하드코딩. 21-stage 세션의 진행바가 12에서 캡되거나 잘못 표시(칸반 세션은 SessionDetailClient가 태스크 수 기반 진행률을 우선하나, 목록 페이지 SessionCard/StageBar는 항상 12-stage `status.current_stage` 사용). 백엔드 `stage_mapper.py`의 12→21 collapse는 `test_stage_narration_crossseam.py`가 강제하는 의도된 seam이지만, 프론트 표기·라벨은 정합화 필요. **권고:** STAGE 라벨/길이를 백엔드 seam과 일치시키고 "12단계" 하드코딩 카피 제거.

### M5 — 프론트엔드 dead code + 미사용 의존성 번들 동봉
`components/MonitoringPane.tsx`·`FileTreePane.tsx`는 어디서도 import되지 않음(JSX 마운트 0). `MiniChart`/`QueueDepthCard`는 dead MonitoringPane 안에서만 쓰여 무거운 `recharts`가 무의미하게 번들에 포함. `@tanstack/react-virtual`은 ChatStream이 "v10에서 제거"했다고 명시했는데도 `package.json` deps에 잔존. `MonacoModal`은 와이어링됐지만 UI 진입점이 없어 도달 불가. **권고:** dead 컴포넌트/의존성 제거로 번들·혼란 감소.

### M6 — `village_proxy`의 모듈 레벨 httpx 클라이언트가 종료되지 않음
`dashboard/backend/routers/village_proxy.py:25`가 import 시 `_client = httpx.AsyncClient(...)` 생성. `main.py` lifespan은 `prometheus`·`hub_registry`만 닫고 이 클라이언트는 닫지 않아 종료 시 커넥션 풀 누수(장수 서비스라 영향은 작지만 다른 두 클라이언트와 비일관). **권고:** lifespan 종료에 `await village_proxy._client.aclose()` 추가.

### M7 — AWG가 벤더링-but-untracked (버전 핀 없음) + copy-paste 결합
`agent-working-group/`은 `.gitignore`에 (중복) 등재되어 추적되지 않으며 자체 `.git` 저장소다(서브모듈 아님, `.gitmodules` 없음). Dev-Booth를 clone해도 따라오지 않고 디스크에 우연히 있는 버전이 곧 버전이다. 대시보드는 AWG의 리더/스키마를 **복사**(import 아님: `awg_inspector.py:3-7`, `models.py:1-14`)해 형식이 진화하면 컴파일/의존 신호 없이 조용히 분기. 또한 `config.KNOWN_AGENTS`는 AWG-형식 conductor/architect/executor 큐를 기대하지만 라이브 세션은 그런 큐를 만들지 않아(Hermes SQLite 사용) AWG 큐 깊이 패널은 사실상 데모용. **권고:** AWG가 런타임 의존이면 submodule/subtree로 핀하고 패키지로 의존; 아니면 README/문서에서 "런타임 미사용·과거 실험"임을 명시(본 검토에서 일부 반영).

---

## 🟢 Low

### L1 — 프론트엔드가 세션 페이지에서 `useKanban`을 2번 마운트 → REST·WS 2중 연결
`components/SessionDetailClient.tsx:70` `useKanban(boardSlug, selectedTaskId)`와 `components/KanbanBoard.tsx:177` `useKanban(boardSlug)`가 동시에 동작해 같은 보드로 `/tasks`+`/stats`+`/timeline` 2중 prefetch와 WebSocket 2중 연결. **권고:** 공유 컨텍스트/캐시로 단일화.

### L2 — `.omc/` 런타임 상태가 gitignore되지 않아 워킹 트리를 더럽힘
`git status`에 다수 `.omc/state/*`(agent-replay-*.jsonl, mission-state.json, subagent-tracking.json, checkpoints/, dashboard/.omc/…)가 M/D/?? 로 잡힘 — 툴 런타임 상태이지 소스 아님. `.gitignore`에 `.omc/`가 없음. **권고:** `.gitignore`에 `.omc/` 추가 후 추적분 `git rm --cached`.

### L3 — archive의 사장된 v1 테스트(12개 파일)가 naive `pytest`를 깨뜨림
`archive/v1-stateless-orchestrator/tests/*`가 존재하지 않는 `core.orchestrator` 등을 import → 루트에서 `pytest`만 치면 18개 collection error(`agent-working-group/tests/`도 `PYTHONPATH=src` 필요해 함께 실패). 현재 우회는 암묵적: 반드시 `pytest tests/`(144 통과)로 스코프해야 함. **권고:** `pyproject.toml`/`pytest.ini`에 `testpaths = ["tests"]`(또는 `norecursedirs`로 archive·agent-working-group 제외) 추가. archive는 별도 태그/브랜치로 분리 고려.

### L4 — 모델 식별자 불일치 (단일 출처 부재)
문서 전반은 `Qwen2.5-Coder-32B`(systemd 유닛 `vllm-qwen25-coder-32b`와 일치)이다. `config/.env`의 주석은 **별도의 `:8000` vLLM 인스턴스를 설명하는 맥락에서** `Qwen3-Coder-Next` 이름을 언급하고, 라이브 `:8003` 엔드포인트의 권위 출처로 `core/config.py`를 가리킨다 — **그러나 그 `core/config.py`는 존재하지 않는다(H6 참조).** 추적되는 `config.yaml`도 없어(`find . -name config.yaml` → 없음) 라이브 모델 식별자를 코드로 확정할 수 없다. archive `config.py:74`는 또 14B를 핀. **권고:** 권위 있는 단일 출처(예: H6의 `core/config.py` 또는 hermes 프로파일)를 실제로 만들고 문서·`config/.env` 주석을 거기에 일치시킬 것.

### L5 — 백엔드 `stage_mapper.py`/`models.py`의 "12 stages" 표현이 stale
기능 버그는 아니나(cross-seam 테스트가 12↔21 collapse를 강제) docstring·주석의 "12 pipeline stages"·"current_stage 1..12"는 v6 기준 오해 소지. **권고:** "21-stage DAG를 12 표시 스테이지로 collapse"임을 주석에 명시.

### L6 — 기타 위생
- `.gitignore`에 `agent-working-group/`이 **중복** 등재(12·13행). 무해하나 churn 흔적.
- `dashboard/backend/scripts/smoke.sh:12`의 `check()` `EXPECT_NOT_200` 분기가 dead(`$2`가 URL이라 조건 미성립) — 인라인 traversal 체크만 실효.
- `run.sh:98-103` `cmd_stop`이 `$SESSION`·`$HERMES`를 `python -c` 소스 문자열에 직접 보간 — 보드/세션명이 venv 인터프리터가 실행하는 Python 소스에 주입되므로 단순 따옴표 깨짐을 넘어 **셸+Python 주입** 표면(정상 운영 입력에선 무해하나 입력 신뢰가 약해지면 위험). 권고: `argv`로 값을 전달하거나 별도 스크립트로 분리.
- 보고서 파일명 규약: 콜론 형(`…14:03:10…`)에서 하이픈 형(`…14-03-10…`)으로 이전 중(`git status`). 하이픈 형이 이식성 안전 — 규약 문서를 하이픈 형으로 확정.

---

## ✅ 검증된 정상/긍정 항목

- 시크릿 미추적: `git ls-files | grep -iE 'env|secret|token|key'` → `next-env.d.ts`(생성된 타입 셰임)만. `config/.env`·`.env`·프론트 `.env*.local` 모두 gitignored. 커밋된 빌드 산출물 없음(node_modules/.next/dist/__pycache__ 추적 0).
- SQLite는 엄격 읽기 전용: `kanban_reader.py:227` `sqlite3.connect("file:…?mode=ro", uri=True)`.
- subprocess는 리스트 폼 `shell=False`: `core/session.py:131`. 셸 문자열 결합 없음.
- 파일 읽기 엔드포인트는 3중 traversal/symlink 방어(`path_guard.py`, `sessions.py:307-310`).
- Prometheus 프록시는 5개 명명 프리셋만 허용(자유 PromQL 거부 = SSRF 방어).
- `.worktrees/`·`agent-working-group/`·`sessions/`·`env/`는 디스크에 있으나 추적 0.
- 테스트: `env/bin/python -m pytest tests/ -q` → **144 passed** (정적 DAG 정합성 127 + 시드 7 + 워치독 10). 대시보드 백엔드 테스트 별도 ~98개.

---

## 권고 실행 순서 (제안)

0. **H7 즉시 조치** (보안): `.git/config` `origin` URL의 평문 PAT를 credential helper/SSH로 대체; 노출 가능성 있으면 토큰 폐기·재발급.
1. **C1 결정·완료** (always-live로 가정): 미커밋 3파일 + `run.sh` 기본값 `live` + 토큰 스크럽/`$DRYRUN_BIN`(양쪽 분기)/`core/dryrun/`/`hermes-gateway.service` dryrun env 제거 + `executor.SOUL.md`+`core/memories/executor.MEMORY.md` Dryrun 절 정리 — **한 커밋으로**. C1 breakage 회귀 테스트 추가(H5).
2. **C2 문서 정합화**: ARCHITECTURE·MANUAL·QUICKSTART를 21-stage/always-live로 (README·TECHNICAL_OVERVIEW·H4는 본 검토에서 완료). H5 e2e 21-task 갱신.
3. **H2/H3/H6 이식성**: `core/config.py`(또는 동등)를 신설해 `HERMES_BIN`·세션 루트·인터프리터·모델 식별자를 env 오버라이드 가능한 단일 출처로; `DEV_BOOTH_PATH` 의미 분리; `run.sh`(python3.11)와 `sessions.py`(python3) 인터프리터 통일.
4. **M 시리즈**: M1(start 보안·실패 표면화·repo_url 검증), M2(침묵 실패), M3(레이어 역전·공유 경로), M4/M5(프론트 정합·dead 제거), M6(클라이언트 종료), M7(AWG 핀/명시).
5. **L 시리즈 위생**: `.omc/` ignore, `testpaths` 설정, 모델 식별자 확정(H6/L4), 중복 gitignore 정리, `cmd_stop` 주입 표면 하드닝.

---

*증거 원천: 7개 병렬 검토 에이전트의 상세 분석(core/backend/frontend/awg/periphery/doc-drift/quality-security)을 통합·중복 제거하고 file:line으로 재검증.*
