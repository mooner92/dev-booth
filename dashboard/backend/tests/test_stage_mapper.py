from __future__ import annotations

from dashboard.backend.services import stage_mapper
from dashboard.backend.services.stage_mapper import StageTracker, detect_stage


def test_detect_stage_korean():
    assert detect_stage("프로젝트 분석을 시작해주세요.") == (2, "initial_scan")


def test_detect_stage_english():
    assert detect_stage("Starting analysis of the repository") == (2, "initial_scan")


def test_detect_stage_highest_wins_within_body():
    body = "초기 분석 결과 작업 계획을 작성했습니다."  # both stage 2 and 3
    assert detect_stage(body) == (3, "plan_drafted")


def test_detect_stage_unmatched():
    assert detect_stage("그냥 잡담입니다") is None
    assert detect_stage("") is None


def test_stage_tracker_within_window_uses_highest():
    tracker = StageTracker(conflict_window_s=60.0)
    tracker.observe("프로젝트 분석을 시작", 1000)
    tracker.observe("저장소 클론 완료", 2000)  # stage 1 but later
    current = tracker.current(now_ms=10000)
    # stage 2 (initial_scan) is higher than stage 1 within 60s window
    assert current == (2, "initial_scan")


def test_stage_tracker_outside_window_latest_wins():
    tracker = StageTracker(conflict_window_s=60.0)
    tracker.observe("초기 분석", 1000)
    # 120 seconds later
    tracker.observe("저장소 클론 완료", 121_000)
    current = tracker.current(now_ms=121_000)
    # Latest wins outside the window
    assert current == (1, "repo_clone")


def test_stage_tracker_handles_late_arriving_old_message():
    tracker = StageTracker(conflict_window_s=60.0)
    tracker.observe("PR 머지 완료", 100_000)  # stage 12
    # Late old message arrives 30s later but is timestamped earlier — but we
    # only check ts_ms, so this is treated as observed within the window.
    tracker.observe("프로젝트 분석을 시작", 110_000)  # stage 2
    current = tracker.current(now_ms=130_000)
    # highest within window wins → 12
    assert current == (12, "pr_merged")


def test_golden_fixture_accuracy(tmp_path):
    # Generate a synthetic fixture covering all 12 stages + negatives
    fixture = [
        ("저장소 클론 완료", "repo_clone"),
        ("git clone https://...", "repo_clone"),
        ("초기 분석 결과:", "initial_scan"),
        ("프로젝트 분석을 시작해주세요.", "initial_scan"),
        ("starting analysis of the codebase", "initial_scan"),
        ("작업 계획 초안을 작성합니다.", "plan_drafted"),
        ("## TODO\n- foo", "plan_drafted"),
        ("draft plan ready for review", "plan_drafted"),
        ("계획 승인합니다.", "plan_approved"),
        ("plan approved, proceed", "plan_approved"),
        ("구현 시작", "implementation"),
        ("implementing feature now", "implementation"),
        ("코드 작성 중", "implementation"),
        ("자체 리뷰 결과 양호", "self_review"),
        ("self review complete", "self_review"),
        ("테스트 실행 중", "tests_running"),
        ("running tests now", "tests_running"),
        ("npm test", "tests_running"),
        ("모든 테스트 통과", "tests_passed"),
        ("tests passed: 12/12", "tests_passed"),
        ("PR 초안 작성", "pr_drafted"),
        ("gh pr create --draft", "pr_drafted"),
        ("PR 리뷰 요청", "pr_review"),
        ("review requested", "pr_review"),
        ("PR 승인", "pr_approved"),
        ("review approved, ready to merge", "pr_approved"),
        ("머지 완료", "pr_merged"),
        ("merged into main", "pr_merged"),
        # Negatives (should not match any stage)
        ("잡담입니다", None),
        ("hello world", None),
        ("foo bar baz", None),
    ]
    correct = 0
    total = 0
    for body, expected_id in fixture:
        total += 1
        hit = detect_stage(body)
        actual_id = hit[1] if hit else None
        if actual_id == expected_id:
            correct += 1
    accuracy = correct / total
    assert accuracy >= 0.9, f"stage detection accuracy {accuracy:.2f} below 0.9 ({correct}/{total})"


def test_stage_ids_complete():
    ids = stage_mapper.stage_ids()
    assert len(ids) == 12
    assert ids[0] == "repo_clone"
    assert ids[-1] == "pr_merged"
