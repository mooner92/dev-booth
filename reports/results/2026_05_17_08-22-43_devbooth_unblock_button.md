# Dev-Booth Unblock 버튼

**Date:** 2026-05-17
**Branch:** `feat/kanban-redesign-2026-05-14`
**Goal:** 차단된 태스크 원클릭 재시작 (사이드바 ping + 채팅 상단 배너 + 헤더 벌크 버튼)
**Result:** ✅ pytest 242/242 (+3 신규), tsc 0 errors, build OK

---

## 1. 변경 요약

| 영역 | 파일 | 변경 |
|------|------|------|
| Backend route  | `dashboard/backend/routers/kanban.py` | `POST /api/kanban/boards/{slug}/tasks/{id}/unblock` — `hermes kanban unblock` 호출, returncode/timeout/FileNotFoundError 분기 |
| Backend test   | `dashboard/backend/tests/test_unblock.py` (신규) | success/failure/timeout 3 케이스 (subprocess.run mock) |
| Frontend API   | `dashboard/frontend/lib/api.ts` | `api.unblockTask(boardSlug, taskId)` — 기존 `apiPost<T>` 헬퍼 재사용 |
| Frontend cmpt  | `dashboard/frontend/components/UnblockBanner.tsx` (신규) | loading→done 상태 머신, error 표시, 🔓 재시작 버튼 |
| Frontend integ | `dashboard/frontend/components/SessionDetailClient.tsx` | blocked 태스크 선택 시 ChatStream 위 배너 + 헤더에 벌크 "차단 N개 재시작" 버튼 |
| Frontend ux    | `dashboard/frontend/components/KanbanBoard.tsx` | blocked StatusIcon 에 `animate-ping` amber halo 추가 |

---

## 2. 동작 검증

### pytest
```
$ pytest tests/ dashboard/backend/tests/ -q
.........................................................................
.........................................................................
.........................................................................
..........................                                       [100%]
242 passed in 0.94s
```
(기존 239 + 신규 3 = 242)

### 신규 테스트만 분리 실행
```
$ pytest dashboard/backend/tests/test_unblock.py -q
...                                                              [100%]
3 passed in 0.36s
```

### tsc
```
$ npx tsc --noEmit
exit 0 (출력 없음)
```

### build
```
$ npm run build
✓ Compiled successfully
○ /                                  16.1 kB         124 kB
● /session/[name]                    112 kB          221 kB   ← +1 kB (UnblockBanner)
○ /village                           1.42 kB         95.5 kB
```

---

## 3. UI 동작

| 상태 | 사이드바 (KanbanBoard) | 헤더 | 채팅 영역 |
|------|------------------------|------|-----------|
| blocked 태스크 0개 | (변화 없음) | 일반 헤더 | 일반 ChatStream |
| blocked 태스크 N개 (선택 안 함) | ⊘ 깜빡임 (amber ping) | `⊘ 차단 N개 재시작` 버튼 표시 | 일반 ChatStream |
| blocked 태스크 선택 | ⊘ 깜빡임 + 선택 강조 | 위와 동일 | **🔓 재시작 배너** + ChatStream |
| 재시작 클릭 → 성공 | (WS push로 곧 ✓ 로 갱신) | (벌크 버튼 자동 사라짐) | ✅ 재시작됨 배너 |
| 재시작 클릭 → 실패 | (그대로) | (그대로) | 빨간색 error 메시지 + 버튼 활성화 |

---

## 4. 운영자 후속 작업 (sudo 필요)

```bash
sudo systemctl restart dev-booth-dashboard
```
이유: 새 `POST .../unblock` 라우트는 backend 재시작이 필요.
프론트엔드 정적 산출물은 `dashboard/frontend/out/` 에 빌드 완료되어 다음 정적 요청부터 새 SessionDetailClient/KanbanBoard 가 서빙됨.

push:
```bash
git push origin feat/kanban-redesign-2026-05-14
```
(Ralph 는 자동 push 하지 않음 — 사용자 명시 승인이 있을 때만)

---

## 5. 금지 사항 준수

- ✅ 기존 API 시그니처 미변경 (신규 라우트만 추가)
- ✅ main 브랜치 미수정 (`feat/kanban-redesign-2026-05-14` 유지)
- ✅ 파일 읽기 head/grep 으로 제한
- ✅ sudo 필요 작업은 §4 운영자 TODO 로 분리
- ✅ 보고서 파일명 콜론 없음 (`2026_05_17_08-22-43_devbooth_unblock_button.md`)
