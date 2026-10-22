"""Real filesystem evidence and mutation controls for the offline source gate."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal, assert_never

import pytest

from src import jsonio
from src.source_evidence import (
    INPUT_DIRECTORIES, INPUT_FILES, capture_inputs, finish_gate, prepare_snapshot,
)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    for relative in INPUT_DIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)
    for relative in INPUT_FILES:
        (root / relative).write_text(relative, encoding="utf-8")
    (root / "src/module.py").write_text("value = 1\n", encoding="utf-8")
    return root


@pytest.fixture
def evidence(source: Path, tmp_path: Path) -> Path:
    directory = tmp_path / "evidence"
    directory.mkdir()
    prepare_snapshot(source, directory)
    (directory / "pytest.xml").write_text(
        '<testsuites><testsuite><testcase name="real"/></testsuite></testsuites>', encoding="utf-8",
    )
    jsonio.write_json(directory / "coverage.json", {
        "meta": {"branch_coverage": True}, "totals": {"percent_covered": 94.11},
    })
    return directory


def test_snapshot_is_sorted_complete_and_ignores_fleet_and_bytecode(source: Path, tmp_path: Path) -> None:
    (source / "repos").symlink_to(tmp_path, target_is_directory=True)
    (source / "src/__pycache__").mkdir()
    (source / "src/__pycache__/cached.pyc").write_bytes(b"ignored")
    first = capture_inputs(source)
    assert first == capture_inputs(source)
    assert [entry.path for entry in first] == sorted(entry.path for entry in first)
    assert len(first) == len(INPUT_FILES) + 1


def test_snapshot_copies_modes_and_saved_inputs(source: Path, evidence: Path) -> None:
    assert capture_inputs(source) == capture_inputs(evidence / "source")
    assert jsonio.read_json(evidence / "source_manifest.json")[0]["path"] == "AGENTS.md"


@pytest.mark.parametrize("relative", ["src/module.py", "docs/external"])
def test_symlink_inputs_refused(source: Path, tmp_path: Path, relative: str) -> None:
    path = source / relative
    if path.exists():
        path.unlink()
    path.symlink_to(tmp_path)
    with pytest.raises(OSError, match="symlinks"):
        capture_inputs(source)


def test_missing_inputs_and_in_checkout_evidence_refused(source: Path, tmp_path: Path) -> None:
    with pytest.raises(OSError, match="outside"):
        prepare_snapshot(source, source / "evidence")
    (source / "uv.lock").unlink()
    with pytest.raises(OSError, match="missing"):
        capture_inputs(source)


def test_receipt_uses_gate_shape_and_binds_manifest(source: Path, evidence: Path) -> None:
    report = finish_gate(source, evidence, 0)
    assert report.passed
    saved = jsonio.read_json(evidence / "source_gate.json")
    assert saved["passed"] and saved["scope"] == "offline-source"
    assert saved["source_root"] == str(source.resolve())
    assert saved["source_manifest_sha256"] == hashlib.sha256((evidence / "source_manifest.json").read_bytes()).hexdigest()
    assert saved["python_version"] and saved["python_executable"]
    assert {row["check_id"] for row in saved["checks"]} == {
        "gate_process", "source_unchanged", "tests_executed", "source_coverage",
    }


@pytest.mark.parametrize("mutation", ["content", "add", "delete", "mode"])
def test_source_changes_fail_even_with_passing_test_reports(source: Path, evidence: Path, mutation: Literal["content", "add", "delete", "mode"]) -> None:
    path = source / "src/module.py"
    match mutation:
        case "content":
            path.write_text("value = 2\n", encoding="utf-8")
        case "add":
            (source / "tests/new.py").write_text("pass\n", encoding="utf-8")
        case "delete":
            path.unlink()
        case "mode":
            path.chmod(path.stat().st_mode ^ 0o100)
        case unreachable:
            assert_never(unreachable)
    report = finish_gate(source, evidence, 0)
    assert not report.passed
    assert [check.check_id for check in report.checks if not check.passed] == ["source_unchanged"]


@pytest.mark.parametrize("xml", ["<testsuites/>", '<testsuites><testcase><skipped/></testcase></testsuites>',
                                    '<testsuites><testcase><failure/></testcase></testsuites>', "broken"])
def test_empty_skipped_failed_and_malformed_junit_fail(source: Path, evidence: Path, xml: str) -> None:
    (evidence / "pytest.xml").write_text(xml, encoding="utf-8")
    assert not finish_gate(source, evidence, 0).passed


@pytest.mark.parametrize("coverage", [
    '{"meta": {"branch_coverage": true}, "totals": {"percent_covered": 89.99}}',
    '{"meta": {"branch_coverage": false}, "totals": {"percent_covered": 100}}',
    '{"meta": {"branch_coverage": true}, "totals": {"percent_covered": NaN}}',
    '{}', '[]',
])
def test_low_line_only_and_invalid_coverage_fail(source: Path, evidence: Path, coverage: str) -> None:
    (evidence / "coverage.json").write_text(coverage, encoding="utf-8")
    assert not finish_gate(source, evidence, 0).passed


@pytest.mark.parametrize("name", ["coverage.json", "pytest.xml", "source_manifest.json"])
def test_missing_or_corrupt_evidence_fails(source: Path, evidence: Path, name: str) -> None:
    (evidence / name).write_text("corrupt", encoding="utf-8")
    assert not finish_gate(source, evidence, 0).passed
    (evidence / name).unlink()
    assert not finish_gate(source, evidence, 0).passed


def test_nonzero_process_exit_cannot_reuse_good_reports(source: Path, evidence: Path) -> None:
    report = finish_gate(source, evidence, 2)
    assert not report.passed
    assert not report.checks[0].passed
    assert all(check.passed for check in report.checks[1:])
