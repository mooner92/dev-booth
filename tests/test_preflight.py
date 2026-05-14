"""US-001 — core/preflight.py checks (mostly mocked for determinism)."""
from __future__ import annotations

import json
import subprocess
from unittest import mock

import pytest

from core import config, preflight


# --------------------------------------------------------------------------
# check_vllm
# --------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_check_vllm_passes_on_expected_model():
    payload = {"data": [{"id": config.EXPECTED_MODEL}]}
    with mock.patch("urllib.request.urlopen", return_value=_FakeResp(payload)):
        preflight.check_vllm()  # must not raise


def test_check_vllm_fails_on_model_mismatch():
    payload = {"data": [{"id": "some/other-model"}]}
    with mock.patch("urllib.request.urlopen", return_value=_FakeResp(payload)):
        with pytest.raises(preflight.PreflightError, match="model mismatch"):
            preflight.check_vllm()


def test_check_vllm_fails_when_unreachable():
    with mock.patch("urllib.request.urlopen", side_effect=OSError("refused")):
        with pytest.raises(preflight.PreflightError, match="unreachable"):
            preflight.check_vllm()


# --------------------------------------------------------------------------
# check_awg — real import (AWG is installed in the venv)
# --------------------------------------------------------------------------
def test_check_awg_real_import():
    preflight.check_awg()  # must not raise under the venv interpreter


# --------------------------------------------------------------------------
# check_gh
# --------------------------------------------------------------------------
def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_check_gh_passes_when_authenticated():
    with mock.patch("subprocess.run", return_value=_completed(0, "Logged in")):
        preflight.check_gh()


def test_check_gh_fails_when_not_authenticated():
    with mock.patch("subprocess.run", return_value=_completed(1, "", "not logged in")):
        with pytest.raises(preflight.PreflightError, match="not authenticated"):
            preflight.check_gh()


# --------------------------------------------------------------------------
# check_profiles
# --------------------------------------------------------------------------
def test_check_profiles_soft_when_missing():
    with mock.patch("subprocess.run", return_value=_completed(0, "default\n")):
        assert preflight.check_profiles(require=False) is False  # warns, no raise


def test_check_profiles_hard_when_required_and_missing():
    with mock.patch("subprocess.run", return_value=_completed(0, "default\n")):
        with pytest.raises(preflight.PreflightError, match="missing"):
            preflight.check_profiles(require=True)


def test_check_profiles_passes_when_all_present():
    listing = "default\nopenclaw\nhermes-a\nhermes-b\n"
    with mock.patch("subprocess.run", return_value=_completed(0, listing)):
        assert preflight.check_profiles(require=True) is True
