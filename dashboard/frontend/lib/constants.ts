// Mirror of backend/config.py for shared frontend usage.
// Keep in sync; production code should fetch dynamic values from /api when possible.

export const SCROLL_ANCHOR_THRESHOLD_PX = 80;
export const CHAT_VIRTUAL_ROW_HEIGHT = 80;
export const LOG_PAGE_SIZE = 200;

export const WS_HEARTBEAT_INTERVAL_S = 20;
export const WS_IDLE_TIMEOUT_S = 60;
export const WS_RECONNECT_BACKOFF_MS = [500, 1000, 2000, 4000, 8000] as const;

export const AGENTS = ["conductor", "architect", "executor"] as const;
export const AGENT_COLORS: Record<string, string> = {
  conductor: "#FF4136",
  "architect": "#0070F3",
  "executor": "#00B493",
  system: "#6B7280",
};
export const AGENT_LABELS: Record<string, string> = {
  conductor: "Conductor",
  "architect": "Architect",
  "executor": "Executor",
};
export const AGENT_INITIALS: Record<string, string> = {
  conductor: "CD",
  "architect": "AR",
  "executor": "EX",
};

export const STAGE_LABELS: Record<string, string> = {
  repo_clone: "저장소 클론",
  initial_scan: "초기 분석",
  plan_drafted: "계획 초안",
  plan_approved: "계획 승인",
  implementation: "구현",
  self_review: "자체 리뷰",
  tests_running: "테스트 실행",
  tests_passed: "테스트 통과",
  pr_drafted: "PR 초안",
  pr_review: "PR 리뷰",
  pr_approved: "PR 승인",
  pr_merged: "머지 완료",
};

export const STAGE_ORDER = [
  "repo_clone",
  "initial_scan",
  "plan_drafted",
  "plan_approved",
  "implementation",
  "self_review",
  "tests_running",
  "tests_passed",
  "pr_drafted",
  "pr_review",
  "pr_approved",
  "pr_merged",
];

export const SESSION_STATE_LABELS: Record<string, string> = {
  running: "실행 중",
  idle: "대기 중",
  error: "오류",
  unknown: "미상",
};
