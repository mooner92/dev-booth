"""Dev-Booth 21-stage scenario — micro-task DAG (v6, 2026-05-17).

This module is pure data + formatting. It does NOT run agents. ``core/session.py``
seeds this DAG onto a Hermes Kanban board; the gateway dispatcher then spawns the
assigned profiles as workers.

v6 (micro-task): every stage is sized for a 5-turn agent budget. Each body:
  * stays under 2 000 chars (~500 tokens),
  * includes a "head -n N / tail -n N" rule so workers never load full files,
  * names the exact files to read (max 3) and the single output file to write,
  * ends with the literal ``kanban_complete(...)`` (and optional ``kanban_block``)
    so the protocol_violation failure mode stays at zero.

Earlier 12-stage v5 corpus is preserved in git history; STAGE_NARRATION is kept
for the dashboard's monotonic stage_mapper but now indexes the new 21-stage flow
(grouped so the dashboard's 12->8 derived progression still increases).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Canonical narration corpus — one line per scenario stage. The keywords match
# stage_mapper rules so detect_stage() is monotonic non-decreasing across 1..21.
STAGE_NARRATION: dict[int, str] = {
    1:  "git clone: 레포지토리 포킹 및 클론 시작",
    2:  "initial scan: 디렉터리 구조 파악",
    3:  "initial scan: README + 패키지 파일 분석",
    4:  "initial scan: 진입점 파일 분석 (Architect)",
    5:  "initial scan: 컴포넌트 분석 1/2 (Architect)",
    6:  "initial scan: 컴포넌트 분석 2/2 (Architect)",
    7:  "initial scan: API/라우터 분석 (Architect)",
    8:  "initial scan: 설정/환경 분석 (Executor)",
    9:  "initial scan: 의존성/취약점 분석 (Executor)",
    10: "initial scan: 분석 결과 취합",
    11: "drafting the implementation plan: 개선방안 TASK 목록 작성",
    12: "plan approved: feature 브랜치 생성",
    13: "implementing: TASK-1 구현",
    14: "running tests: TASK-1 자동 테스트 실행",
    15: "tests passed: TASK-1 리뷰",
    16: "implementing: TASK-2 구현",
    17: "running tests: TASK-2 자동 테스트 실행",
    18: "tests passed: TASK-2 리뷰",
    19: "tests passed: 모든 변경사항 커밋",
    20: "pr drafted: PR 초안 작성",
    21: "pr merged: PR 제출 완료",
}


# The three Hermes profiles the dispatcher can spawn.
ALLOWED_ASSIGNEES: frozenset[str] = frozenset({"conductor", "architect", "executor"})


@dataclass
class StageTask:
    """One node of the static micro-task DAG."""

    stage: int
    title: str
    assignee: str
    workspace: str
    tag: str
    body_template: str
    parent_stages: list[int] = field(default_factory=list)
    is_review_gate: bool = False
    skills: list[str] = field(default_factory=list)


# Per-skill use-case registry. Keys are Hermes skill names; values are
# one-line Korean use-case descriptions shown in every stage body.
SKILL_USE_CASES: dict[str, str] = {
    "github-auth":                 "GitHub 인증 (gh auth status, token 환경변수 검증)",
    "github-repo-management":      "레포 fork / clone / 브랜치 생성",
    "github-pr-workflow":          "branch → commit → PR 작성/제출 / CI 대기 전체 lifecycle",
    "github-code-review":          "PR 리뷰 (코드 진단 + 코멘트 작성)",
    "requesting-code-review":      "내 코드를 리뷰받을 수 있게 정리하는 절차",
    "codebase-inspection":         "낯선 레포의 구조 / 핵심 파일 / 의존성 파악",
    "architecture-diagram":        "ASCII / Mermaid 로 아키텍처 그리기",
    "writing-plans":               "markdown 계획서 작성 컨벤션 (이 프로젝트는 reports/plans/)",
    "plan":                        "plan 모드 — 코드 안 짜고 markdown 계획만 작성",
    "test-driven-development":     "RED → GREEN → REFACTOR; 테스트가 코드보다 먼저",
    "systematic-debugging":        "실패 테스트 / 버그의 근본 원인 분리 절차",
    "subagent-driven-development": "범위 큰 구현을 자식 에이전트에게 위임",
    "spike":                       "옵션 비교용 시한부 탐색 (결과는 폐기되거나 흡수)",
}


# Common header injected into every body so the worker sees the file-reading
# rule before anything else. Kept short — 5 lines, ~200 chars.
_FILE_READING_RULE = """## ⚠️ 파일 읽기 규칙 (필수)
- `cat <파일>` 금지 → `head -n 100 <파일>` 만 사용 (최대 100줄)
- 명령 결과는 `... | tail -n 20` 으로만 확인
- 한 태스크에서 읽는 파일 최대 3개

