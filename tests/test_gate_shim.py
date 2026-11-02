"""Restart gate compatibility: `.venv/Scripts/python.exe` must work through cmd.exe.

The issue's gate is configured as a forward-slash path. On Windows cmd parses
`.venv/Scripts/python.exe` as command `.venv` plus argument `/Scripts/python.exe`,
so the repository ships `.venv.cmd` to forward to the real interpreter.
This test runs the exact gate form; it is skipped on non-Windows.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe shim is Windows-only")


def test_forward_slash_venv_path_runs_through_cmd() -> None:
    completed = subprocess.run(
        ["cmd", "/c", ".venv/Scripts/python.exe", "-c", "print('gate-shim-ok')"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "gate-shim-ok" in completed.stdout


def test_shim_forwards_pytest_arguments() -> None:
    """The real gate form is `.venv/Scripts/python.exe -m pytest -q`."""
    completed = subprocess.run(
        ["cmd", "/c", ".venv/Scripts/python.exe", "-m", "pytest", "--version"],
        cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "pytest" in completed.stdout.lower()
