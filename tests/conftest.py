"""Pytest configuration for the Dev-Booth orchestrator test suite.

Puts the repo root (``/dev-booth``) on ``sys.path`` so ``import core.*`` works
when pytest is invoked as ``/dev-booth/env/bin/python3.11 -m pytest tests/``.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
