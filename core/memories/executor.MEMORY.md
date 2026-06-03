# Dev-Booth Executor 운영 메모

## 서버 환경
- LLM: Qwen2.5-Coder-32B @ http://localhost:8003/v1 (max_model_len 32K)
- 워크스페이스 env: $HERMES_KANBAN_WORKSPACE
- 레포 클론 경로: 부모 태스크 metadata.clone_path 확인 (kanban_show)
- 의존성 분석 저장: /dev-booth/sessions/{session}/analysis_executor.md
- 개선안 파일: /dev-booth/sessions/{session}/improvements_v0.0.1.md

## 내 역할
- dependency analysis: codebase-inspection 스킬 사용
- implementation: test-driven-development / systematic-debugging / subagent-driven-development 스킬 사용
- 구현 완료 후 반드시 테스트 실행 — 테스트 없는 구현은 완성 아님
- 로컬 git commit 은 하되 git push 는 하지 않음 (Conductor 가 push 담당)

## Kanban 규칙 (필수)
- 시작: kanban_show() 로 현재 + 부모 태스크의 summary/metadata 확인
- 완료: kanban_complete(summary="...", metadata={"changed_files":[...],"test_result":"passed"})
- 막힘: kanban_comment("@architect: 질문") → kanban_block(reason="review-required: ...")
- 팀 공지: kanban_comment("▶/✅/⚠️ ...") — 상태 전환 순간에만

## 컨텍스트 절약
- npm install / pip install 출력은 tail -n 20 만 확인
- 테스트 결과는 실패한 케이스만 자세히 확인
- 파일은 필요한 함수 부분만 read (전체 읽기 금지)
- 터미널 출력: RTK 자동 압축

## Dryrun 규칙
- DEV_BOOTH_DRYRUN=1 일 때 git push 는 --dry-run
