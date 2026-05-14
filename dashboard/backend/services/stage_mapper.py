"""Stage mapper per plan ADR-004 (C1).

Detects which of the 12 pipeline stages a message body belongs to using:

1. NFC Unicode normalization (Korean + English mixed).
2. Regex patterns with word-boundary semantics on the ASCII side and
   lookbehind/lookahead on non-CJK boundaries for Korean.
3. Conflict resolution: within a sliding 60-second window the
   *highest-stage-wins* (the pipeline only moves forward); outside the window
   it's *latest-wins*. This guards against premature regression when an old
   message arrives late.

The 12 stage keyword table is the source of truth — synonyms are added
liberally because we'd rather a moderate false-positive than miss a stage
entirely (the user can scrub the chat log if needed).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Sequence

from .. import config


# Each entry: (stage_number, stage_id, korean_keywords, english_keywords)
STAGES: list[tuple[int, str, list[str], list[str]]] = [
    (1, "repo_clone",
        ["저장소 클론", "리포지토리 클론", "클론 완료"],
        ["git clone", "repo clone", "cloning repository"]),
    (2, "initial_scan",
        ["초기 분석", "프로젝트 분석을 시작", "프로젝트 스캔", "코드베이스 분석"],
        ["initial scan", "starting analysis", "scanning codebase"]),
    (3, "plan_drafted",
        ["작업 계획", "구현 계획", "계획 초안", "TODO 목록"],
        ["draft plan", "implementation plan", "## TODO", "planning"]),
    (4, "plan_approved",
        ["계획 승인", "승인합니다", "계획에 동의"],
        ["plan approved", "approved the plan", "lgtm plan"]),
    (5, "implementation",
        ["구현 진행", "구현 시작", "코드 작성", "개발 중"],
        ["implementing", "writing code", "building feature", "코드 변경"]),
    (6, "self_review",
        ["자체 리뷰", "셀프 리뷰", "스스로 검토"],
        ["self review", "self-review", "reviewing my own"]),
    (7, "tests_running",
        ["테스트 실행", "테스트 시작", "테스트 돌리는 중"],
        ["running tests", "pytest", "npm test", "test run"]),
    (8, "tests_passed",
        ["테스트 통과", "테스트 성공", "모든 테스트 통과"],
        ["tests passed", "all tests pass", "0 failures"]),
    (9, "pr_drafted",
        ["PR 초안", "풀 리퀘스트 초안", "PR 생성"],
        ["pr drafted", "draft pull request", "gh pr create"]),
    (10, "pr_review",
        ["PR 리뷰", "코드 리뷰 요청"],
        ["pr review", "review requested", "review comments"]),
    (11, "pr_approved",
        ["PR 승인", "리뷰 승인", "머지 가능"],
        ["pr approved", "review approved", "ready to merge"]),
    (12, "pr_merged",
        ["머지 완료", "PR 머지", "병합 완료"],
        ["pr merged", "merged into main", "merged the pr"]),
]


def _make_pattern(keywords: Sequence[str]) -> re.Pattern[str]:
    parts = []
    for kw in keywords:
        # ASCII boundary if all ASCII, otherwise literal substring match
        # (Korean has no \b word boundary).
        if kw.isascii():
            parts.append(rf"\b{re.escape(kw)}\b")
        else:
            parts.append(re.escape(kw))
    return re.compile("|".join(parts), re.IGNORECASE)


_STAGE_PATTERNS: list[tuple[int, str, re.Pattern[str]]] = []
for stage_no, stage_id, ko_kw, en_kw in STAGES:
    keywords = ko_kw + en_kw
    _STAGE_PATTERNS.append((stage_no, stage_id, _make_pattern(keywords)))


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


@dataclass
class StageHit:
    stage: int
    stage_id: str
    ts_ms: int


def detect_stage(body: str) -> Optional[tuple[int, str]]:
    """Return the highest stage whose keywords match in ``body``."""
    text = normalize(body)
    best: Optional[tuple[int, str]] = None
    for stage_no, stage_id, pattern in _STAGE_PATTERNS:
        if pattern.search(text):
            if best is None or stage_no > best[0]:
                best = (stage_no, stage_id)
    return best


class StageTracker:
    """Maintains the current stage across a session, with 60s conflict window."""

    def __init__(self, conflict_window_s: float = config.STAGE_CONFLICT_WINDOW_S):
        self.conflict_window_s = conflict_window_s
        self.hits: list[StageHit] = []

    def observe(self, body: str, ts_ms: int) -> Optional[tuple[int, str]]:
        hit = detect_stage(body)
        if hit:
            self.hits.append(StageHit(stage=hit[0], stage_id=hit[1], ts_ms=ts_ms))
        return self.current(now_ms=ts_ms)

    def current(self, now_ms: Optional[int] = None) -> Optional[tuple[int, str]]:
        if not self.hits:
            return None
        if now_ms is None:
            now_ms = self.hits[-1].ts_ms
        window_ms = int(self.conflict_window_s * 1000)
        recent = [h for h in self.hits if h.ts_ms >= now_ms - window_ms]
        if recent:
            # highest-stage-wins inside the window
            best = max(recent, key=lambda h: h.stage)
            return (best.stage, best.stage_id)
        # outside window: latest-wins
        last = self.hits[-1]
        return (last.stage, last.stage_id)


def stage_ids() -> list[str]:
    return [sid for _, sid, _, _ in STAGES]
