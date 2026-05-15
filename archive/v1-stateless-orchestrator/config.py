"""Centralised constants for the Dev-Booth multi-agent runtime.

Every magic value the orchestrator, logger, and preflight need lives here so it
can be tweaked without code spelunking. Plan v3 §6 is the source of truth.

Reality notes (plan principle P5 — reconcile to verified reality):
  * ``HERMES_BIN`` is the wrapper at ``~/.local/bin/hermes`` (it scrubs
    PYTHONPATH/PYTHONHOME and execs the real binary — desirable isolation).
  * ``MAX_MODEL_LEN = 32768``: the live vLLM on :8003 reports
    ``max_model_len=32768``. The ``.env`` ``MAX_MODEL_LEN=65536`` is the *other*
    vLLM (:8000, Qwen3-Coder-Next) and is irrelevant here. No behaviour change —
    worst-case prompt is ~4000 tokens and ``PROMPT_HARD_CEILING`` (chars) is the
    real guard.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --------------------------------------------------------------------------
# .env — the orchestrator's environment of record
# --------------------------------------------------------------------------
ENV_FILE = Path("/dev-booth/config/.env")
load_dotenv(ENV_FILE)

# --------------------------------------------------------------------------
# Filesystem roots & binaries
# --------------------------------------------------------------------------
DEV_BOOTH_ROOT = Path("/dev-booth")
SESSIONS_ROOT = Path(os.environ.get("DEV_BOOTH_PATH", "/dev-booth/sessions"))

VENV_PYTHON = "/dev-booth/env/bin/python3.11"
AWG_BIN = "/dev-booth/env/bin/awg"
# NEW-1 (v3 architect): the real hermes path. There is NO hermes under
# /dev-booth/env/bin. This wrapper scrubs PYTHONPATH/PYTHONHOME then execs the
# bundled venv hermes — exactly the isolation we want for subprocess turns.
HERMES_BIN = "/home/mooner92/.local/bin/hermes"

# --------------------------------------------------------------------------
# Agents
# --------------------------------------------------------------------------
AGENTS: tuple[str, ...] = ("openclaw", "hermes-a", "hermes-b")
ORCHESTRATOR_ID = "orchestrator"  # reserved sender id — NEVER an AWG queue agent

# --------------------------------------------------------------------------
# Hermes invocation / safety caps (DD1, DD6)
# --------------------------------------------------------------------------
HERMES_MAX_TURNS = 40              # set in each profile config.yaml (FE-2)
HERMES_TURN_TIMEOUT_S = 900        # per-turn subprocess wall-clock timeout
SESSION_TIMEOUT_S = 5400           # whole-session wall-clock cap
MAX_REVISE_ROUNDS = 3              # dev-loop revise cap (8e: mark-failed-continue)

# --------------------------------------------------------------------------
# Prompt budget (helper 8a, PM-3)
# --------------------------------------------------------------------------
BODY_CAP = 4000                    # chars per context artifact (head+tail trunc)
MAX_ARTIFACTS_PER_PROMPT = 3
PROMPT_HARD_CEILING = 50000        # chars — assert before every dispatch
MAX_MODEL_LEN = 32768              # verified: live :8003 vLLM max_model_len

# --------------------------------------------------------------------------
# Stage narration heartbeat (helper 8f)
# --------------------------------------------------------------------------
STAGE_HEARTBEAT_EVERY = 15         # secondary trigger: every N agent messages
HEARTBEAT_INTERVAL_S = 45          # primary trigger: re-emit if >45s since last
                                   # log append (45s < StageTracker 60s window)

# --------------------------------------------------------------------------
# vLLM (authoritative source is the hermes `default` profile config.yaml)
# --------------------------------------------------------------------------
VLLM_BASE_URL = "http://localhost:8003/v1"
EXPECTED_MODEL = "/data/vllm/models/Qwen2.5-Coder-14B-Instruct"

# --------------------------------------------------------------------------
# GitHub (KEEP keys from .env)
# --------------------------------------------------------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
UPSTREAM_OWNER = os.environ.get("GITHUB_UPSTREAM_OWNER", "mooner92")
BOT_OWNER = os.environ.get("GITHUB_BOT_OWNER", "CrownClownCrowd")

# --------------------------------------------------------------------------
# 12-stage scenario — canonical stage ids (must match dashboard stage_mapper)
# --------------------------------------------------------------------------
STAGE_IDS: tuple[str, ...] = (
    "repo_clone",       # 1
    "initial_scan",     # 2
    "plan_drafted",     # 3
    "plan_approved",    # 4
    "implementation",   # 5
    "self_review",      # 6
    "tests_running",    # 7
    "tests_passed",     # 8
    "pr_drafted",       # 9
    "pr_review",        # 10
    "pr_approved",      # 11
    "pr_merged",        # 12
)
