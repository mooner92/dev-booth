"""Dev-Booth 12-stage scenario — the domain layer, surgically extracted from the
v1 stateless orchestrator (archive/v1-stateless-orchestrator/orchestrator.py).

This module is pure data + formatting. It does NOT run agents. ``core/session.py``
seeds this DAG onto a Hermes Kanban board; the gateway dispatcher then spawns the
assigned profiles as workers.

Kept from v1 (P3 — reuse the tested domain layer):
  * STAGE_NARRATION — the canonical narration corpus (carries stage_mapper
    keywords so the dashboard derives a monotonic 12->~8 stage progression).
  * the assignee mapping (openclaw / hermes-a / hermes-b).
  * the dryrun policy (DEV_BOOTH_DRYRUN, default on).

Retired from v1: the hermes -z per-turn execution loop, the MessageQueue
mediation, strand recovery, reply draining — Hermes Kanban does all of that.

DD5/§7 of plan v4: STAGE_NARRATION bodies must each carry their stage's
stage_mapper keyword and must NOT trip a *higher* stage's keyword than the next
DAG stage — verified monotonic non-decreasing by the cross-seam test
(dashboard/backend/tests/test_stage_narration_crossseam.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------
# Canonical narration corpus — one line per scenario stage. Each line contains
# the dashboard stage_mapper keyword(s) for the stage it represents; the
# sequence of detect_stage() results across 1..12 is monotonic non-decreasing.
# --------------------------------------------------------------------------
STAGE_NARRATION: dict[int, str] = {
    1:  "git clone: 레포지토리 포킹 및 클론 시작",
    2:  "initial scan: 프로젝트 초기 분석 시작",
    3:  "initial scan: 코드 구조 분석 중 (Hermes-A)",
    4:  "initial scan: 의존성 분석 중 (Hermes-B)",
    5:  "initial scan: 분석 취합 및 요약 작성",
    6:  "drafting the implementation plan: 개선방안 계획 수립",
    7:  "plan approved: 개발 계획 승인, feature 브랜치 생성",
    8:  "implementing: 개발 루프 시작",
    9:  "running tests: 자동 테스트 실행",
    10: "tests passed: 테스트 통과, 커밋 준비",
    11: "pr drafted: PR 초안 작성",
    12: "pr merged: PR 제출 완료",
}

# The three real Hermes profiles the dispatcher can spawn. A task assigned to
# any other name sits in `ready` forever (the dispatcher silently does not
# spawn unknown assignees) — core/session.py validates against this set.
ALLOWED_ASSIGNEES: frozenset[str] = frozenset({"openclaw", "hermes-a", "hermes-b"})


@dataclass
class StageTask:
    """One node of the static 12-stage DAG."""

    stage: int
    title: str
    assignee: str          # openclaw / hermes-a / hermes-b
    workspace: str         # worktree / dir:<path> / scratch
    tag: str               # orchestration / analysis / implementation / review / pr
    body_template: str
    parent_stages: list[int] = field(default_factory=list)
    is_review_gate: bool = False  # True -> `blocked` is an expected terminal state


# --------------------------------------------------------------------------
# The static 12-stage DAG. Stages 6 & 8 are *statically pre-decomposed* here —
# autonomous kanban_create fan-out is integration-test-only and off the e2e
# critical path (plan v4 ADR-001 / scope honesty).
# --------------------------------------------------------------------------
STAGE_DAG: list[StageTask] = [
    StageTask(
        stage=1, title="[{repo}] fork & clone",
        assignee="openclaw", workspace="worktree", tag="orchestration",
        body_template="""레포지토리를 fork하고 clone하세요.

레포: {repo_url}
Bot 계정: CrownClownCrowd (GITHUB_TOKEN 환경변수 사용)
원본 소유자: mooner92
목표: {goal}

clone 직후 반드시 dryrun 안전 훅을 설치하세요 (clone 경로를 인자로):
    bash /dev-booth/core/dryrun/install_hooks.sh <clone_path>
이 pre-push 훅이 DEV_BOOTH_DRYRUN=1 일 때 실제 push를 차단합니다.

완료 시:
- kanban_complete() 호출
- summary에 clone 경로 포함
- metadata: {{"repo_name": "...", "clone_path": "...", "branch": "develop"}}
"""),
    StageTask(
        stage=2, title="[{repo}] initial project scan",
        assignee="openclaw", workspace="worktree", tag="orchestration",
        parent_stages=[1],
        body_template="""클론된 레포를 초기 스캔하세요.

완료 후 Hermes-A에게 코드 구조 분석 태스크,
Hermes-B에게 의존성 분석 태스크를 kanban_create()로 생성하세요.
각 태스크에 --parent 현재 태스크 ID를 설정하세요.
"""),
    StageTask(
        stage=3, title="[{repo}] code structure analysis",
        assignee="hermes-a", workspace="worktree", tag="analysis",
        parent_stages=[2],
        body_template="""코드 구조와 아키텍처를 분석하세요.

분석 항목:
- 디렉터리 구조 및 모듈 설계
- 핵심 클래스/함수 파악
- 코드 품질 이슈 (중복, 복잡도, 미사용 코드)
- 개선 가능한 아키텍처 포인트

