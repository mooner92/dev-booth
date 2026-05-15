# Dev-Booth Conductor 운영 메모

## 서버 환경
- 서버: data05lx (Ubuntu 24.04)
- LLM: Qwen2.5-Coder-32B @ http://localhost:8003/v1 (vLLM, max_model_len 32K)
- 세션 루트: /dev-booth/sessions/{session_name}/
- 레포 클론 경로: /dev-booth/sessions/{session_name}/project/
- worktrees: ~/.worktrees/{task_id}/  또는  ~/.hermes/kanban/boards/<slug>/workspaces/<task_id>/
- 워크스페이스 env: $HERMES_KANBAN_WORKSPACE

## GitHub 설정
- Bot 계정: CrownClownCrowd
- 원본 소유자: mooner92
- GITHUB_TOKEN: 환경변수 (DEV_BOOTH_DRYRUN=1 일 때 스크럽됨)
- Dryrun: git push → --dry-run, gh pr create → pr_draft.json 저장만

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
