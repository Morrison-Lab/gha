"""Tests for run-check.sh."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "run-check.sh"


def run(args, tmp_path):
    summary = tmp_path / "summary.md"
    env = {**os.environ, "RUN_CHECK_SUMMARY": str(summary)}
    proc = subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env
    )
    rows = summary.read_text() if summary.exists() else ""
    return proc, rows


def test_passes_and_groups(tmp_path):
    proc, rows = run(["c1", "--", "echo", "hello"], tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["::group::c1", "hello", "::endgroup::"]
    assert rows.splitlines()[-1] == "| c1 | pass | 0 |"
    assert rows.startswith("| Check | Result | Exit code |")


def test_failure_keeps_exit_code(tmp_path):
    proc, rows = run(["c2", "--", "bash", "-c", "exit 3"], tmp_path)
    assert proc.returncode == 3
    assert rows.splitlines()[-1] == "| c2 | FAIL | 3 |"


def test_env_is_passed(tmp_path):
    proc, _ = run(["c3", "FOO=bar", "--", "bash", "-c", 'echo "$FOO"'], tmp_path)
    assert "bar" in proc.stdout.splitlines()


def test_annotations_are_titled(tmp_path):
    script = (
        "echo '::warning::plain'; echo '::error file=a.qmd,line=2::located';"
        " echo '::warning title=mine::kept'; echo 'not ::warning::'"
    )
    proc, _ = run(["c4", "--", "bash", "-c", script], tmp_path)
    lines = proc.stdout.splitlines()
    assert "::warning title=c4::plain" in lines
    assert "::error title=c4,file=a.qmd,line=2::located" in lines
    assert "::warning title=mine::kept" in lines
    assert "not ::warning::" in lines


def test_two_checks_share_one_summary(tmp_path):
    summary = tmp_path / "summary.md"
    env = {**os.environ, "RUN_CHECK_SUMMARY": str(summary)}
    for n, rc in (("a", 0), ("b", 1)):
        subprocess.run(
            ["bash", str(SCRIPT), n, "--", "bash", "-c", f"exit {rc}"], env=env
        )
    lines = summary.read_text().splitlines()
    assert lines[0].startswith("| Check")
    assert lines[2:] == ["| a | pass | 0 |", "| b | FAIL | 1 |"]


def test_bad_usage(tmp_path):
    assert run([], tmp_path)[0].returncode == 64
    assert run(["bad name", "--", "true"], tmp_path)[0].returncode == 64
    assert run(["ok"], tmp_path)[0].returncode == 64
