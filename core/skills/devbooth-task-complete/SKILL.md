---
name: devbooth-task-complete
description: >
  Dev-Booth Kanban 태스크 완료 시 활성화. kanban_complete() 호출 전 체크리스트
  확인 및 올바른 metadata 형식 (analysis / implementation / review 별) 을 안내한다.
  "작업 완료", "kanban_complete", "태스크 끝", "LGTM" 컨텍스트에서 활성화.
version: 1.0.0
author: mooner92
metadata:
  hermes:
    tags: [dev-booth, kanban, lifecycle, complete]
    related_skills: [devbooth-session-start, kanban-worker]
---

# Dev-Booth 태스크 완료 체크리스트

`kanban_complete()` 를 호출하기 직전에 이 스킬이 안내하는 절차를 거칩니다.
완료 신호가 빠지면 Hermes 는 그 시도를 `crashed (protocol_violation)` 으로 기록하고
failure_limit:2 회를 초과하면 태스크가 자동으로 `blocked` 됩니다.

## 1. 완료 전 자가 확인

- [ ] 요청된 작업이 *실제로* 완료됐는가? (단순 "맞춰서 끝"은 금지)
- [ ] 산출물 파일이 올바른 절대 경로에 저장됐는가?
- [ ] 테스트가 실제로 통과했는가? (구현 태스크의 경우)
- [ ] 다음 단계 워커가 읽을 정보가 metadata 에 충분히 들어있는가?

체크 항목이 하나라도 미달이면 `kanban_complete()` 대신 `kanban_block(reason="...")`
으로 멈춥니다.

## 2. 팀 공지 (kanban_complete 직전)

```
kanban_comment("✅ <태스크 제목> 완료. 다음 단계: <다음 태스크명 또는 단계 설명>")
```

## 3. kanban_complete 형식 — 태스크 타입별

### 분석 태스크 (architect / executor 의 analysis)

```python
kanban_complete(
    summary="<핵심 발견사항 1~2줄>",
    metadata={
        "file": "/dev-booth/sessions/<session>/analysis_<role>.md",
        "issues_found": N,
        "clone_path": "/dev-booth/sessions/<session>/project"
    }
)
```

### 구현 태스크 (executor 의 implementation)

```python
kanban_complete(
    summary="<구현 내용 1~2줄>",
    metadata={
        "task_id_local": "TASK-<n>",
        "changed_files": ["파일1", "파일2"],
        "test_command": "<예: npm test / pytest -q>",
        "test_result": "passed",
        "clone_path": "/dev-booth/sessions/<session>/project"
    }
)
```

### 리뷰 태스크 (architect) — 통과

```python
kanban_complete(
    summary="LGTM: <구체적 통과 사유>",
    metadata={"approved": true, "review_notes": "<선택적>"}
)
```

### 리뷰 미통과

```python
kanban_block(reason="review-required: <어떤 파일/어떤 줄/왜>")
```

## 4. 금지 사항

- summary 가 "완료" / "끝" 같은 한 단어로만 끝남
- metadata 에 다음 단계가 사용할 키 (clone_path / file / changed_files) 가 없음
- kanban_complete 후 추가 텍스트 작성 (gateway 가 잘라낼 수 있음)