"""


def _body(text: str) -> str:
    """Prepend the file-reading rule and strip trailing whitespace."""
    return _FILE_READING_RULE + text.rstrip() + "\n"


# --------------------------------------------------------------------------
# The 21-stage micro DAG.
# --------------------------------------------------------------------------
STAGE_DAG: list[StageTask] = [

    # ── 준비 (1-3) ───────────────────────────────────────────────────────
    StageTask(
        stage=1, title="[{repo}] fork & clone",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[],
        skills=["github-auth", "github-repo-management"],
        body_template=_body("""## 작업
{repo_url} 를 fork & clone 하세요.

## 단계
1. `gh repo fork {repo_url} --org CrownClownCrowd --clone=false`
2. `gh repo clone CrownClownCrowd/{repo} {session_path}/project`
3. `cd {session_path}/project && git checkout -b develop`
4. `bash /dev-booth/core/dryrun/install_hooks.sh {session_path}/project`

## 완료
kanban_complete(
    summary="fork & clone 완료: {session_path}/project (branch=develop)",
    metadata={{"repo_name": "{repo}", "repo_url": "{repo_url}",
               "clone_path": "{session_path}/project", "branch": "develop"}}
)
"""),
    ),

    StageTask(
        stage=2, title="[{repo}] 디렉터리 구조 파악",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[1],
        skills=["codebase-inspection"],
        body_template=_body("""## 작업
클론된 레포의 구조만 파악 (파일 내용 X).

## 단계
1. `kanban_show()` → 부모 stage 1 metadata.clone_path 확인
2. `cd <clone_path> && find . -type f -not -path './.git/*' | head -100`
3. 결과를 `{session_path}/dir_structure.txt` 에 저장 (write 툴)

## 완료
kanban_complete(
    summary="디렉터리 구조 파악 완료 (파일 N개)",
    metadata={{"file": "{session_path}/dir_structure.txt",
               "clone_path": "<stage 1 의 clone_path>"}}
)
"""),
    ),

    StageTask(
        stage=3, title="[{repo}] README + 패키지 파일 분석",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[2],
        skills=["codebase-inspection"],
        body_template=_body("""## 작업
README + 패키지 매니페스트로 기술 스택 파악.

## 읽을 파일 (각각 head -n 50)
- README.md (또는 README)
- package.json / requirements.txt / go.mod / pyproject.toml 중 존재하는 하나

## 저장
{session_path}/tech_stack.md
형식: `# Tech Stack\\n- Language: ...\\n- Framework: ...\\n- 주요 deps: ...`

## 완료
kanban_complete(
    summary="기술 스택 파악: <한 줄 요약>",
    metadata={{"file": "{session_path}/tech_stack.md",
               "clone_path": "<stage 1 clone_path>",
               "tech_stack": "<예: React 17 / Python FastAPI>"}}
)
"""),
    ),

    # ── 코드 분석 (4-9) ──────────────────────────────────────────────────
    StageTask(
        stage=4, title="[{repo}] 진입점 파일 분석",
        assignee="architect", workspace="worktree", tag="analysis",
        parent_stages=[3],
        skills=["codebase-inspection"],
        body_template=_body("""## 작업
