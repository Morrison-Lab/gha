"""Tests for check-pr-size (gha#1188). Fixture repos are built in tmp_path."""
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = ROOT / "check-pr-size.py"
spec = importlib.util.spec_from_file_location("check_pr_size", SCRIPT)
cps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cps)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})


def make_repo(tmp_path, files):
    """Commit a base, then add `files` ({path: line count}) on top."""
    git(tmp_path, "init", "-q")
    (tmp_path / "base.txt").write_text("base\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    for path, n in files.items():
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(f"line {i}\n" for i in range(n)))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "change")
    return tmp_path


def run(repo, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("PRS_")}
    e.update({"PRS_BASE_REF": "HEAD^1"})
    e.update(env)
    p = subprocess.run([sys.executable, str(SCRIPT)], cwd=repo, env=e,
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def test_small_pr_passes(tmp_path):
    repo = make_repo(tmp_path, {"a.qmd": 20, "b.qmd": 20})
    code, out = run(repo)
    assert code == 0
    assert "2 file(s), 40 changed line(s)" in out


def test_sweep_over_file_cap_fails(tmp_path):
    """Regression: a pds#244-style sweep touching many files, a few lines each."""
    repo = make_repo(tmp_path, {f"chapters/c{i}.qmd": 2 for i in range(25)})
    code, out = run(repo)
    assert code == 1
    assert "25 files changed (cap 10)" in out
    assert "minimal batches" in out


def test_over_line_cap_fails(tmp_path):
    repo = make_repo(tmp_path, {"big.qmd": 500})
    code, out = run(repo)
    assert code == 1
    assert "500 lines changed (cap 300)" in out


def test_exactly_at_cap_passes(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 30 for i in range(10)})
    code, _ = run(repo)
    assert code == 0


def test_one_over_cap_fails(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 1 for i in range(11)})
    code, _ = run(repo)
    assert code == 1


def test_builtin_ignores_are_not_counted(tmp_path):
    files = {f"_freeze/p{i}/x.json": 100 for i in range(30)}
    files["renv.lock"] = 900
    files["a.qmd"] = 5
    repo = make_repo(tmp_path, files)
    code, out = run(repo)
    assert code == 0
    assert "1 file(s), 5 changed line(s)" in out


def test_paths_ignore_exempts_a_directory(tmp_path):
    repo = make_repo(tmp_path, {f"gen/g{i}.qmd": 5 for i in range(20)})
    assert run(repo)[0] == 1
    assert run(repo, PRS_PATHS_IGNORE="gen/**")[0] == 0


def test_exempt_label_lifts_the_cap(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(40)})
    code, out = run(repo, PRS_EXEMPT="true")
    assert code == 0
    assert "exemption label" in out


def test_fail_false_warns_without_blocking(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(40)})
    code, out = run(repo, PRS_FAIL="false")
    assert code == 0
    assert "::warning::This PR is too large" in out


def test_no_base_ref_skips(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(40)})
    code, out = run(repo, PRS_BASE_REF="")
    assert code == 0
    assert "skipping" in out


def test_unresolvable_base_ref_skips(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(40)})
    code, out = run(repo, PRS_BASE_REF="no-such-ref")
    assert code == 0
    assert "skipping" in out


def test_invalid_cap_is_an_error(tmp_path):
    repo = make_repo(tmp_path, {"a.qmd": 1})
    code, out = run(repo, PRS_MAX_FILES="ten")
    assert code == 2
    assert "PRS_MAX_FILES" in out


def test_custom_caps(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(5)})
    assert run(repo, PRS_MAX_FILES="4")[0] == 1
    assert run(repo, PRS_MAX_FILES="5")[0] == 0


def test_binary_file_counts_as_a_file_with_no_lines(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "base.txt").write_text("base\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "bin")
    code, out = run(tmp_path)
    assert code == 0
    assert "1 file(s), 0 changed line(s)" in out


def test_parse_numstat_handles_renames():
    rows = cps.parse_numstat("3\t1\tdir/{old.qmd => new.qmd}\n-\t-\timg.bin\n")
    assert rows == [("dir/new.qmd", 4), ("img.bin", 0)]


def test_glob_to_regex_recursive():
    r = cps.glob_to_regex("_freeze/**")
    assert r.match("_freeze/a/b/c.json")
    assert not r.match("src/_freeze/a")
    r2 = cps.glob_to_regex("**/*.png")
    assert r2.match("a/b/c.png") and r2.match("c.png")


def _default(path, key):
    """First `default:` after the line `<key>:` (a line scan, no YAML library)."""
    lines = path.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == f"{key}:")
    for line in lines[start + 1:]:
        m = re.match(r"\s+default: '(\d+)'", line)
        if m:
            return m.group(1)
        assert not re.match(r"\s{0,6}[a-z-]+:\s*$", line) or line.strip().startswith(("description", "type")), \
            f"no default for {key} in {path}"
    raise AssertionError(f"{key} default not found in {path}")


@pytest.mark.parametrize("name,expected", [("max-files", cps.DEFAULT_MAX_FILES),
                                           ("max-lines", cps.DEFAULT_MAX_LINES)])
def test_defaults_agree_across_script_action_and_workflow(name, expected):
    """The gha#303 precedent: one default, declared three times, must agree."""
    action = ROOT / "action.yml"
    workflow = ROOT.parent / ".github" / "workflows" / "check-pr-size.yml"
    assert int(_default(action, name)) == expected
    assert int(_default(workflow, name)) == expected
