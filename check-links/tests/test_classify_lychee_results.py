"""Tests for check-links/classify-lychee-results.py (gha#1052).

The lychee report is a canned JSON file in the shape lychee 0.24.2 writes
with ``--format json`` (measured against a local server returning 404, 500
and 503), so nothing here touches the network. Diff-scoped cases build a
throwaway git repository in tmp_path; nothing is committed to this repo.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "classify-lychee-results.py"


def entry(url, code, line, text=None):
    status = {"text": text or f"Rejected status code: {code}"}
    if code is not None:
        status["code"] = code
    return {"url": url, "status": status, "span": {"line": line, "column": 1}}


def report(errors=None, timeouts=None, total=3):
    return {
        "total": total,
        "errors": sum(len(v) for v in (errors or {}).values()),
        "error_map": errors or {},
        "timeout_map": timeouts or {},
    }


def run(tmp_path, rep, exit_code=2, base_ref="", fail="true",
        fail_if_empty="false", cwd=None):
    report_path = tmp_path / "lychee.json"
    report_path.write_text(json.dumps(rep) if isinstance(rep, dict) else rep)
    summary = tmp_path / "summary.md"
    env = dict(os.environ)
    env.update(
        LYCHEE_JSON=str(report_path),
        LYCHEE_EXIT=str(exit_code),
        LINKS_BASE_REF=base_ref,
        LINKS_FAIL=fail,
        LINKS_FAIL_IF_EMPTY=fail_if_empty,
        GITHUB_STEP_SUMMARY=str(summary),
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, cwd=cwd or tmp_path,
        capture_output=True, text=True,
    )
    return proc, summary.read_text() if summary.exists() else ""


GH_503 = entry("https://github.com/Morrison-Lab/ai-config/blob/main/AGENTS.md", 503, 4)
DEAD_404 = entry("https://example.org/gone", 404, 7)


def test_untouched_503_is_a_warning_not_a_failure(tmp_path):
    proc, summary = run(tmp_path, report({"./AGENTS.md": [GH_503]}))
    assert proc.returncode == 0, proc.stdout
    assert "::warning file=AGENTS.md,line=4::[503]" in proc.stdout
    assert "::error" not in proc.stdout
    assert "1 demoted 5xx" in summary


def test_404_still_fails_alongside_a_demoted_503(tmp_path):
    proc, _ = run(tmp_path, report({"README.md": [DEAD_404], "AGENTS.md": [GH_503]}))
    assert proc.returncode == 1
    assert "::error file=README.md,line=7::[404] https://example.org/gone" in proc.stdout
    assert "::warning file=AGENTS.md,line=4::[503]" in proc.stdout


def test_network_error_without_a_code_still_fails(tmp_path):
    e = entry("https://nowhere.invalid/", None, 2, text="Network error: dns")
    proc, _ = run(tmp_path, report({"a.md": [e]}))
    assert proc.returncode == 1
    assert "::error file=a.md,line=2::https://nowhere.invalid/" in proc.stdout


def test_timeout_still_fails(tmp_path):
    proc, _ = run(tmp_path, report(timeouts={"a.md": [entry("https://slow.example/", None, 1)]}))
    assert proc.returncode == 1


def test_all_makes_every_5xx_block(tmp_path):
    proc, _ = run(tmp_path, report({"AGENTS.md": [GH_503]}), base_ref="all")
    assert proc.returncode == 1
    assert "::error file=AGENTS.md,line=4::[503]" in proc.stdout


def test_fail_false_never_fails_but_still_reports(tmp_path):
    proc, _ = run(tmp_path, report({"README.md": [DEAD_404]}), fail="false")
    assert proc.returncode == 0
    assert "::error file=README.md" in proc.stdout


def test_clean_run_passes(tmp_path):
    proc, summary = run(tmp_path, report(), exit_code=0)
    assert proc.returncode == 0
    assert "0 blocking failure(s), 0 demoted" in summary


def test_lychee_tool_error_fails(tmp_path):
    proc, _ = run(tmp_path, report(), exit_code=1)
    assert proc.returncode == 1
    assert "tool or configuration error" in proc.stdout


def test_failures_with_an_empty_report_are_not_called_clean(tmp_path):
    proc, _ = run(tmp_path, report(), exit_code=2)
    assert proc.returncode == 1
    assert "refusing to call that clean" in proc.stdout


def test_unreadable_report_is_an_error(tmp_path):
    proc, _ = run(tmp_path, "| Status | Count |\n", exit_code=2)
    assert proc.returncode == 2
    assert "Remove any --format or --output" in proc.stdout


def test_fail_if_empty(tmp_path):
    proc, _ = run(tmp_path, report(total=0), exit_code=0, fail_if_empty="true")
    assert proc.returncode == 1
    proc, _ = run(tmp_path, report(total=0), exit_code=0)
    assert proc.returncode == 0


def test_annotation_data_is_escaped(tmp_path):
    e = entry("https://x.example/a%0Ab", 404, 1, text="bad\nline")
    proc, _ = run(tmp_path, report({"a.md": [e]}))
    assert "a%250Ab" in proc.stdout and "bad%0Aline" in proc.stdout


# ---------------------------------------------------------------- diff scope


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.invalid")  # phi-allow
    git(root, "config", "user.name", "t")
    (root / "old.md").write_text("one\ntwo https://down.example/old\n")
    (root / "new.md").write_text("first\n")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    git(root, "switch", "-q", "-c", "pr")
    (root / "new.md").write_text("first\nsecond https://down.example/new\n")
    git(root, "commit", "-qam", "pr")
    return root


def scoped_report():
    return report({
        "./old.md": [entry("https://down.example/old", 503, 2)],
        "./new.md": [entry("https://down.example/new", 502, 2)],
    })


def test_5xx_on_an_added_line_blocks_and_an_untouched_one_warns(tmp_path, repo):
    proc, _ = run(tmp_path, scoped_report(), base_ref="main", cwd=repo)
    assert proc.returncode == 1
    assert "::error file=new.md,line=2::[502]" in proc.stdout
    assert "::warning file=old.md,line=2::[503]" in proc.stdout


def test_5xx_on_an_unchanged_line_of_a_changed_file_warns(tmp_path, repo):
    rep = report({"new.md": [entry("https://down.example/first", 503, 1)]})
    proc, _ = run(tmp_path, rep, base_ref="main", cwd=repo)
    assert proc.returncode == 0, proc.stdout


def test_unresolvable_base_ref_falls_back_to_every_5xx_blocking(tmp_path, repo):
    proc, _ = run(tmp_path, scoped_report(), base_ref="no-such-ref", cwd=repo)
    assert proc.returncode == 1
    assert "cannot diff against base-ref 'no-such-ref'" in proc.stdout
    assert "::error file=old.md,line=2::[503]" in proc.stdout


def test_action_and_workflow_declare_the_base_ref_input():
    root = SCRIPT.parents[1]
    action = (root / "check-links" / "action.yml").read_text()
    workflow = (root / ".github" / "workflows" / "check-links.yml").read_text()
    assert "  base-ref:\n" in action
    assert "LINKS_BASE_REF: ${{ inputs.base-ref }}" in action
    assert "fail: false" in action  # the script, not lychee-action, decides
    assert "base-ref: ${{" in workflow and "fetch-depth: 2" in workflow
