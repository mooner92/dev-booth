---
name: devbooth-session-start
description: >
  Dev-Booth Kanban 태스크를 시작할 때 활성화. 워크스페이스 확인, 부모 태스크
  metadata 로드, 팀 공지 kanban_comment 전송까지 표준 시작 절차를 안내한다.
  "kanban task 시작", "작업 시작", "Dev-Booth 태스크" 같은 컨텍스트에서 활성화.
version: 1.0.0
author: mooner92
metadata:
  hermes:
    tags: [dev-booth, kanban, lifecycle, start]
    related_skills: [devbooth-task-complete, kanban-worker]
---

# Dev-Booth 태스크 시작 표준 절차

당신은 Dev-Booth 의 Kanban 워커입니다. 새 태스크를 받았을 때 이 스킬이 안내하는
4단계를 순서대로 수행합니다.

## 1. 태스크 정보 확인
`kanban_show()` 를 호출하여 현재 태스크 body 와 부모 태스크의 summary/metadata
를 확인합니다.

특히 반드시 확인:
- `clone_path`: 레포가 클론된 절대 경로
- `session`: 세션 이름 (파일 저장 경로에 사용됨)
- 부모 태스크의 findings / results / changed_files / commit_sha 등 핸드오프 데이터

## 2. 팀 공지

```
kanban_comment("▶ <태스크 제목> 작업을 시작합니다.")
```

작업이 길어질 것 같으면 예상 단계도 한 줄 덧붙입니다.

## 3. 워크스페이스 확인

```bash
echo "$HERMES_KANBAN_WORKSPACE"   # 현재 작업 디렉터리
pwd                                # 안전 확인
```

`$HERMES_KANBAN_WORKSPACE` 가 비어있다면 dispatcher 가 env 를 주입하지 못한 것이므로
즉시 `kanban_block(reason="workspace-env-missing")` 으로 멈춥니다.

## 4. 컨텍스트 절약 원칙 (필수)

- 파일 전체 읽기 금지 → 먼저 `head -n 50` / `head -n 100`
- 긴 명령어 출력은 `tail -n 20` 으로 확인
- npm install / pip install 출력은 마지막 success/error 줄만 확인
- 같은 파일을 두 번 read 하지 않기 (변수에 저장하거나 metadata 활용)

RTK 가 자동으로 터미널 출력을 압축 중이지만, 입력 컨텍스트도 절약해야
max_turns 15 한도 안에서 완주합니다.

## 다음 단계

이 4단계가 끝나면 본격적인 작업을 시작합니다. 작업이 끝나면
`devbooth-task-complete` 스킬을 참고하여 `kanban_complete()` 를 호출합니다.
