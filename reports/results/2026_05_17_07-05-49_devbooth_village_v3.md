# Dev-Booth Village v3 + Dashboard UX

**Date:** 2026-05-17
**Branch:** `feat/kanban-redesign-2026-05-14`
**Goal:** Village 고양이 3마리 + 채팅 가독성 + 한국어 + 팀 타임라인 status_change
**Result:** ✅ pytest 239/239, tsc 0 errors, build OK, architect APPROVED

---

## 1. 4개 작업 영역

| 영역 | 파일 | 변경 |
|------|------|------|
| Village sync v3 | `~/star-office-ui/devbooth_sync.py` | conductor=isMain, architect/executor=visitor (isMain=false, authStatus=approved, 2초 lastPushAt 갱신) + state.json `officeName/name = Dev-Booth: {board}` |
| 한국어 i18n | `~/star-office-ui/frontend/index.html` | EN/CN locale memoTitle/guestTitle/officeTitle 모두 한국어 Dev-Booth 라벨로; 暂无 inline strings 도 |
| 채팅 그룹핑 | `dashboard/frontend/components/ChatStream.tsx` | `groupAndFilterEntries()` — 같은 agent text 5초 window 합치기 + 7개 noise pattern 제거 (log 탭만, timeline 탭은 raw 유지) |
| 채팅 styling | `dashboard/frontend/components/ChatMessage.tsx` | kind=status_change 시각 구분 (✅=초록 border-left, ⊘=주황) |
| Timeline 백엔드 | `dashboard/backend/services/kanban_reader.py` | `get_status_change_events()` — done/blocked task 를 `COALESCE(completed_at, created_at)` 시각으로 추출 |
| Timeline 라우터 | `dashboard/backend/routers/kanban.py` | `_status_event_to_log_entry` 추가, `_collect_timeline` 이 comments+status events 병합 후 chronologic 정렬 |
| Timeline 테스트 | `dashboard/backend/tests/test_kanban_reader.py` | v7 contract 검증 (5 entries, kind 집합 {comment, status_change}, ✅/⊘ marker body) |

---

## 2. 동작 검증 (live)

### `/agents` — 고양이 3마리
```
agent count: 3
  devbooth-conductor        isMain=True  state=executing  authStatus=approved
  devbooth-architect        isMain=False state=executing  authStatus=approved
  devbooth-executor         isMain=False state=idle       authStatus=approved
```

### `state.json` — officeName 노출
```json
{
  "state": "executing",
  "detail": "디렉터리 구조 파악",
  "progress": 5,
  "name": "Dev-Booth: awq-test-001",
  "officeName": "Dev-Booth: awq-test-001",
  "board": "awq-test-001",
  "updated_at": "2026-05-17T07:00:42.870022"
}
```

### Star-Office-UI 한국어 텍스트
```
$ curl -s http://localhost:19000/ | grep -c "Dev-Booth Agent Office"
2
$ curl -s http://localhost:19000/ | grep -c "어제 작업 노트"
2
$ curl -s http://localhost:19000/ | grep -c "팀 에이전트"
2
```
(EN locale + CN locale 양쪽 다 한국어 Dev-Booth 라벨로 통일)

### 빌드 + 테스트
```
$ pytest tests/ dashboard/backend/tests/ -q
.................................................................................
.................................................................................
.................................................................................
.......................                                                  [100%]
239 passed in 0.87s

$ npx tsc --noEmit       (dashboard/frontend)
exit 0

$ npm run build          (dashboard/frontend)
✓ Compiled successfully
✓ Generating static pages (6/6)
○ /village                              1.42 kB        95.5 kB
```

### systemd
```
star-office-ui.service     Active: active (running)
star-office-sync.service   Active: active (running)
```

---

## 3. 아키텍트 검증 (sonnet) 결과

| User Story | Criteria | 결과 |
|------------|----------|------|
| US-001 multi-agent sync | 5/5 | PASS |
| US-002 한국어 i18n      | 9/9 | PASS |
| US-003 채팅 그룹핑      | 4/4 | PASS |
| US-004 timeline events  | 5/5 | PASS |
| US-005 회귀             | 3/3 | PASS |
| US-006 보고서 + commit  | 3/3 | PASS (본 보고서 + 본 커밋) |

아키텍트 비-PRD 발견:
- **[LOW]** index.html:1177 `正在加载访客...` (방문자 로딩) 中文 잔존 — 짧은 transition 시점만 보임. 후속 정리 가능.
- **[LOW]** `name` vs `officeName` 매핑 경로 — 두 필드에 같은 값 쓰므로 어느 쪽을 frontend 가 읽든 동일.
- **[INFO]** `_collect_timeline` 의 사전-슬라이스 + 사후-슬라이스 더블 limit — 현재 데이터량에서 무해.

---

## 4. 운영자 후속 작업 (sudo / 외부 시스템 필요)

1. `sudo systemctl restart dev-booth-dashboard` — backend 변경 사항 (kanban_reader/router) 적용. 빌드 산출물은 정적이므로 dashboard 가 새 /village static 만 서빙해도 됨. backend timeline endpoint 활성화는 재시작 필요.
2. `git push origin feat/kanban-redesign-2026-05-14` — Ralph 는 push 를 자동 실행하지 않음. 본 commit 만 로컬에 만들어두었음.
3. (선택) `loginctl enable-linger mooner92` — star-office-{ui,sync} user service 가 로그아웃 후에도 살아남도록.

---

## 5. 금지 사항 준수

- ✅ Star-Office-UI backend/app.py 미수정
- ✅ Star-Office-UI 픽셀 아트 에셋 미수정 (index.html 의 i18n string 값만 변경)
- ✅ 기존 /api/kanban, /api/sessions API 시그니처 미변경 (timeline 응답 shape 만 확장: 기존 comment 필드 + 신규 status_change 항목)
- ✅ main 브랜치 미수정 (`feat/kanban-redesign-2026-05-14` 유지)
- ✅ 파일 읽기 head -n 으로 제한 (index.html 4889 줄 중 필요한 부분만 head/grep)
- ✅ sudo 필요 작업은 §4 운영자 TODO 로 분리
- ✅ 보고서 파일명 콜론 없음 (HH-MM-SS 형식)