앱의 진입점 파일을 분석 (최대 3개).

## 단계
1. `head -n 50 {session_path}/dir_structure.txt` 로 후보 파악
2. 다음 중 존재하는 파일 최대 3개를 `head -n 100` 으로 읽기:
   src/index.{{js,ts}} / src/main.{{js,ts,py}} / src/App.{{js,tsx}} / app.py / main.go

## 저장
{session_path}/analysis_entrypoint.md
- 어떤 프레임워크 진입 패턴인지
- 주요 import / 초기화 로직 1-2개

## 완료
kanban_complete(
    summary="진입점 분석 완료: <한 줄 요약>",
    metadata={{"file": "{session_path}/analysis_entrypoint.md",
               "clone_path": "<stage 1 clone_path>"}}
)

## 막힐 때
kanban_block(reason="review-required: <구체적 이유>")
"""),
    ),

    StageTask(
        stage=5, title="[{repo}] 컴포넌트/모듈 분석 1/2",
        assignee="architect", workspace="worktree", tag="analysis",
        parent_stages=[4],
        skills=["codebase-inspection"],
        body_template=_body("""## 작업
components/ 또는 modules/ 의 앞쪽 절반 분석.

## 단계
1. `grep -E 'components/|modules/|src/lib/' {session_path}/dir_structure.txt | head -n 50`
2. 목록의 앞 3개 파일을 `head -n 80` 으로 읽기
3. 각 파일 1줄 요약 + 발견한 코드 스멜

## 저장
{session_path}/analysis_components_1.md

## 완료
kanban_complete(
    summary="컴포넌트 분석 1/2 완료 (3 files)",
    metadata={{"file": "{session_path}/analysis_components_1.md",
               "clone_path": "<stage 1 clone_path>"}}
)
"""),
    ),

    StageTask(
        stage=6, title="[{repo}] 컴포넌트/모듈 분석 2/2",
        assignee="architect", workspace="worktree", tag="analysis",
        parent_stages=[5],
        skills=["codebase-inspection"],
        body_template=_body("""## 작업
components/ 의 나머지 절반 분석.
analysis_components_1.md 는 읽지 말 것 (컨텍스트 절약).

## 단계
1. `grep -E 'components/|modules/|src/lib/' {session_path}/dir_structure.txt | head -n 50`
2. 목록의 4-6번째 파일을 `head -n 80` 으로 읽기 (이미 분석된 1-3 건너뜀)
3. 각 파일 1줄 요약 + 코드 스멜

## 저장
{session_path}/analysis_components_2.md

## 완료
kanban_complete(
    summary="컴포넌트 분석 2/2 완료 (3 files)",
    metadata={{"file": "{session_path}/analysis_components_2.md",
               "clone_path": "<stage 1 clone_path>"}}
)
"""),
    ),

    StageTask(
        stage=7, title="[{repo}] API/라우터 분석",
        assignee="architect", workspace="worktree", tag="analysis",
        parent_stages=[3],
        skills=["codebase-inspection", "architecture-diagram"],
        body_template=_body("""## 작업
API 엔드포인트 또는 라우터 파일 분석.

## 단계
1. `grep -E '(api|routes|server|controller)/' {session_path}/dir_structure.txt | head -n 30`
2. 후보 3개 파일을 `head -n 80` 으로 읽기
3. 엔드포인트 목록 + 인증/검증 누락 여부 정리

## 저장
{session_path}/analysis_api.md
- 발견된 엔드포인트 수
- 인증/검증 누락 여부

