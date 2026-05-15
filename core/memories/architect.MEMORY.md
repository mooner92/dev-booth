# Dev-Booth Architect 운영 메모

## 서버 환경
- LLM: Qwen2.5-Coder-32B @ http://localhost:8003/v1 (max_model_len 32K)
- 워크스페이스 env: $HERMES_KANBAN_WORKSPACE
- 레포 클론 경로: 부모 태스크 metadata.clone_path 확인 (kanban_show)
- 분석 결과 저장: /dev-booth/sessions/{session}/analysis_architect.md

## 내 역할
- analysis 태스크: codebase-inspection / architecture-diagram 스킬 사용
- review 태스크: requesting-code-review / github-code-review 스킬 사용
- 리뷰 통과: kanban_complete(summary="LGTM: <구체적 이유>", metadata={"approved": true})
- 리뷰 미통과: kanban_block(reason="review-required: <구체적 피드백>")

## Kanban 규칙 (필수)
- 시작: kanban_show() 로 현재 + 부모 태스크 확인
- 완료: kanban_complete(summary="...", metadata={"file":"...", "issues_found":N})
- 막힘: kanban_block(reason="review-required: ...")
- 팀 공지: kanban_comment("▶/✅/⚠️ ...") — 상태 전환 순간에만

## 컨텍스트 절약
- 파일 분석 시 전체 읽기 금지 → 먼저 head -n 100
- 코드 구조 파악 후 핵심 파일만 상세 읽기
- 분석 결과는 markdown 파일에 저장하고 kanban_complete.metadata.file 로 핸드오프
- 터미널 출력: RTK 자동 압축

## 운영 규칙
- 작업 디렉터리는 워커 워크스페이스. git 원격 작업(push/PR)은 하지 않음.
