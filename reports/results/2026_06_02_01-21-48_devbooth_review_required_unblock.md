# Dev-Booth 완전 자동화 — `review-required` 자가-블록 제거 (결과 보고서)

> 작성일: 2026-06-02 · 브랜치: `feat/kanban-redesign-2026-05-14`
> 미션: Architect/Executor 워커가 분석·구현·리뷰 태스크를 끝낸 뒤 `kanban_block(reason="review-required: ...")`를 **스스로 호출해 워크플로우를 멈추는** 문제를 제거한다. git URL만 넣으면 분석→구현→테스트→커밋→PR까지 사람 개입 없이 자동 진행되어야 한다.

---

## 1. 근본 원인 (요약)

Qwen2.5-Coder-32B 워커는 "코드에서 이슈를 발견하는 것"과 "태스크가 막힌 것"을 혼동한다. 보안 누락·문서 부재 같은 발견은 **분석의 정상 결과물**인데, 모델이 이를 블로커로 오인해 `kanban_block(reason="review-required: ...")`를 호출했다. gateway dispatcher는 `ready` 태스크만 워커를 스폰하고 `blocked`는 건드리지 않으므로, 사람이 `hermes kanban unblock`할 때까지 파이프라인이 영원히 멈췄다.

자가-블록을 유발한 세 출처:
1. **KANBAN_GUIDANCE** (`~/.hermes/hermes-agent/agent/prompt_builder.py`) — Hermes 코어. **수정 금지 (건드리지 않음).**
2. **architect/executor SOUL.md 규칙 2 (block-don't-guess)** — "리뷰 미통과 시 review-required로 block". → **여기를 오버라이드함.**
3. **kanban-worker 스킬 예시** (`~/.hermes/skills/devops/kanban-worker/SKILL.md`) — `review-required handoff:` 예시. 공용 스킬이라 **수정하지 않고** SOUL.md 규칙으로 무력화.

해결 전략: SOUL.md가 "이슈 발견 = 정상 결과물(metadata 기록), 블로커 아님"을 명시적으로 구분하게 만들고, scenario.py 본문에서 review-required 자가-블록 유발 패턴을 제거한다. KANBAN_GUIDANCE·SKILL.md는 그대로 두고 SOUL.md 규칙이 이를 무력화한다.

---

## 2. 변경한 파일 (각 1줄 요약)

| 파일 | 변경 |
|---|---|
| `core/souls/architect.SOUL.md` | 규칙 2 `block-don't-guess` → `complete-don't-block-on-findings`; 규칙 1의 "리뷰 통과 시에만 LGTM" → "리뷰 단계는 approved를 metadata에 기록하고 **항상** complete (block 금지)" |
| `~/.hermes/profiles/architect/SOUL.md` | 위와 동일 (배포본 동기화) |
| `core/souls/executor.SOUL.md` | 규칙 2 → `complete-don't-block-on-findings` (테스트 통과 시 complete; **테스트 실패 시에만** block) |
| `~/.hermes/profiles/executor/SOUL.md` | 위와 동일 (배포본 동기화) |
| `core/scenario.py` | 5개 stage(4·13·15·16·18)의 `## 막힐 때` + `kanban_block(reason="review-required: ...")` 제거; stage 15·18은 `## 완료`를 approved 플래그 기록 + 항상 complete 형태로 재작성 |
| `tests/test_scenario_bodies.py` | 구(舊) 블록-필수 테스트를 신규 계약 테스트로 교체 (아래 §4) |

> 배포본(`~/.hermes/profiles/*`)은 git 추적 밖이지만 gateway가 워커를 스폰할 때 읽는 **런타임 본**이다. 원본(`core/souls/*`)과 **두 벌 모두** 동기화했다.

---

## 3. 블록 회계 (제거 vs 유지)

**제거한 review-required 자가-블록: 5개** — scenario.py stage 4(진입점 분석), 13(TASK-1 구현), 15(TASK-1 리뷰), 16(TASK-2 구현), 18(TASK-2 리뷰).

**유지한 테스트-실패 블록: 2개** — scenario.py stage 14(`kanban_block(reason="TASK-1 테스트 실패: ...")`, L482), 17(`TASK-2 테스트 실패`, L561). 이건 정상적인 조건부 실패이지 자가-블록이 아니므로 그대로 둔다.

리뷰 단계(15·18)는 이제 `kanban_complete(summary="리뷰 완료 ...", metadata={"approved": true, "findings": [...], "file": "..."})`로 **항상 완료**한다. approved가 false여도 complete한다 — 후속 수정 분기는 Conductor 몫(이 작업 범위 밖).

---

## 4. 테스트 업데이트 근거 (왜 테스트를 고쳤나)

기존 `tests/test_scenario_bodies.py::test_review_and_implementation_have_block_pathway`는 **모든 review-gate/implementation stage가 `kanban_block(` + `## 막힐 때`를 갖는지** 강제했다 — 즉 이번에 제거하는 바로 그 자가-블록을 의무화하는 테스트였다. 동작을 의도적으로 바꾸므로 이 테스트도 새 계약을 반영해야 한다 (테스트를 통과시키려고 삭제한 것이 아니라 — 스펙 변경에 맞춰 의도를 다시 인코딩).

교체 결과 — 더 강한 두 가드:
- `test_no_review_required_self_block` (21개 stage 전수 파라미터화): **어떤 stage 본문에도 `review-required`가 없어야** 한다. 이 작업의 핵심 회귀 가드.
- `test_test_stages_retain_failure_block_pathway` (stage 14·17): 테스트 실행 stage는 `kanban_block(` + `## 막힐 때`를 **유지**해야 한다 (진짜 테스트 실패 시 레인이 멈추도록).

`test_body_has_completion_block`(모든 stage가 `## 완료`+`kanban_complete(`+`metadata=`)은 그대로 통과 — 15·18의 새 완료 섹션도 충족.

---

## 5. 검증 결과 (프롬프트 6-체크 + 회귀)

| # | 검사 | 결과 |
|---|---|---|
| 1 | `ast.parse(core/scenario.py)` | **SYNTAX OK** |
| 2 | scenario.py에 `review-required` 자가-블록 | **0건 (제거 완료)** |
| 3 | scenario.py 테스트-실패 블록 | **2건 (stage 14 L482, 17 L561 유지)** |
| 4 | 4개 SOUL 파일에 `complete-don't-block-on-findings` | **각 1건** |
| 5 | live SOUL 파일에 옛 `kanban_block(reason="review-required:` | **0건** (단, `*.bak` 백업은 옛 텍스트 보존 — `grep -rn core/souls/`는 .bak도 매칭하므로 정상) |
| 6 | `.bak` 백업 6개 | **모두 존재** |
| — | `env/bin/python -m pytest tests/ -q` | **161 passed** (베이스라인 144 → +17: 구 6 파라미터 항목 제거, 신규 21+2 추가 = 커버리지 증가) |
| — | 금지 파일 미변경 | `prompt_builder.py`·`kanban-worker/SKILL.md` 타임스탬프 불변 (미수정 확인) |

stage 15/18 불변식 확인: `is_review_gate=True`, `kanban_block` 없음, `kanban_complete` 있음, metadata에 `approved`, body 639/520자(<2000).

---

## 6. 운영자 다음 단계 (필수)

1. **gateway 재시작** — SOUL.md/프로필 변경을 워커가 읽으려면 gateway를 재시작해야 한다. 이 환경의 gateway는 **systemd** 서비스다(PM2 아님 — `pm2`는 미설치). 운영자가 직접 실행:
   ```bash
   sudo systemctl restart hermes-gateway
   ```
   (sudo 필요 → 본 자동화에서 직접 실행하지 않음. 운영자가 실행할 것.)
2. **기존 blocked 태스크 해제** — 이미 `blocked`로 멈춘 기존 태스크는 새 규칙으로 자동 재시작되지 않는다. 한 번 풀어줘야 새 워커가 새 SOUL로 재시도한다:
   ```bash
   hermes kanban --board <slug> unblock <task_id>
   ```
3. **신규 세션** — `core/scenario.py` 본문 변경은 **새로 seed되는 보드**에만 적용된다(기존 보드의 태스크 본문은 seed 시점에 고정됨). 새 세션부터 review-required 자가-블록 없는 21단계가 적용된다.

---

## 7. 백업 / 롤백

`.bak` 백업 6개(편집 직전 byte-identical 사본):
- `core/scenario.py.bak`, `core/souls/architect.SOUL.md.bak`, `core/souls/executor.SOUL.md.bak`, `tests/test_scenario_bodies.py.bak`
- `~/.hermes/profiles/architect/SOUL.md.bak`, `~/.hermes/profiles/executor/SOUL.md.bak`

repo 내 4개는 git 추적본이라 `git checkout -- <file>`로도 복구 가능하지만, **프로필 2개는 git 밖이라 `.bak`이 유일한 롤백 수단**이다. gateway 재시작 후 새 동작이 확인되면 `.bak`은 삭제해도 된다.

---

## 8. 범위 밖 / 잔존 메모

- **금지 규칙 준수:** `agent/prompt_builder.py`(KANBAN_GUIDANCE)·`kanban-worker/SKILL.md`는 건드리지 않았다. SOUL.md 규칙 2가 이들의 "review-required" 권고를 Dev-Booth 파이프라인에서 무력화한다.
- 새 SOUL 규칙 본문에 `review-required` 단어가 등장하지만, 이는 "review-required로 block하지 **않는다**"는 **부정(negation)** 문맥이다(의도적). 실제 `kanban_block(reason="review-required:` 지시는 0건.
- `executor.SOUL.md`/`executor.MEMORY.md`의 stale "## Dryrun 규칙" 절은 별도 이슈(이전 코드리뷰 보고서 H1)로, 이 작업 범위 밖이라 손대지 않았다.

---

*검증 근거: `core/scenario.py`·`core/souls/*`·`~/.hermes/profiles/{architect,executor}/SOUL.md`·`tests/test_scenario_bodies.py`의 실제 내용과 `pytest tests/` 출력(161 passed)을 직접 대조.*
