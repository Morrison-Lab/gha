"""Tests for check-notes-plan (gha#1367)."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "plan.py"
spec = importlib.util.spec_from_file_location("plan", SCRIPT)
plan_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan_mod)

DEFAULTS = {"check-a": True, "check-b": False, "check-c": True}


def test_plan_keeps_each_default():
    skip, fail = plan_mod.plan(DEFAULTS, [], [], [])
    assert skip == []
    assert fail == {"check-a": "true", "check-b": "false", "check-c": "true"}


def test_plan_overrides_and_skip():
    skip, fail = plan_mod.plan(DEFAULTS, ["check-c"], ["check-b"], ["check-a"])
    assert skip == ["check-c"]
    assert fail["check-a"] == "false" and fail["check-b"] == "true"


def test_plan_all_warns_everything():
    _, fail = plan_mod.plan(DEFAULTS, [], [], ["all"])
    assert set(fail.values()) == {"false"}


def test_plan_all_fails_everything():
    _, fail = plan_mod.plan(DEFAULTS, [], ["all"], [])
    assert set(fail.values()) == {"true"}


@pytest.mark.parametrize("skip,fail_checks,warn_checks,needle", [
    (["check-typo"], [], [], "skip names checks"),
    ([], ["check-typo"], [], "fail-checks names checks"),
    ([], [], ["check-typo"], "warn-checks names checks"),
    ([], ["check-a"], ["check-a"], "both"),
    ([], ["all"], ["check-b"], "both"),
    (["all"], [], [], "skip does not take"),
])
def test_plan_refuses(skip, fail_checks, warn_checks, needle):
    with pytest.raises(ValueError, match=needle):
        plan_mod.plan(DEFAULTS, skip, fail_checks, warn_checks)


def test_split_names_accepts_commas_spaces_newlines():
    assert plan_mod.split_names("a, b\nc  d,") == ["a", "b", "c", "d"]
    assert plan_mod.split_names(None) == []


def run_main(tmp_path, **env):
    out = tmp_path / "out"
    out.write_text("")
    full = {**os.environ, "GITHUB_OUTPUT": str(out),
            "DEFAULTS": json.dumps(DEFAULTS), **env}
    result = subprocess.run([sys.executable, str(SCRIPT)], env=full,
                            capture_output=True, text=True)
    return result, out.read_text()


def test_main_writes_outputs(tmp_path):
    result, out = run_main(tmp_path, SKIP="check-c", WARN_CHECKS="check-a")
    assert result.returncode == 0, result.stderr
    assert 'skip=["check-c"]' in out
    assert json.loads(out.split("fail=", 1)[1])["check-a"] == "false"
    assert "Running 2 of 3 checks." in result.stdout


def test_main_refuses_a_typo_and_writes_nothing(tmp_path):
    result, out = run_main(tmp_path, SKIP="check-x")
    assert result.returncode == 2
    assert "::error::" in result.stdout and "check-x" in result.stdout
    assert out == ""