## 완료
kanban_complete(
    summary="API 분석 완료: 엔드포인트 N개",
    metadata={{"file": "{session_path}/analysis_api.md",
               "clone_path": "<stage 1 clone_path>",
               "endpoint_count": 0}}
)
"""),
    ),

    StageTask(
        stage=8, title="[{repo}] 설정/환경 분석",
        assignee="executor", workspace="worktree", tag="analysis",
        parent_stages=[3],
        skills=["codebase-inspection"],
        body_template=_body("""## 작업
설정 파일과 환경 변수 분석.
**절대 .env 파일은 읽지 마세요 (.env.example 만).**

## 단계
1. `head -n 50 {session_path}/dir_structure.txt | grep -E '(config|\\\\.env\\\\.example|tsconfig|eslint)'`
2. 후보 3개 (`.env.example`, `tsconfig.json`, `.eslintrc*`, `config.{{js,py}}`)를 `head -n 50`
3. 발견된 설정 항목 정리

## 저장
{session_path}/analysis_config.md

## 완료
kanban_complete(
    summary="설정 분석 완료",
    metadata={{"file": "{session_path}/analysis_config.md",
               "clone_path": "<stage 1 clone_path>"}}
)
"""),
    ),

    StageTask(
        stage=9, title="[{repo}] 의존성/취약점 분석",
        assignee="executor", workspace="worktree", tag="analysis",
        parent_stages=[3],
        skills=["codebase-inspection"],
        body_template=_body("""## 작업
의존성과 보안 취약점 분석.

## 단계
1. `head -n 80 <clone_path>/package.json` 또는 `head -n 80 <clone_path>/requirements.txt`
2. `cd <clone_path> && (npm audit --json 2>&1 || pip-audit 2>&1) | tail -n 20`
3. 오래된 패키지 / 취약점 카운트

## 저장
{session_path}/analysis_deps.md
- 의존성 N개
- 취약점 N개 (high/critical)

## 완료
kanban_complete(
    summary="의존성 분석: deps N, vuln M",
    metadata={{"file": "{session_path}/analysis_deps.md",
               "clone_path": "<stage 1 clone_path>",
               "vulnerabilities": 0}}
)
"""),
    ),

    # ── 취합 + 계획 (10-12) ─────────────────────────────────────────────
    StageTask(
        stage=10, title="[{repo}] 분석 결과 취합",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[6, 7, 8, 9],
        skills=["writing-plans"],
        body_template=_body("""## 작업
분석 결과 파일 3개만 head -n 30 으로 읽고 요약 작성.

## 읽을 파일 (각각 head -n 30)
1. {session_path}/analysis_entrypoint.md
2. {session_path}/analysis_api.md
3. {session_path}/analysis_deps.md

(components_*.md / analysis_config.md 는 컨텍스트 절약을 위해 *건너뜀*)

## 저장
{session_path}/summary_v1.0.0.md
- # Summary v1.0.0
- ## 프로젝트 개요 (3줄)
- ## 핵심 발견사항 (bullet list)
- ## 개선 우선순위 (top 3)

## 완료
kanban_complete(
    summary="분석 종합 요약 완료",
    metadata={{"file": "{session_path}/summary_v1.0.0.md",
               "top_issue_count": 0}}
)
"""),
    ),

    StageTask(
        stage=11, title="[{repo}] 개선방안 TASK 목록 작성",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[10],
        skills=["plan", "writing-plans"],
        body_template=_body("""## 작업
summary_v1.0.0.md 만 읽고 (head -n 60) 개선 TASK 목록 작성.
이 태스크 body 를 그대로 복붙 금지.

## 단계
1. `head -n 60 {session_path}/summary_v1.0.0.md`
2. Top issues 를 실행 가능한 TASK 로 변환 (정확히 2개: TASK-1, TASK-2)
3. 각 TASK 는 1-2개 파일만 수정하는 작은 단위

