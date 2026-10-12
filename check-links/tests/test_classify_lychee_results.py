"""Tests for check-links/classify-lychee-results.py (gha#1052).

The lychee report is a canned JSON file in the shape lychee 0.24.2 writes
with ``--format json``, measured against a local server returning 404, 500,
503 and a timeout: ``errors`` and ``timeouts`` count disjoint failures, and
each input keeps the path it was given (absolute stays absolute). Nothing
here touches the network. Diff-scoped cases build a throwaway git
repository in tmp_path; nothing is committed to this repo.
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
        "timeouts": sum(len(v) for v in (timeouts or {}).values()),
        "error_map": errors or {},
        "timeout_map": timeouts or {},
    }


def run(tmp_path, rep, exit_code=2, base_ref="", fail="true",
        fail_if_empty="false", cwd=None, unset_base_ref=False, output=None):
    report_path = tmp_path / "lychee.json"
    report_path.write_text(json.dumps(rep) if isinstance(rep, dict) else rep)
    summary = tmp_path / "summary.md"
    if summary.exists():
        summary.unlink()
    env = dict(os.environ)
    env.update(
        LYCHEE_JSON=str(report_path),
        LYCHEE_EXIT=str(exit_code),
        LINKS_BASE_REF=base_ref,
        LINKS_FAIL=fail,
        LINKS_FAIL_IF_EMPTY=fail_if_empty,
        GITHUB_STEP_SUMMARY=str(summary),
    )
    # Never write to a real runner's step outputs from a test.
    env.pop("GITHUB_OUTPUT", None)
    if output is not None:
        env["GITHUB_OUTPUT"] = str(output)
    if unset_base_ref:
        del env["LINKS_BASE_REF"]
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, cwd=cwd or tmp_path,
        capture_output=True, text=True,
    )
    return proc, summary.read_text() if summary.exists() else ""


GH_503 = entry("https://github.com/Morrison-Lab/ai-config/blob/main/AGENTS.md", 503, 4)
DEAD_404 = entry("https://example.org/gone", 404, 7)


def test_untouched_503_with_an_empty_base_ref_is_a_warning(tmp_path):
    proc, summary = run(tmp_path, report({"./AGENTS.md": [GH_503]}))
    assert proc.returncode == 0, proc.stdout
    assert "::warning file=AGENTS.md,line=4::[503]" in proc.stdout
    assert "::error" not in proc.stdout
    assert "1 demoted 5xx" in summary


def test_counts_are_written_as_step_outputs(tmp_path):
    out = tmp_path / "github_output"
    run(tmp_path, report({"README.md": [DEAD_404], "AGENTS.md": [GH_503]}), output=out)
    assert out.read_text() == "blocking=1\ndemoted=1\n"


def test_an_unset_base_ref_blocks_every_5xx(tmp_path):
    proc, _ = run(tmp_path, report({"AGENTS.md": [GH_503]}), unset_base_ref=True)
    assert proc.returncode == 1
    assert "::error file=AGENTS.md,line=4::[503]" in proc.stdout


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
    assert proc.returncode == 2
    assert "refusing to call the run clean" in proc.stdout


def test_listed_failures_with_a_clean_exit_are_unusable(tmp_path):
    proc, _ = run(tmp_path, report({"README.md": [DEAD_404]}), exit_code=0)
    assert proc.returncode == 2


def test_a_demoted_5xx_does_not_hide_an_unlisted_failure(tmp_path):
    rep = report({"AGENTS.md": [GH_503]})
    rep["errors"] = 2  # lychee counted a failure the map does not list
    proc, _ = run(tmp_path, rep)
    assert proc.returncode == 2
    assert "counts 2 error(s) and timeout(s) but lists 1" in proc.stdout


@pytest.mark.parametrize("key", ["errors", "timeouts", "total"])
def test_missing_counts_are_unusable(tmp_path, key):
    rep = report({"AGENTS.md": [GH_503]})
    del rep[key]
    proc, _ = run(tmp_path, rep)
    assert proc.returncode == 2
    assert f"'{key}' count is missing" in proc.stdout


def test_missing_total_is_not_a_pass_under_fail_if_empty(tmp_path):
    rep = report()
    rep["total"] = None
    proc, _ = run(tmp_path, rep, exit_code=0, fail_if_empty="true")
    assert proc.returncode == 2


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


def scoped_report(old_key="./old.md", new_key="./new.md"):
    return report({
        old_key: [entry("https://down.example/old", 503, 2)],
        new_key: [entry("https://down.example/new", 502, 2)],
    })


def test_5xx_on_an_added_line_blocks_and_an_untouched_one_warns(tmp_path, repo):
    proc, _ = run(tmp_path, scoped_report(), base_ref="main", cwd=repo)
    assert proc.returncode == 1
    assert "::error file=new.md,line=2::[502]" in proc.stdout
    assert "::warning file=old.md,line=2::[503]" in proc.stdout


def test_an_absolute_report_key_is_matched_against_the_diff(tmp_path, repo):
    rep = scoped_report(str(repo / "old.md"), str(repo / "new.md"))
    proc, _ = run(tmp_path, rep, base_ref="main", cwd=repo)
    assert proc.returncode == 1
    warnings = [l for l in proc.stdout.splitlines() if l.startswith("::warning")]
    errors = [l for l in proc.stdout.splitlines() if l.startswith("::error")]
    assert len(warnings) == 1 and "file=old.md,line=2::[503]" in warnings[0]
    assert len(errors) == 1 and "new.md,line=2::[502]" in errors[0]


def test_a_key_relative_to_a_subdirectory_is_matched(tmp_path, repo):
    sub = repo / "docs"
    sub.mkdir()
    (sub / "page.md").write_text("x https://down.example/page\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "page")
    added = report({"page.md": [entry("https://down.example/page", 503, 1)]})
    proc, summary = run(tmp_path, added, base_ref="main", cwd=sub)
    assert proc.returncode == 1, proc.stdout  # docs/page.md line 1 is added
    # The annotation and the summary name the file from the repository root.
    assert "::error file=docs/page.md,line=1::[503]" in proc.stdout
    assert "- `docs/page.md`: [503]" in summary
    untouched = report({"../old.md": [entry("https://down.example/old", 503, 2)]})
    proc, summary = run(tmp_path, untouched, base_ref="main", cwd=sub)
    assert proc.returncode == 0, proc.stdout
    assert "::warning file=old.md,line=2::[503]" in proc.stdout
    assert "- `old.md`: [503]" in summary


@pytest.mark.parametrize("key, shown", [
    ("https://example.org/page.md", "https%3A//example.org/page.md"),
    ("stdin", "stdin"),
    ("/elsewhere/a.md", "/elsewhere/a.md"),  # outside the repository
])
def test_a_report_key_that_is_not_a_repo_file_is_kept_as_given(tmp_path, repo, key, shown):
    sub = repo / "docs"
    sub.mkdir()
    rep = report({key: [entry("https://example.org/gone", 404, 3)]})
    proc, summary = run(tmp_path, rep, base_ref="all", cwd=sub)
    assert proc.returncode == 1, proc.stdout
    assert f"::error file={shown},line=3::[404]" in proc.stdout
    assert f"- `{key}`: [404]" in summary


def test_file_property_and_summary_survive_awkward_names(tmp_path):
    rep = report({"a,b:c`d.md": [entry("https://example.org/gone", 404, 1)]})
    proc, summary = run(tmp_path, rep, base_ref="all")  # tmp_path is no git repo
    assert proc.returncode == 1, proc.stdout
    assert "::error file=a%2Cb%3Ac`d.md,line=1::[404]" in proc.stdout
    assert "- `` a,b:c`d.md ``: [404]" in summary


@pytest.mark.parametrize("key", ["untracked.md", "/elsewhere/a.md"])
def test_a_5xx_in_a_file_git_does_not_know_blocks(tmp_path, repo, key):
    (repo / "untracked.md").write_text("x\n")
    rep = report({key: [entry("https://down.example/u", 503, 1)]})
    proc, _ = run(tmp_path, rep, base_ref="main", cwd=repo)
    assert proc.returncode == 1, proc.stdout


def test_5xx_on_an_unchanged_line_of_a_changed_file_warns(tmp_path, repo):
    rep = report({"new.md": [entry("https://down.example/first", 503, 1)]})
    proc, _ = run(tmp_path, rep, base_ref="main", cwd=repo)
    assert proc.returncode == 0, proc.stdout


def test_unresolvable_base_ref_falls_back_to_every_5xx_blocking(tmp_path, repo):
    proc, _ = run(tmp_path, scoped_report(), base_ref="no-such-ref", cwd=repo)
    assert proc.returncode == 1
    assert "cannot diff against base-ref 'no-such-ref'" in proc.stdout
    assert "::error file=old.md,line=2::[503]" in proc.stdout


def test_action_and_workflow_wire_the_base_ref_input():
    root = SCRIPT.parents[1]
    action = (root / "check-links" / "action.yml").read_text()
    workflow = (root / ".github" / "workflows" / "check-links.yml").read_text()
    # Direct callers keep lychee's blocking behaviour; only the workflow opts in.
    block = action.split("  base-ref:\n", 1)[1].split("\nruns:", 1)[0]
    assert "default: 'all'" in block
    assert "LINKS_BASE_REF: ${{ inputs.base-ref }}" in action
    assert "fail: false" in action  # the script, not lychee-action, decides
    assert "base-ref: ${{" in workflow and "fetch-depth: 2" in workflow
