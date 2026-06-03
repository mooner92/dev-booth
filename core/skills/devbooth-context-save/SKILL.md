---
name: devbooth-context-save
description: >
  Dev-Booth 세션에서 발견한 중요한 사항을 MEMORY.md 에 저장하는 절차.
  "기억해줘", "저장해줘", "다음에도 필요한 정보", "memory" 컨텍스트에서 활성화.
version: 1.0.0
author: mooner92
metadata:
  hermes:
    tags: [dev-booth, memory, learning, persistence]
    related_skills: [devbooth-session-start, devbooth-task-complete]
---

# 컨텍스트 저장 절차

MEMORY.md (2200 자 제한) 는 모든 태스크 시작 시 자동 주입됩니다. 따라서
**여러 세션에서 재사용할 발견사항**만 신중하게 추가합니다.

## 추가해야 할 정보

- 레포별 특이사항 ("firebase-chat-exp 는 npm install 후 .env.example 복사 필요")
- 실패한 접근법과 그 이유 ("gh repo fork 는 CrownClownCrowd 권한 없어서 실패 — gh api 로 직접 호출")
- 성공한 패턴 ("clone_path 는 /dev-booth/sessions/<session>/project — 항상 동일")
- 비정상 환경 ("vLLM 가 8003 대신 8000 으로 떠 있을 때는 config.yaml model.base_url 확인")

## 추가하지 말 것 (noise)

- 일회성 에러 메시지
- 쉽게 재발견 가능한 정보 (path, command help)
- 원시 데이터 덤프
- 한 번만 사용한 임시 정보

## MEMORY.md 갱신 형식

작업 중 MEMORY.md 를 직접 편집할 수 있는 권한이 있을 때:

```python
# 1) 현재 MEMORY.md read
# 2) 새 발견을 적절한 섹션에 한 줄 추가
# 3) 2200 바이트 cap 확인 — 초과하면 가장 오래된 / 가장 덜 중요한 줄 삭제
# 4) write 후 wc -c 로 cap 확인
```

권한이 없거나 시간이 부족하면 `kanban_comment("📝 MEMORY 후보: <한 줄 발견>")`
로 운영자에게 위임합니다.

## 형식 예

```
- "firebase-chat-exp: tests 디렉터리에 setup.test.js 추가 필요 (jest 가 픽업)."
- "executor 가 large file 분석 시 head -n 200 으로 충분."
- "gh pr create 는 dryrun 시 pr_draft.json 만 — 실제 호출 금지."
```

각 줄은 ≤ 100 자, 핵심만.

## 안전 가이드

- MEMORY.md 는 모든 세션에서 공유됨 — 세션별 비밀이나 개인정보 절대 금지
- 보안 토큰 (GITHUB_TOKEN 값 등) 절대 저장 금지
- 변경 후 한 번 read 로 형식 확인