결과를 /dev-booth/sessions/{session}/analysis_hermes_a.md 에 저장하세요.
완료 시 kanban_complete()에 findings 포함:
metadata: {{"file": "analysis_hermes_a.md", "issues_found": N}}
"""),
    StageTask(
        stage=4, title="[{repo}] dependency & tech stack analysis",
        assignee="hermes-b", workspace="worktree", tag="analysis",
        parent_stages=[2],
        body_template="""의존성과 기술 스택을 분석하세요.

분석 항목:
- package.json / requirements.txt / go.mod 등 의존성
- 오래된 패키지, 보안 취약점
- 테스트 커버리지 현황
- CI/CD 설정

결과를 /dev-booth/sessions/{session}/analysis_hermes_b.md 에 저장하세요.
완료 시 kanban_complete()에 findings 포함.
"""),
    StageTask(
        stage=5, title="[{repo}] analysis summary",
        assignee="openclaw", workspace="worktree", tag="orchestration",
        parent_stages=[3, 4],
        body_template="""Hermes-A와 Hermes-B의 분석 결과를 취합하여
/dev-booth/sessions/{session}/summary_v1.0.0.md 를 작성하세요.

부모 태스크의 kanban_show()로 findings를 읽어서 종합하세요.
"""),
    StageTask(
        stage=6, title="[{repo}] improvements plan",
        assignee="openclaw", workspace="worktree", tag="orchestration",
        parent_stages=[5],
        body_template="""summary를 바탕으로 개선방안을 작성하세요.
(Hermes-A, Hermes-B와 kanban_comment()로 의견 교환 후 확정)

/dev-booth/sessions/{session}/improvements_v0.0.1.md 작성:
- TASK 목록 (각 TASK에 담당자, 예상 파일, 설명 포함)
- 우선순위 순서

완료 시 kanban_complete() 호출.
"""),
    StageTask(
        stage=7, title="[{repo}] create feature branch",
        assignee="openclaw", workspace="worktree", tag="orchestration",
        parent_stages=[6],
        body_template="""feature 브랜치를 생성하세요.
브랜치명: feature/devbooth-{session}-improvements

DEV_BOOTH_DRYRUN=1 이면 git push에 --dry-run 옵션 사용.
"""),
    StageTask(
        stage=8, title="[{repo}] implement TASK-{n}",
        assignee="hermes-b", workspace="worktree", tag="implementation",
        parent_stages=[7],
        body_template="""improvements_v0.0.1.md 의 TASK-{n}을 구현하세요.

구현 완료 후:
1. 자동 테스트 실행 (npm test / pytest / 해당 프레임워크)
2. 테스트 통과 시 kanban_complete()
3. 테스트 실패 시 수정 후 재시도 (최대 3회)
4. 해결 불가 시 kanban_block("review-required: ...")

metadata: {{"changed_files": [...], "test_result": "passed/failed"}}
"""),
    StageTask(
        stage=9, title="[{repo}] code review TASK-{n}",
        assignee="hermes-a", workspace="worktree", tag="review",
        parent_stages=[8], is_review_gate=True,
        body_template="""Hermes-B의 구현을 리뷰하세요.

리뷰 기준:
- 기존 코드 스타일 준수
- 테스트 커버리지
- 성능/보안 이슈
- improvements 계획과의 일치

통과: kanban_complete(summary="LGTM: ...")
미통과: kanban_block("review-required: 구체적 피드백")
"""),
    StageTask(
        stage=10, title="[{repo}] commit approved changes",
        assignee="openclaw", workspace="worktree", tag="orchestration",
        parent_stages=[9],
        body_template="""리뷰 통과된 변경사항을 커밋하세요.
커밋 메시지: "feat: {task_description} [devbooth/{session}]"

DEV_BOOTH_DRYRUN=1 이면 커밋만, push는 --dry-run.
"""),
    StageTask(
        stage=11, title="[{repo}] draft PR",
        assignee="openclaw", workspace="worktree", tag="pr",
        parent_stages=[10],
        body_template="""PR을 작성하세요.

PR 제목: "[Dev-Booth] {goal}"
PR 본문: 변경사항 요약, 테스트 결과, 주요 파일 목록

DEV_BOOTH_DRYRUN=1 이면 /dev-booth/sessions/{session}/pr_draft.json 저장.
실제 실행 시 gh pr create 사용.
"""),
    StageTask(
        stage=12, title="[{repo}] submit PR",
        assignee="openclaw", workspace="worktree", tag="pr",
        parent_stages=[11],
        body_template="""CrownClownCrowd → mooner92 PR을 제출하세요.

DEV_BOOTH_DRYRUN=1 이면 pr_draft.json 에 url: "DRYRUN://no-pr" 기록.
실제 실행 시 gh pr create --repo mooner92/{repo}.

kanban_complete() 후 세션 완료 처리.
"""),
]


def get_stage(n: int) -> Optional[StageTask]:
    """Return the StageTask for stage number ``n`` (1-12), or None."""
    return next((s for s in STAGE_DAG if s.stage == n), None)


def format_task(stage: StageTask, **kwargs) -> dict:
    """Render a StageTask into ``hermes kanban create`` parameters."""
    return {
        "title": stage.title.format(**kwargs),
        "assignee": stage.assignee,
        "workspace": stage.workspace,
        "tag": stage.tag,
        "body": stage.body_template.format(**kwargs),
    }
