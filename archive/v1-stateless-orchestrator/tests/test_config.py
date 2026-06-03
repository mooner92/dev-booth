"""US-001 — core/config.py constants + .env reconciliation."""
from __future__ import annotations

from pathlib import Path

from core import config

ENV_TEXT = Path("/dev-booth/config/.env").read_text(encoding="utf-8")

# Keys the plan v3 .env KEY DISPOSITION MATRIX says to DELETE.
_DELETED_KEYS = (
    "VLLM_BASE_URL",
    "AGENT_MODEL",
    "OPENCLAW_TOKEN",
    "HERMES_A_TOKEN",
    "HERMES_B_TOKEN",
    "DISCORD_GUILD_ID",
    "NOTION_TOKEN",
    "NOTION_DATABASE_ID",
)
# Keys the matrix says to KEEP.
_KEPT_KEYS = (
    "GITHUB_TOKEN",
    "GITHUB_UPSTREAM_OWNER",
    "GITHUB_BOT_OWNER",
    "DEV_BOOTH_PATH",
    "MAX_MODEL_LEN",
)


def test_env_stale_keys_removed():
    for key in _DELETED_KEYS:
        assert f"{key}=" not in ENV_TEXT, f"{key} should have been removed from .env"


def test_env_kept_keys_present():
    for key in _KEPT_KEYS:
        assert f"{key}=" in ENV_TEXT, f"{key} must remain in .env"


def test_config_imports_clean():
    # Importing the module is the smoke test; `from core import config` above
    # already exercised it, this asserts the public surface is intact.
    assert config.HERMES_BIN == "/home/mooner92/.local/bin/hermes"
    assert config.VENV_PYTHON == "/dev-booth/env/bin/python3.11"
    assert config.AWG_BIN == "/dev-booth/env/bin/awg"


def test_agents_are_the_three_real_agents():
    assert config.AGENTS == ("openclaw", "hermes-a", "hermes-b")
    assert config.ORCHESTRATOR_ID == "orchestrator"
    assert config.ORCHESTRATOR_ID not in config.AGENTS


def test_safety_caps_are_sane():
    assert config.HERMES_MAX_TURNS == 40
    assert config.HERMES_TURN_TIMEOUT_S == 900
    assert config.SESSION_TIMEOUT_S == 5400
    assert config.MAX_REVISE_ROUNDS == 3


def test_prompt_budget_constants():
    assert config.BODY_CAP == 4000
    assert config.PROMPT_HARD_CEILING == 50000
    # verified reality: live :8003 vLLM reports max_model_len 32768
    assert config.MAX_MODEL_LEN == 32768
    # worst-case prompt budget must stay under the hard ceiling
    worst_case = 500 + 1000 + config.MAX_ARTIFACTS_PER_PROMPT * config.BODY_CAP + 1000
    assert worst_case < config.PROMPT_HARD_CEILING


def test_heartbeat_inside_conflict_window():
    # heartbeat must fire well before StageTracker's 60s conflict window closes
    assert config.HEARTBEAT_INTERVAL_S < 60
    assert config.STAGE_HEARTBEAT_EVERY == 15


def test_vllm_endpoint_and_model():
    assert config.VLLM_BASE_URL == "http://localhost:8003/v1"
    assert config.EXPECTED_MODEL == "/data/vllm/models/Qwen2.5-Coder-14B-Instruct"


def test_stage_ids_match_count_and_order():
    assert len(config.STAGE_IDS) == 12
    assert config.STAGE_IDS[0] == "repo_clone"
    assert config.STAGE_IDS[-1] == "pr_merged"
