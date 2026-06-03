# Dev-Booth Scenario v6 — 마이크로 태스크 DAG 재설계

**Date:** 2026-05-17
**Branch:** `feat/kanban-redesign-2026-05-14`
**Goal:** 1 태스크 = 1 에이전트 세션 = 5턴 안에 완료 가능한 작은 단위로 분해
**Result:** ✅ 12 → 21 stages, 모든 body ≤736B, pytest 239/239 passed

---

## 1. 변경 개요

| | v5 (이전) | v6 (현재) |
|--|----------|-----------|
| Stage 수 | 12 | **21** |
| 분석 단계 수 | 2 (architect + executor 통합) | **6** (entrypoint / components×2 / api / config / deps) |
| 구현 사이클 | 1 (TASK-{n} 파라미터) | **2 명시적 사이클** (TASK-1 + TASK-2, 각 impl/test/review 분리) |
| 평균 body 크기 | ~990B | **~640B** |
| 최대 body 크기 | 1 098B | **736B** |
| 파일 읽기 규칙 | (없음) | **모든 body 에 `head -n` / `tail -n` 강제** |

---

## 2. 21-Stage 마이크로 DAG

| Stage | Assignee  | Tag            | Body | Title                              |
|------:|-----------|----------------|-----:|------------------------------------|
| 1     | conductor | orchestration  | 674B | fork & clone                       |
| 2     | conductor | orchestration  | 532B | 디렉터리 구조 파악                 |
| 3     | conductor | orchestration  | 624B | README + 패키지 파일 분석          |
| 4     | architect | analysis       | 681B | 진입점 파일 분석                   |
| 5     | architect | analysis       | 564B | 컴포넌트/모듈 분석 1/2             |
| 6     | architect | analysis       | 612B | 컴포넌트/모듈 분석 2/2             |
| 7     | architect | analysis       | 595B | API/라우터 분석                    |
| 8     | executor  | analysis       | 616B | 설정/환경 분석                     |
| 9     | executor  | analysis       | 633B | 의존성/취약점 분석                 |
| 10    | conductor | orchestration  | 644B | 분석 결과 취합                     |
| 11    | conductor | orchestration  | 704B | 개선방안 TASK 목록 작성            |
| 12    | conductor | orchestration  | 736B | feature 브랜치 생성                |
| 13    | executor  | implementation | 666B | TASK-1 구현                        |
| 14    | executor  | implementation | 651B | TASK-1 테스트                      |
| 15    | architect | review         | 615B | TASK-1 코드 리뷰 (is_review_gate)  |
| 16    | executor  | implementation | 679B | TASK-2 구현 (parent_stages=[15])   |
| 17    | executor  | implementation | 623B | TASK-2 테스트                      |
| 18    | architect | review         | 487B | TASK-2 코드 리뷰 (is_review_gate)  |
| 19    | conductor | orchestration  | 722B | 변경사항 커밋                      |
| 20    | conductor | pr             | 694B | PR 초안 작성                       |
| 21    | conductor | pr             | 698B | PR 제출                            |

---

## 3. 모든 body 에 강제된 공통 헤더

```markdown
## ⚠️ 파일 읽기 규칙 (필수)
- `cat <파일>` 금지 → `head -n 100 <파일>` 만 사용 (최대 100줄)
- 명령 결과는 `... | tail -n 20` 으로만 확인
- 한 태스크에서 읽는 파일 최대 3개
```

`core/scenario.py` 의 `_body()` helper 가 모든 body_template 앞에 자동 prepend.

---

## 4. SOUL.md 업데이트 (6개 파일)

다음 6개 파일에 동일한 "## ⚠️ 파일 읽기 규칙" 섹션 삽입:

- `/dev-booth/core/souls/conductor.SOUL.md`
- `/dev-booth/core/souls/architect.SOUL.md`
- `/dev-booth/core/souls/executor.SOUL.md`
- `~/.hermes/profiles/conductor/SOUL.md`
- `~/.hermes/profiles/architect/SOUL.md`
- `~/.hermes/profiles/executor/SOUL.md`

`grep -c "파일 읽기 규칙"` → 모든 파일 1.

---

## 5. pytest 결과

```
================================
v5 → v6 마이그레이션 직후 (1차):
  52 failed, 155 passed     ← v5 12-stage 단언이 21-stage 와 충돌

테스트 4개 파일 v6 invariant 로 업데이트 후 (2차, 최종):
  239 passed in 0.98s
================================
```

업데이트된 테스트 파일:
- `tests/test_scenario.py` — 12→21 갱신, 분석 stage assignee 제약 추가
- `tests/test_scenario_bodies.py` — v5 skeleton 검사 → v6 invariants
  (head-n 규칙, body ≤2000B, kanban_complete + metadata)
- `tests/test_session.py` — 12개 task 단언 → `len(STAGE_DAG)`
- `dashboard/backend/tests/test_stage_narration_crossseam.py` —
  21 stage 커버리지 + stage 1..15 monotonic + 첫/마지막 anchor

---

## 6. PRD 수용 기준 검증

| US    | 요약                                          | 결과 |
|-------|-----------------------------------------------|------|
| US-001 | 21+ stage / body ≤2000B / head-n / kanban_complete / assignee / DAG 방향성 / stage 1·끝=conductor | ✅ |
| US-002 | entrypoint / components / api / config / deps 분석 stage 모두 존재, 모두 architect 또는 executor | ✅ |
| US-003 | TASK-1·TASK-2 각 impl/test/review 6 stage, 구현=executor, 리뷰=architect+is_review_gate, TASK-1 review가 TASK-2 impl의 parent | ✅ |
| US-004 | core/souls 3개 + ~/.hermes/profiles 3개 SOUL 에 파일 읽기 규칙 섹션 추가 | ✅ |
| US-005 | pytest 239 passed (exit 0) + DevBoothSession 인스턴스화 + format_task 21 stage KeyError 없음 | ✅ |
| US-006 | 본 보고서 + git commit | ✅ |

---

## 7. 금지 사항 준수

- ✅ 기존 12-stage DAG 완전 교체 (병행 없음)
- ✅ 모든 body_template `<` 2000자 (가장 큰 것 736B)
- ✅ 모든 body 에 `head -n` 또는 `tail -n` 키워드 포함
- ✅ 모든 body 에 `kanban_complete(` 예시 포함
- ✅ main 브랜치 미수정 (`feat/kanban-redesign-2026-05-14` 유지)
- ✅ 테스트 없이 완료 선언하지 않음 (pytest 239/239)
