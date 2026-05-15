# Phase 0 probes — Dev-Booth Stabilization v5
## Date: 2026-05-15T05:28:17Z

## P0.1 — firebase-001 state
    SLUG                      NAME                          COUNTS
●   default                   Default                       (empty)
    e2e-kanban-001            e2e-kanban-001                blocked=1, done=1, todo=10
    firebase-001              firebase-001                  blocked=1, done=22, running=4, todo=4

Current board: default
Switch boards with `hermes kanban boards switch <slug>`.

### list firebase-001 (json compact)
  31 tasks
  by status: {'done': 22, 'blocked': 1, 'todo': 4, 'running': 4}
  - t_be0966f7 [blocked] [firebase-chat-exp] implement TASK-1 :: 
  - t_8256e2a9 [running] Set up the development environment :: 
  - t_d5179931 [running] Address high-severity vulnerabilities :: 
  - t_0bbcf12b [running] Set up the development environment :: 
  - t_4fe64b2d [running] Code structure analysis :: 

## P0.6 — profile baseline (config.yaml)
### conductor
  default: /data/vllm/models/Qwen2.5-Coder-32B-Instruct
  context_length: 65536
  max_turns: 40
  max_turns: 20
### architect
  default: /data/vllm/models/Qwen2.5-Coder-32B-Instruct
  context_length: 65536
  max_turns: 40
  max_turns: 20
### executor
  default: /data/vllm/models/Qwen2.5-Coder-32B-Instruct
  context_length: 65536
  max_turns: 40
  max_turns: 20

  backups -> /tmp/v5-backup/:
architect-config.yaml
architect-SOUL.md
conductor-config.yaml
conductor-SOUL.md
executor-config.yaml
executor-SOUL.md

## P0.7 — SOUL.md sizes
  27 1934 /home/mooner92/.hermes/profiles/conductor/SOUL.md
  25 1889 /home/mooner92/.hermes/profiles/architect/SOUL.md
  29 2035 /home/mooner92/.hermes/profiles/executor/SOUL.md

## P0.2 — protocol_violation evidence (firebase-001)
Hermes itself records 'protocol violation' as runs.outcome='crashed' with detail
'worker exited cleanly (rc=0) without calling kanban_complete or kanban_block'.
Task transitions to 'blocked' after failure_limit:2 attempts (per ~/.hermes/config.yaml).

Evidence rows:
  t_be0966f7 [blocked]   1 crashed run -> blocked (failure_limit reached or single-strike)
  t_8256e2a9 [running]   1 crashed + 1 running (within failure_limit)
  t_d5179931 [running]   1 running, no priors
  t_0bbcf12b [running]   1 crashed + 1 running
  t_4fe64b2d [running]   1 reclaimed (stale_lock) + 1 running

INSIGHT: 'protocol violation' is NOT a silent failure — Hermes flags it as crashed and
retries up to failure_limit. The v5 watchdog's purpose is therefore diagnostic visibility
(stale claims, exhausted retries), NOT primary enforcement.

Stage-1 sub-task evidence (t_8256e2a9 log): executor ran
  git clone https://github.com/example/firebase-app /home/mooner92/.hermes/kanban/boards/firebase-001/workspaces/t_8256e2a9
→ literal 'example/firebase-app' placeholder — confirms Problem 2 (sub-tasks don't carry
  the real repo_url; v5 Phase 2 body rewrites must inject it explicitly).

## P0.3 — vLLM served context window
model_id:        /data/vllm/models/Qwen2.5-Coder-32B-Instruct
max_model_len:   32768  (confirms plan default)
→ Phase 1 target: agent.max_turns: 15, model.context_length: 28000  (32768 − 4096 headroom)

## P0.4 — hermes kanban log + runs subcommands
Both EXIST on v0.13.0:
  hermes kanban log <task_id> [--tail N]   — worker stdout/transcript
  hermes kanban runs <task_id>             — attempt history (start/end/outcome/elapsed)
Plain-text only (no --json on either). The dashboard reader must shell out + parse.

## P0.5 — worker workspace path layout
Both layouts exist concurrently:
  ~/.hermes/kanban/boards/<slug>/workspaces/<task_id>/  (named-board workspace_kind=worktree)
  ~/.worktrees/<task_id>/                                (legacy / dispatcher default per profile)
Body templates must reference {HERMES_KANBAN_WORKSPACE} env var (literal), not hardcode.

## P0.8 — dashboard health
/api/health -> {ok:true, version:0.1.0}
/api/kanban/boards -> [firebase-001, e2e-kanban-001] (default board filtered out — correct)

## P0.9 — pytest baseline
78 passed in 0.59s

## Note on profile config.yaml (P0.6 follow-up)
There are TWO max_turns keys per file:
  L13 'agent.max_turns: 40'   (the one we want to lower → 15)
  L346 'max_turns: 20'         (under a personalities sub-tree; unrelated)
Mutation must target the agent section only (yaml-aware, not blind sed).
