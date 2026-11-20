"""Tests for check-notes-report (gha#1367)."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "report.py"
spec = importlib.util.spec_from_file_location("report", SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_success_and_skipped_pass():
    rows, failed, missing = report.summarize(
        {"a": {"outcome": "success"}, "b": {"outcome": "skipped"}}, ["a", "b"])
    assert failed == [] and missing == [] and len(rows) == 2


def test_failure_is_read_from_outcome_not_conclusion():
    # continue-on-error turns a failed step's conclusion to success but
    # keeps its outcome at failure.
    _, failed, _ = report.summarize(
        {"a": {"outcome": "failure", "conclusion": "success"}}, ["a"])
    assert failed == ["a"]


def test_missing_step_is_reported():
    _, _, missing = report.summarize({"other": {"outcome": "success"}}, ["a"])
    assert missing == ["a"]


def run_main(tmp_path, steps, checks):
    summary = tmp_path / "summary.md"
    output = tmp_path / "output.txt"
    env = {**os.environ, "STEPS": json.dumps(steps), "CHECKS": json.dumps(checks),
           "GITHUB_STEP_SUMMARY": str(summary), "GITHUB_OUTPUT": str(output)}
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env,
                            capture_output=True, text=True)
    result.output = output.read_text() if output.exists() else ""
    return result, summary.read_text() if summary.exists() else ""


def test_main_fails_on_a_failed_check(tmp_path):
    result, summary = run_main(tmp_path, {"a": {"outcome": "failure"},
                                          "b": {"outcome": "success"}}, ["a", "b"])
    assert result.returncode == 1
    assert "Check steps failed (a blocking finding or an error): a" in result.stdout
    assert "| `a` | failure |" in summary
    assert result.output == "result=failed\n"


def test_main_passes_when_all_pass_or_skip(tmp_path):
    result, _ = run_main(tmp_path, {"a": {"outcome": "skipped"}}, ["a"])
    assert result.returncode == 0, result.stdout
    assert result.output == "result=passed\n"


def test_main_errors_on_a_missing_step(tmp_path):
    result, _ = run_main(tmp_path, {}, ["a"])
    assert result.returncode == 2
    assert result.output == "result=missing\n"
