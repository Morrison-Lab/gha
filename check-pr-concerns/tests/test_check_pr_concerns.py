"""Tests for check-pr-concerns (gha#1188). Fixture repos are built in tmp_path."""
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = ROOT / "check-pr-concerns.py"
spec = importlib.util.spec_from_file_location("check_pr_concerns", SCRIPT)
cpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpc)

DEFAULTS = (
    cpc.compile_all(cpc.DEFAULT_CONTENT),
    cpc.compile_all(cpc.DEFAULT_INFRA),
    cpc.compile_all(cpc.BUILTIN_IGNORE),
)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",  # phi-allow
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})  # phi-allow


def make_repo(tmp_path, files):
    """Commit a base, then add `files` on top."""
    git(tmp_path, "init", "-q")
    (tmp_path / "base.txt").write_text("base\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    for path in files:
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "change")
    return tmp_path


def run(repo, **env):
    full = {k: v for k, v in os.environ.items() if not k.startswith("PRC_")}
    full.update(env)
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=repo, env=full,
                          capture_output=True, text=True)


def kinds(paths):
    return cpc.classify(paths, *DEFAULTS)


def test_content_only_has_no_infra():
    content, infra = kinds(["chapters/a.qmd", "chapters/_subfiles/a/_x.qmd", "notes.Rmd"])
    assert len(content) == 3 and infra == []


def test_infra_only_has_no_content():
    content, infra = kinds([".github/workflows/x.yml", "tools/check.py", "_quarto.yml",
                            "sub/_quarto-website.yml", ".claude/settings.json"])
    assert content == [] and len(infra) == 5


def test_infra_wins_an_overlap():
    content, infra = kinds([".github/ISSUE_TEMPLATE/a.qmd", "tools/notes.qmd"])
    assert content == [] and len(infra) == 2


def test_ignored_paths_count_as_neither():
    content, infra = kinds(["renv.lock", "_freeze/a/x.json", "docs/a.html",
                            "changelog.d/x.added.md", "chapters/_freeze/y.json"])
    assert content == [] and infra == []


def test_unclassified_paths_count_as_neither():
    assert kinds(["README.md", "references.bib", "images/a.png"]) == ([], [])


def test_parse_names_takes_the_new_name_of_a_rename():
    assert cpc.parse_names("R100\told.qmd\ttools/new.qmd\nM\ta.py\n") == ["tools/new.qmd", "a.py"]


def test_mixed_pr_fails(tmp_path):
    repo = make_repo(tmp_path, ["chapters/a.qmd", "tools/check.py"])
    r = run(repo, PRC_BASE_REF="HEAD^1")
    assert r.returncode == 1
    assert "::error::" in r.stdout and "chapters/a.qmd" in r.stdout and "tools/check.py" in r.stdout


def test_content_only_pr_passes(tmp_path):
    repo = make_repo(tmp_path, ["chapters/a.qmd", "chapters/b.qmd", "README.md"])
    r = run(repo, PRC_BASE_REF="HEAD^1")
    assert r.returncode == 0 and "::error" not in r.stdout


def test_infra_only_pr_passes(tmp_path):
    repo = make_repo(tmp_path, [".github/workflows/a.yml", "scripts/b.sh"])
    assert run(repo, PRC_BASE_REF="HEAD^1").returncode == 0


def test_exempt_label_lets_a_mixed_pr_pass(tmp_path):
    repo = make_repo(tmp_path, ["chapters/a.qmd", "tools/check.py"])
    r = run(repo, PRC_BASE_REF="HEAD^1", PRC_EXEMPT="true")
    assert r.returncode == 0 and "exemption label" in r.stdout


def test_fail_false_warns_without_blocking(tmp_path):
    repo = make_repo(tmp_path, ["chapters/a.qmd", "tools/check.py"])
    r = run(repo, PRC_BASE_REF="HEAD^1", PRC_FAIL="false")
    assert r.returncode == 0 and "::warning::This PR mixes" in r.stdout


def test_paths_ignore_removes_the_mix(tmp_path):
    repo = make_repo(tmp_path, ["chapters/a.qmd", "tools/check.py"])
    assert run(repo, PRC_BASE_REF="HEAD^1", PRC_PATHS_IGNORE="tools/**").returncode == 0


def test_custom_infra_paths_replace_the_defaults(tmp_path):
    repo = make_repo(tmp_path, ["chapters/a.qmd", "tools/check.py"])
    assert run(repo, PRC_BASE_REF="HEAD^1", PRC_INFRA_PATHS="ops/**").returncode == 0


def test_custom_infra_paths_still_catch_a_mix(tmp_path):
    repo = make_repo(tmp_path, ["chapters/a.qmd", "ops/run.sh"])
    assert run(repo, PRC_BASE_REF="HEAD^1", PRC_INFRA_PATHS="ops/**").returncode == 1


def test_no_base_skips_instead_of_scanning_everything(tmp_path):
    repo = make_repo(tmp_path, ["chapters/a.qmd", "tools/check.py"])
    r = run(repo)
    assert r.returncode == 0 and "skipping" in r.stdout


def test_unresolvable_base_skips(tmp_path):
    repo = make_repo(tmp_path, ["chapters/a.qmd", "tools/check.py"])
    r = run(repo, PRC_BASE_REF="no-such-ref")
    assert r.returncode == 0 and "skipping" in r.stdout


def test_base_before_head_sees_only_the_last_commit(tmp_path):
    """Diffing HEAD~1 against HEAD sees only the last commit."""
    repo = make_repo(tmp_path, ["chapters/a.qmd"])
    r = run(repo, PRC_BASE_REF="HEAD~1")
    assert r.returncode == 0


def _default(path, key):
    """Read `key`'s default from an action or workflow YAML by line scan."""
    lines = Path(path).read_text().splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"\s+{re.escape(key)}:\s*$", line):
            for later in lines[i + 1:i + 8]:
                m = re.match(r"\s+default:\s*(.*)$", later)
                if m:
                    return m.group(1).strip().strip("'\"")
                if re.match(r"\s+\S+:\s*$", later):
                    break
    raise AssertionError(f"no default for {key} in {path}")


@pytest.mark.parametrize("key,expected", [("exempt", "false"), ("fail", "true"), ("base-ref", "")])
def test_action_defaults(key, expected):
    assert _default(ROOT / "action.yml", key) == expected


def test_workflow_defaults_agree_with_the_action():
    wf = ROOT.parent / ".github" / "workflows" / "check-pr-concerns.yml"
    assert _default(wf, "exempt-label") == "mixed-ok"
    assert _default(wf, "fail") == "true"
    for key in ("content-paths", "infra-paths", "paths-ignore"):
        assert _default(wf, key) == _default(ROOT / "action.yml", key) == ""