## 저장
{session_path}/improvements_v0.0.1.md
형식:
```
# Dev-Booth Improvements (v0.0.1)
## TASK-1: <제목>
- 담당: executor
- 파일: <파일 1개>
- 설명: <구체적 변경>
- 수용 기준: <검증 가능한 조건>

## TASK-2: ...
```

## 완료
kanban_complete(
    summary="개선방안 작성 완료 (TASK 2개)",
    metadata={{"file": "{session_path}/improvements_v0.0.1.md",
               "task_count": 2}}
)
"""),
    ),

    StageTask(
        stage=12, title="[{repo}] feature 브랜치 생성",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[11],
        skills=["github-pr-workflow"],
        body_template=_body("""## 작업
feature 브랜치 생성. (DEV_BOOTH_DRYRUN=1 이면 push --dry-run)

## 단계
1. `cd {session_path}/project`
2. `git fetch origin && git checkout develop && git pull --ff-only`
3. `git checkout -b feature/devbooth-{session}-improvements`
4. dryrun: `git push --dry-run -u origin feature/devbooth-{session}-improvements`
   live: 위 명령에서 `--dry-run` 제거
5. `git branch --show-current | head -n 1` 로 확인

## 완료
kanban_complete(
    summary="feature 브랜치 생성 완료",
    metadata={{"branch": "feature/devbooth-{session}-improvements",
               "from": "develop",
               "clone_path": "{session_path}/project"}}
)
"""),
    ),

    # ── TASK-1: impl → test → review (13-15) ─────────────────────────────
    StageTask(
        stage=13, title="[{repo}] TASK-1 구현",
        assignee="executor", workspace="worktree", tag="implementation",
        parent_stages=[12],
        skills=["test-driven-development", "systematic-debugging"],
        body_template=_body("""## 작업
improvements_v0.0.1.md 의 **TASK-1 만** 구현. 다른 TASK 건드리지 말 것.

## 단계
1. `head -n 30 {session_path}/improvements_v0.0.1.md` → TASK-1 섹션 파악
2. TASK-1 대상 파일을 `head -n 80` 으로 읽기 (1개만)
3. edit / write 툴로 최소 수정
4. `git status | head -n 10` 로 변경 파일 확인

## 완료 (구현만 — 테스트는 stage 14)
kanban_complete(
    summary="TASK-1 구현 완료 — <한 줄 요약>",
    metadata={{"task_id_local": "TASK-1",
               "changed_files": ["<파일경로>"],
               "clone_path": "{session_path}/project"}}
)

## 막힐 때
kanban_block(reason="review-required: <구체적 이유>")
"""),
    ),

    StageTask(
        stage=14, title="[{repo}] TASK-1 테스트",
        assignee="executor", workspace="worktree", tag="implementation",
        parent_stages=[13],
        skills=["test-driven-development", "systematic-debugging"],
        body_template=_body("""## 작업
TASK-1 의 자동 테스트 실행 (전체 X, 영향 범위만).

## 단계
1. `cd {session_path}/project`
2. 다음 중 하나: `npm test 2>&1 | tail -n 20` / `pytest -q 2>&1 | tail -n 20` / `go test ./... 2>&1 | tail -n 20`
3. 결과 마지막 20줄을 `{session_path}/test_result_1.txt` 에 저장

## 완료 (통과)
kanban_complete(
    summary="TASK-1 테스트 통과",
    metadata={{"file": "{session_path}/test_result_1.txt",
               "task_id_local": "TASK-1",
               "test_result": "passed"}}
)

## 막힐 때 (실패)
kanban_block(reason="TASK-1 테스트 실패: <에러 1줄 from tail -n 20>")
"""),
    ),

    StageTask(
        stage=15, title="[{repo}] TASK-1 코드 리뷰",
        assignee="architect", workspace="worktree", tag="review",
        parent_stages=[14], is_review_gate=True,
        skills=["github-code-review", "requesting-code-review"],
        body_template=_body("""## 작업
TASK-1 구현을 리뷰하고 통과/미통과 판단.

