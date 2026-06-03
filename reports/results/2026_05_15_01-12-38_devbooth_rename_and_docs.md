# Dev-Booth — 에이전트 이름 변경 + 문서화 + Gateway systemd 등록 — 결과 보고서

**날짜:** 2026-05-15
**브랜치:** `feat/kanban-redesign-2026-05-14` (`main` 미변경)
**모드:** ralph PRD-driven, 8개 user story US-001..US-008
**이전 작업:** `eb6b85a` (Hermes Kanban 재플랫폼) 위에서 진행

---

## 요약

Dev-Booth의 세 에이전트를 역할 기반 이름으로 전면 개명하고
(`openclaw→conductor`, `hermes-a→architect`, `hermes-b→executor`),
GitHub 공개 수준의 README + 한국어 운영 문서 3종(MANUAL/ARCHITECTURE/QUICKSTART)을
작성했으며, hermes-gateway를 systemd 서비스로 등록할 수 있도록 유닛 파일을 준비했다.

**검증:** pytest 78개 전부 통과, frontend `tsc --noEmit` 0 에러,
`core.scenario`/`core.session` import 정상, 전체 코드베이스에서 구 이름 0건.

---

## Deliverable 결과

### US-001 — Hermes 프로필 개명
- `conductor`/`architect`/`executor` 프로필을 각각 `openclaw`/`hermes-a`/`hermes-b`에서
  `hermes profile create <name> --clone --clone-from <src>`로 생성 (Qwen2.5-Coder-14B 설정 그대로 복제).
- 각 프로필에 역할별 SOUL.md 설치 (`~/.hermes/profiles/{conductor,architect,executor}/SOUL.md`),
  버전관리 원본은 `core/souls/{conductor,architect,executor}.SOUL.md`.
- 구 프로필(`openclaw`/`hermes-a`/`hermes-b`)은 검증 전까지 **삭제하지 않고 유지**.

### US-002 — 코드베이스 전체 개명
- `core/scenario.py`: `ALLOWED_ASSIGNEES = {conductor, architect, executor}`,
  12개 StageTask assignee 값 + 내레이션 + body 템플릿 전부 개명,
  분석 산출물 경로 `analysis_architect.md` / `analysis_executor.md`로 변경.
- `core/session.py`: 기본 agent `conductor`, 주석 예시 갱신.
- `core/souls/`: 파일명 + 내용 개명 (구 파일 git rm).
- `dashboard/frontend/{lib/constants.ts,tailwind.config.ts}`: `AGENTS`, `AGENT_COLORS`,
  `AGENT_LABELS`, `AGENT_INITIALS`(CD/AR/EX) 갱신.
- `dashboard/backend/config.py` `KNOWN_AGENTS` + 백엔드 테스트 픽스처/스크립트/`models.py` 독스트링 +
  `core/dryrun/install_hooks.sh` 주석 + `tests/test_session.py` 개명.
- **검증 grep:** `core/`+`dashboard/`의 `*.py`/`*.ts`/`*.tsx`에서 구 이름 0건 (archive 제외).

### US-003 — hermes-gateway systemd 등록
- 유닛 파일을 `/dev-booth/config/hermes-gateway.service`에 준비
  (`Type=simple`, `User=mooner92`, `DEV_BOOTH_DRYRUN=1`, `GITHUB_TOKEN`/`GH_TOKEN` 스크럽,
  `After/Wants=vllm-qwen25-coder-32b.service`, `Restart=on-failure`).
- **운영자 실행 필요:** 이 환경의 sudo가 비밀번호를 요구하여 자동 설치 불가.
  운영자가 다음을 실행:
  ```bash
  pkill -f "hermes gateway run"; sleep 2
  sudo cp /dev-booth/config/hermes-gateway.service /etc/systemd/system/hermes-gateway.service
  sudo systemctl daemon-reload && sudo systemctl enable hermes-gateway && sudo systemctl start hermes-gateway
  sudo systemctl status hermes-gateway --no-pager | grep -E "Active|running|failed"
  ```
- 현재 게이트웨이는 B1 (foreground, PID 3378382)로 동작 중 — 재부팅 시 꺼짐.

### US-004 — README.md
- `/dev-booth/README.md` (189줄): 한/영 Abstract, 시스템 아키텍처 ASCII 다이어그램
  (mooner92 ← PR ← CrownClownCrowd ← Dev-Booth ← conductor/architect/executor),
  12단계 시나리오, 기술 스택 표, 디렉터리 구조, 빠른 시작, 대시보드 URL, 라이선스, 문서 링크.

### US-005 — docs/MANUAL.md
- `/dev-booth/docs/MANUAL.md` (578줄, 한국어): 9개 섹션 — 시스템 개요, 사전 준비,
  세션 시작, 모니터링, Kanban 명령어 모음(`--board` 선행 문법), 트러블슈팅(5종),
  프로필 관리, 세션 데이터 경로, dryrun vs live.

### US-006 — docs/ARCHITECTURE.md
- `/dev-booth/docs/ARCHITECTURE.md` (407줄, 한국어): 7개 섹션 — 전체 구성도,
  Hermes Kanban 동작 원리, 에이전트 간 통신 흐름, dryrun 3중 레이어, vLLM 설정,
  Cloudflare Tunnel, 데이터 흐름도. 실제 소스(`session.py`/`scenario.py`/`run.sh`/
  `routers/kanban.py`/`kanban_reader.py`)와 일치하도록 작성.

### US-007 — docs/QUICKSTART.md
- `/dev-booth/docs/QUICKSTART.md` (86줄, 한국어): 5분 가이드 5개 섹션 —
  서비스 상태 확인, 첫 세션 시작, 대시보드 접속, 진행 상황 확인, 자주 쓰는 명령어.

### US-008 — 검증 / 커밋 / 푸시 / 대시보드 재시작
- `pytest tests/ dashboard/backend/tests/` → **78 passed**.
- `npx tsc --noEmit` (frontend) → **0 errors**; `npm run build`로 정적 export 재생성.
- `core.scenario` import 시 `STAGE_DAG` 12개, `ALLOWED_ASSIGNEES == {architect,conductor,executor}`.
- **대시보드 재시작은 운영자 실행 필요:** `dev-booth-dashboard.service`는 system 서비스이고
  이 환경의 sudo가 비밀번호를 요구하여 `systemctl restart`를 자동 실행할 수 없음.
  운영자가 `sudo systemctl restart dev-booth-dashboard` 실행 (개명된 `KNOWN_AGENTS` +
  재빌드된 frontend `out/` 반영).
- 전체 변경 `feat/kanban-redesign-2026-05-14`에 커밋 + 푸시; `main` 미변경.

---

## 변경 파일

**신규:** `README.md`, `docs/{MANUAL,ARCHITECTURE,QUICKSTART}.md`,
`config/hermes-gateway.service`, `core/souls/{conductor,architect,executor}.SOUL.md`.
**개명/삭제:** `core/souls/{openclaw,hermes-a,hermes-b}.SOUL.md` → 신규 3종.
**수정:** `core/{scenario,session}.py`, `core/dryrun/install_hooks.sh`,
`dashboard/frontend/{lib/constants.ts,tailwind.config.ts}`,
`dashboard/backend/{config.py,services/models.py,docs/log-schema.md,scripts/*,tests/*}`,
`tests/test_session.py`.

## 운영자 TODO

- **OT1** — `hermes-gateway.service` 설치 (위 sudo 블록). 완료 후 `systemctl is-active hermes-gateway` = `active`.
- 구 Hermes 프로필(`openclaw`/`hermes-a`/`hermes-b`)은 신규 프로필 검증 후 삭제 가능.
