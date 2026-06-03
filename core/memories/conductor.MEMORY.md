# Dev-Booth Conductor 운영 메모

## 서버 환경
- 서버: data05lx (Ubuntu 24.04)
- LLM: Qwen2.5-Coder-32B @ http://localhost:8003/v1 (vLLM, max_model_len 32K)
- 세션 루트: /dev-booth/sessions/{session_name}/
- 레포 클론 경로: /dev-booth/sessions/{session_name}/project/
- worktrees: ~/.worktrees/{task_id}/  또는  ~/.hermes/kanban/boards/<slug>/workspaces/<task_id>/
- 워크스페이스 env: $HERMES_KANBAN_WORKSPACE

## GitHub 설정
- Bot 계정: CrownClownCrowd (모든 git/gh 작업은 이 계정으로; `gh auth status` 에서 active=CrownClownCrowd)
- 원본 소유자(upstream): 세션 `repo_url` 에서 추출 (`{repo_owner}`) — mooner92 하드코딩 금지
- git --global identity: CrownClownCrowd / 283567286+CrownClownCrowd@users.noreply.github.com
- `gh repo fork` 는 이미 fork 가 있을 수 있으므로 `gh repo view ... >/dev/null 2>&1 || gh repo fork ...` 멱등 패턴 사용

## Kanban 규칙 (필수)
- 담당 프로필: conductor(자신), architect, executor (다른 이름은 dispatcher가 무시)
- 작업 시작: kanban_show() 로 부모 metadata 의 clone_path 확인
- 완료 시 반드시: kanban_complete(summary="...", metadata={...}) — 없으면 protocol_violation
- 막힐 때: kanban_block(reason="...")
- 팀 공지: kanban_comment("▶/✅/⚠️/📋 ...") — 상태 전환 순간에만

## 컨텍스트 절약
- 터미널 출력: RTK 가 자동 압축 (60-90% 감소)
- max_turns 15, context_length 28000 (v5 envelope)
- 긴 파일은 head/tail 로 필요한 부분만 — 전체 read 금지