## 단계
1. `kanban_show()` → stage 13 metadata.changed_files 확인
2. 변경 파일 1개를 `head -n 100`
3. `head -n 20 {session_path}/test_result_1.txt`
4. `git -C {session_path}/project diff develop -- <file> | head -n 80`

## 리뷰 기준
- 스타일/네이밍 일관성
- 수용 기준 충족
- 회귀 없음

## 완료 (통과)
kanban_complete(
    summary="LGTM TASK-1: <한 줄 사유>",
    metadata={{"approved": true, "task_id_local": "TASK-1"}}
)

## 막힐 때 (미통과)
kanban_block(reason="review-required: <어떤 파일/어떤 줄/왜>")
"""),
    ),

    # ── TASK-2: impl → test → review (16-18) ─────────────────────────────
    StageTask(
        stage=16, title="[{repo}] TASK-2 구현",
        assignee="executor", workspace="worktree", tag="implementation",
        parent_stages=[15],
        skills=["test-driven-development", "systematic-debugging"],
        body_template=_body("""## 작업
improvements_v0.0.1.md 의 **TASK-2 만** 구현. TASK-1 영역은 건드리지 말 것.

## 단계
1. `head -n 40 {session_path}/improvements_v0.0.1.md` → TASK-2 섹션 파악
2. TASK-2 대상 파일을 `head -n 80` 으로 읽기 (1개만)
3. edit / write 툴로 최소 수정
4. `git status | head -n 10` 확인 (TASK-1 의 commit 은 아직 안 했으니 같이 잡힘 — 정상)

## 완료
kanban_complete(
    summary="TASK-2 구현 완료 — <한 줄 요약>",
    metadata={{"task_id_local": "TASK-2",
               "changed_files": ["<파일경로>"],
               "clone_path": "{session_path}/project"}}
)

## 막힐 때
kanban_block(reason="review-required: <구체적 이유>")
"""),
    ),

    StageTask(
        stage=17, title="[{repo}] TASK-2 테스트",
        assignee="executor", workspace="worktree", tag="implementation",
        parent_stages=[16],
        skills=["test-driven-development", "systematic-debugging"],
        body_template=_body("""## 작업
TASK-2 의 자동 테스트 실행 (마지막 20줄만).

## 단계
1. `cd {session_path}/project`
2. `npm test 2>&1 | tail -n 20` / `pytest -q 2>&1 | tail -n 20` / `go test ./... 2>&1 | tail -n 20`
3. 결과 tail 20줄을 `{session_path}/test_result_2.txt` 에 저장

## 완료 (통과)
kanban_complete(
    summary="TASK-2 테스트 통과",
    metadata={{"file": "{session_path}/test_result_2.txt",
               "task_id_local": "TASK-2",
               "test_result": "passed"}}
)

## 막힐 때 (실패)
kanban_block(reason="TASK-2 테스트 실패: <에러 1줄>")
"""),
    ),

    StageTask(
        stage=18, title="[{repo}] TASK-2 코드 리뷰",
        assignee="architect", workspace="worktree", tag="review",
        parent_stages=[17], is_review_gate=True,
        skills=["github-code-review", "requesting-code-review"],
        body_template=_body("""## 작업
TASK-2 구현 리뷰. 통과/미통과 판단.

## 단계
1. `kanban_show()` → stage 16 metadata.changed_files
2. 변경 파일 1개를 `head -n 100`
3. `head -n 20 {session_path}/test_result_2.txt`

## 완료 (통과)
kanban_complete(
    summary="LGTM TASK-2: <한 줄 사유>",
    metadata={{"approved": true, "task_id_local": "TASK-2"}}
)

## 막힐 때 (미통과)
kanban_block(reason="review-required: <피드백>")
"""),
    ),

    # ── 커밋 + PR (19-21) ────────────────────────────────────────────────
    StageTask(
        stage=19, title="[{repo}] 변경사항 커밋",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[18],
        skills=["github-pr-workflow"],
        body_template=_body("""## 작업
