# Dev-Booth Dryrun 제거 완료 보고서

**날짜:** 2026-05-18 01:26:18
**브랜치:** `feat/kanban-redesign-2026-05-14`
**Result:** ✅ pytest 242/242, tsc 0 errors, build OK

---

## 작업 요약
세션 생성 모달의 드라이런/라이브 모드 선택 UI를 제거하고 항상 라이브 모드로
동작하도록 수정. `DEV_BOOTH_DRYRUN` 환경변수는 더 이상 코드 분기를 가르지 않으며,
`core/dryrun/*` 보호 스크립트들은 git pre-push 훅의 안전망으로만 남는다.

---

## 수정된 파일
| 파일 | 변경 |
|---|---|
| `core/session.py` | `DRYRUN = os.getenv(...)` 모듈 상수 삭제, `self.dryrun` 속성 삭제, `setup()` print 의 `dryrun=` 표시 제거, `_write_status()` 의 `"dryrun"` 키 제거 |
| `dashboard/backend/routers/sessions.py` | `SessionStartRequest.mode` 필드 삭제, `Literal` import 정리, `_run_session_seed(..., dryrun: bool)` → `_run_session_seed(...)` (서명 단순화), `env["DEV_BOOTH_DRYRUN"]` 주입 제거, `body.mode != "live"` 분기 제거 |
| `dashboard/frontend/components/NewSessionModal.tsx` | `mode` state 삭제, 모달 reset 시 setMode 호출 제거, "실행 모드" 버튼 그룹 JSX 블록 전체 삭제, `api.startSession` 호출 payload 에서 `mode` 인자 제거 |
| `dashboard/frontend/lib/api.ts` | `startSession` body 타입에서 `mode: "dryrun" \| "live"` 필드 제거 |
| `dashboard/backend/tests/test_sessions_start.py` | happy-path POST payload 에서 `"mode": "dryrun"` 제거 |
| `tests/test_session.py` | `_write_status` schema 검증에서 `"dryrun"` 키 기대 삭제 |

---

## 검증 결과
```
$ pytest tests/ dashboard/backend/tests/ -q
.................................................................................
.................................................................................
.................................................................................
..........................                                               [100%]
242 passed in 0.98s

$ npx tsc --noEmit         (dashboard/frontend)
exit 0 (출력 없음)

$ npm run build            (dashboard/frontend)
✓ Compiled successfully
○ /                          16.1 kB     124 kB
● /session/[name]            112 kB      221 kB
○ /village                   1.42 kB     95.5 kB
```

---

## 이전 대비 변경
- 제거됨: 모달의 "드라이런 (읽기 전용) / 라이브 (실제 PR 생성)" 버튼 그룹
- 제거됨: `mode` state + reset 분기 + payload 필드
- 제거됨: `mode: Literal["dryrun", "live"]` Pydantic 필드
- 제거됨: `_run_session_seed` 의 `dryrun: bool` 파라미터 + env 주입
- 제거됨: `core/session.py` 의 `DRYRUN` 모듈 상수 + `self.dryrun` 속성 + status 의 `dryrun` 키

---

## 손대지 않은 것 (의도적)
- `core/scenario.py` — STAGE_DAG body 의 `(DEV_BOOTH_DRYRUN=1 이면 push --dry-run)` 안내문은 유지 (워커가 실제 push 시 안전을 위한 가드 설명; 실제 가드는 `core/dryrun/*` 스크립트가 담당)
- `core/dryrun/{gh,git,pre-push,install_hooks.sh}` — 클론된 워크스페이스에 설치되는 git pre-push 가드. `DEV_BOOTH_DRYRUN` 환경변수 자체는 `.env` 로만 토글되며, 기본값은 `0` (live)
- `core/souls/{conductor,executor}.SOUL.md` — 워커 SOUL 의 dryrun 안내문은 유지 (실제 가드 동작 설명)
- `tests/e2e/{e2e_dryrun.sh,e2e_live.sh}` — 수동 E2E 스모크 스크립트. 별도 surface
- `core/memories/*.MEMORY.md` — 에이전트 메모리

---

## 후속 작업
- 운영자: `sudo systemctl restart dev-booth-dashboard` (FastAPI 가 새 schema 를 픽업하도록)
- `.env` 의 `DEV_BOOTH_DRYRUN=0` 이 유일한 제어 지점이며, 이번 변경으로 코드 분기 자체가 없으므로 값은 무시됨 (향후 정리 시 함께 삭제 가능)
