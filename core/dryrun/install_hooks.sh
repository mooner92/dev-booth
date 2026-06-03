#!/usr/bin/env bash
# Install the Dev-Booth pre-push dryrun hook into a repo's .git/hooks.
#
# Usage: core/dryrun/install_hooks.sh <repo_path>
#
# The stage-1 scenario task body instructs the conductor worker to run this
# right after it clones the target repo (the worker's clone is a fresh
# standalone repo with its own .git, NOT a worktree of /dev-booth — so it does
# not inherit /dev-booth's hooks; it needs its own). This is a best-effort
# Layer-1 gate; the mechanically-enforced backstop is Layer 3 (GITHUB_TOKEN
# scrubbed from the gateway env under dryrun — see run.sh).
set -euo pipefail

REPO="${1:?usage: install_hooks.sh <repo_path>}"
HOOK_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/pre-push"

GIT_COMMON_DIR="$(git -C "$REPO" rev-parse --git-common-dir 2>/dev/null)"
[[ "$GIT_COMMON_DIR" = /* ]] || GIT_COMMON_DIR="$REPO/$GIT_COMMON_DIR"
HOOKS_DIR="$GIT_COMMON_DIR/hooks"

mkdir -p "$HOOKS_DIR"
cp "$HOOK_SRC" "$HOOKS_DIR/pre-push"
chmod +x "$HOOKS_DIR/pre-push"
echo "[dryrun-gate] installed pre-push hook -> $HOOKS_DIR/pre-push"
