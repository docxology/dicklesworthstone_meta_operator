"""Source bindings and native gate receipts for retained offline snapshots.

These receipts qualify source tests only. Corpus health, Sidecar validation,
and Flywheel adoption keep their own evidence and verdicts.
"""

from __future__ import annotations

import errno
import hashlib
import json
import math
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Iterator

from src import jsonio
from src.models import GateCheck, GateReport, to_dict

INPUT_DIRECTORIES: Final = (
    "src", "scripts", "tests", "docs", "data", "output/data", "output/figures",
)
INPUT_FILES: Final = ("pyproject.toml", "uv.lock", "AGENTS.md", "README.md")


@dataclass(frozen=True, slots=True)
class InputFile:
    """A gate input's relative path, content hash, and permission bits."""

    path: str
    sha256: str
    mode: int


def _files(path: Path) -> Iterator[Path]:
    """Walk declared inputs without following symlinks or fleet checkouts."""
    if path.is_symlink():
        raise OSError(errno.ELOOP, "gate inputs cannot be symlinks", str(path))
    if path.is_dir():
        for child in sorted(path.iterdir()):
            if child.name != "__pycache__" and child.suffix != ".pyc":
                yield from _files(child)
    elif path.is_file():
        yield path
    else:
        raise OSError(errno.ENOENT, "gate input missing or not a regular file", str(path))


def capture_inputs(root: Path) -> tuple[InputFile, ...]:
    """Hash exactly the source, tests, and saved inputs consumed by gate.sh."""
    entries = (
        InputFile(
            path.relative_to(root).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mode & 0o777,
        )
        for relative in (*INPUT_DIRECTORIES, *INPUT_FILES)
        for path in _files(root / relative)
    )
    return tuple(sorted(entries, key=lambda entry: entry.path))


def prepare_snapshot(root: Path, evidence_dir: Path) -> Path:
    """Copy and verify declared inputs, retaining the original file manifest."""
    root, evidence_dir = root.resolve(), evidence_dir.resolve()
    if evidence_dir.is_relative_to(root):
        raise OSError(errno.EINVAL, "gate evidence must be outside the checkout", str(evidence_dir))
    source = evidence_dir / "source"
    source.mkdir()
    inputs = capture_inputs(root)
    for relative in INPUT_DIRECTORIES:
        (source / relative).mkdir(parents=True, exist_ok=True)
    for entry in inputs:
        destination = source / entry.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / entry.path, destination)
    if capture_inputs(source) != inputs:
        raise OSError(errno.EBUSY, "gate inputs changed while copying", str(root))
    jsonio.write_json(evidence_dir / "source_manifest.json", to_dict(inputs))
    return source


def _source_check(root: Path, manifest: Path) -> tuple[GateCheck, str]:
    """Recompare original inputs, including additions, deletions, and modes."""
    try:
        content = manifest.read_bytes()
        matches = json.loads(content) == to_dict(capture_inputs(root))
        detail = "declared source inputs match the tested snapshot" if matches else "source inputs changed; rerun scripts/gate.sh"
        digest = hashlib.sha256(content).hexdigest()
    except (OSError, ValueError) as error:
        matches, detail, digest = False, f"source comparison unavailable: {error}", ""
    return GateCheck("source_unchanged", matches, detail), digest


def _tests_check(path: Path) -> GateCheck:
    """Require nonempty executed tests and no failures/errors in JUnit output."""
    try:
        tree = ET.parse(path)
        cases = tree.findall(".//testcase")
        executed = sum(case.find("skipped") is None for case in cases)
        failed = len(tree.findall(".//failure")) + len(tree.findall(".//error"))
        return GateCheck("tests_executed", executed > 0 and failed == 0,
                         f"{len(cases)} collected, {executed} executed, {failed} failures/errors")
    except (OSError, ET.ParseError) as error:
        return GateCheck("tests_executed", False, f"JUnit evidence unavailable: {error}")


def _coverage_check(path: Path) -> GateCheck:
    """Require actual branch measurement and a finite combined score >=90%."""
    try:
        raw = jsonio.read_json(path)
        percent = float(raw["totals"]["percent_covered"])
        branches = raw["meta"]["branch_coverage"] is True
        passed = branches and math.isfinite(percent) and 90 <= percent <= 100
        return GateCheck("source_coverage", passed, f"branch coverage enabled={branches}; score={percent:.2f}%; required >=90%")
    except (OSError, KeyError, TypeError, ValueError) as error:
        return GateCheck("source_coverage", False, f"coverage evidence unavailable: {error}")


def finish_gate(root: Path, evidence_dir: Path, exit_code: int) -> GateReport:
    """Write a failed or passing GateReport-shaped source receipt atomically.

    A passing receipt requires the whole shell gate to finish, JUnit execution,
    branch coverage, and unchanged original inputs. The manifest digest binds
    the separately retained input list; consumers must recompare it before reuse.
    """
    manifest = evidence_dir / "source_manifest.json"
    source_check, manifest_digest = _source_check(root, manifest)
    report = GateReport(
        checks=[
            GateCheck("gate_process", exit_code == 0, f"scripts/gate.sh exit {exit_code}"),
            source_check,
            _tests_check(evidence_dir / "pytest.xml"),
            _coverage_check(evidence_dir / "coverage.json"),
        ],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    jsonio.write_json(evidence_dir / "source_gate.json", {
        "generated_at": report.generated_at,
        "passed": report.passed,
        "checks": to_dict(report.checks),
        "scope": "offline-source",
        "source_root": str(root.resolve()),
        "source_manifest": str(manifest),
        "source_manifest_sha256": manifest_digest,
        "python_executable": sys.executable,
        "python_version": sys.version,
    })
    return report