TASK-1 + TASK-2 변경을 로컬 커밋. (DEV_BOOTH_DRYRUN=1 이면 push --dry-run)

## 단계
1. `cd {session_path}/project && git status | head -n 20`
2. `git add -A` (stage 13, 16 의 changed_files 모두 포함)
3. `git commit -m "feat: devbooth improvements [{session}]"`
4. dryrun: `git push --dry-run origin feature/devbooth-{session}-improvements`
   live: 위에서 `--dry-run` 제거
5. `git log -1 --oneline | head -n 1`

## 완료
kanban_complete(
    summary="커밋 완료: <첫 줄 요약>",
    metadata={{"commit_sha": "<git log -1 --format=%H | head -c 12>",
               "branch": "feature/devbooth-{session}-improvements"}}
)
"""),
    ),

    StageTask(
        stage=20, title="[{repo}] PR 초안 작성",
        assignee="conductor", workspace="worktree", tag="pr",
        parent_stages=[19],
        skills=["github-pr-workflow", "writing-plans"],
        body_template=_body("""## 작업
PR 초안 작성. summary_v1.0.0.md 만 head -n 30.

## 단계
1. `head -n 30 {session_path}/summary_v1.0.0.md`
2. `kanban_show()` → stage 19 metadata.commit_sha
3. `{session_path}/pr_draft.json` 에 JSON 저장:
```
{{
  "title": "[Dev-Booth] {goal}",
  "body":  "## 변경사항\\n...\\n## 테스트\\n...",
  "head":  "CrownClownCrowd:feature/devbooth-{session}-improvements",
  "base":  "main",
  "url":   "DRYRUN://no-pr"
}}
```

## 완료
kanban_complete(
    summary="PR 초안 작성 완료",
    metadata={{"draft_file": "{session_path}/pr_draft.json",
               "title": "[Dev-Booth] {goal}"}}
)
"""),
    ),

    StageTask(
        stage=21, title="[{repo}] PR 제출",
        assignee="conductor", workspace="worktree", tag="pr",
        parent_stages=[20],
        skills=["github-pr-workflow"],
        body_template=_body("""## 작업
PR 제출 (dryrun 이면 시뮬레이션만).

## 단계 (DEV_BOOTH_DRYRUN=1)
1. `cp {session_path}/pr_draft.json {session_path}/pr_final.json`
2. pr_final.json 의 url 을 "DRYRUN://no-pr" 로 보장

## 단계 (live)
1. `gh pr create --repo mooner92/{repo} --base main --head CrownClownCrowd:feature/devbooth-{session}-improvements -t "<title>" -b "<body>"`
2. 반환 URL 을 `{session_path}/pr_final.json` 에 기록

## 완료
kanban_complete(
    summary="PR 제출 처리 완료 (dryrun=<true/false>)",
    metadata={{"final_file": "{session_path}/pr_final.json",
               "pr_url": "<DRYRUN://no-pr 또는 실제 URL>"}}
)
"""),
    ),
]


def get_stage(n: int) -> Optional[StageTask]:
    """Return the StageTask for stage number ``n``, or None."""
    return next((s for s in STAGE_DAG if s.stage == n), None)


def format_task(stage: StageTask, **kwargs) -> dict:
    """Render a StageTask into ``hermes kanban create`` parameters."""
    body = stage.body_template.format(**kwargs)
    if stage.skills:
        lines = ["", "## 활용 가능한 스킬 (필요 시 로드)"]
        for name in stage.skills:
            use = SKILL_USE_CASES.get(name, "")
            lines.append(f"- `{name}` — {use}")
        body = body + "\n".join(lines) + "\n"
    return {
        "title": stage.title.format(**kwargs),
        "assignee": stage.assignee,
        "workspace": stage.workspace,
        "tag": stage.tag,
        "body": body,
    }
