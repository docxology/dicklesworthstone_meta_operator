"""Smoke tests for scripts/: preflight subprocess run + compile checks.

Scripts delegate everything to tested ``src/`` modules; these checks prove the
wiring (paths, argparse, exit codes) works as invoked from a real shell.
"""

from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((PROJECT_ROOT / "scripts").glob("*.py"))


def test_all_scripts_compile():
    assert len(SCRIPTS) == 11
    for script in SCRIPTS:
        py_compile.compile(str(script), doraise=True)


def test_preflight_offline_succeeds():
    """Real subprocess: --offline skips gh auth; toolchain checks still run."""
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "00_preflight.py"), "--offline"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert "preflight OK" in proc.stdout


def test_orchestrate_help_exit_zero():
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "50_orchestrate.py"), "--help"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert proc.returncode == 0
    assert "--auto" in proc.stdout


def test_health_gate_help_exit_zero():
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "70_health_gate.py"), "--help"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert proc.returncode == 0
    assert "--from-github" in proc.stdout


def test_health_gate_script_runs_against_real_tree():
    """Gate runs end-to-end (exit 0 GO / 1 NO-GO) and always prints a verdict."""
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "70_health_gate.py")],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert proc.returncode in (0, 1)
    assert "HEALTH GATE:" in proc.stdout
    for line in proc.stdout.splitlines():
        if line.startswith("  ["):
            assert ("[PASS]" in line) ^ ("[FAIL]" in line)
