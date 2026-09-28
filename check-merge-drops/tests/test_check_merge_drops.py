"""Unit tests for check-merge-drops.

Each case builds a small throwaway git repository (``tmp_path``; nothing is
committed here) holding one conflicting merge, resolves it a particular way,
and asserts what the check reports. The three resolutions the check exists to
tell apart are:

- keeping one side of the whole file, dropping the other side's paragraph
  (reported);
- a clean hunk-by-hunk resolution keeping both sides (not reported);
- the dropped paragraph moved to another file by the merge (not reported).

check-merge-drops.py isn't an importable module name (the hyphen), so load it
by path -- same pattern as check-new-line-breaks/tests.
"""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_MOD_PATH = _DIR / "check-merge-drops.py"
_spec = importlib.util.spec_from_file_location("check_merge_drops", _MOD_PATH)
assert _spec is not None and _spec.loader is not None, f"Could not load {_MOD_PATH}"
cmd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmd)

INTRO = "# Chapter\n\nThe opening paragraph of the chapter, shared by both sides.\n"
MAIN_PARA = (
    "Main adds a history paragraph about where this method came from,\n"
    "who first described it, and why it is still taught today.\n"
)
BRANCH_PARA = (
    "The branch adds a worked example that walks through the method\n"
    "step by step on a small data set.\n"
)
MAIN_LINE = "Main adds a history paragraph about where this method came from,"


def _git(repo: Path, *args: str, check: bool = True) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",  # phi-allow
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",  # phi-allow
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
    }
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=check, capture_output=True, text=True
    ).stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _conflicting_merge(repo: Path) -> str:
    """Branch and main each append a paragraph at the same spot; start the merge.

    Returns the base commit. Leaves the repo mid-merge on ``feature`` with
    ``chapter.qmd`` conflicted, for the caller to resolve and commit.
    """
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "chapter.qmd", INTRO)
    _write(repo, "notes.md", "# Notes\n\nNothing here yet, just a placeholder line.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-qb", "feature")
    _write(repo, "chapter.qmd", INTRO + "\n" + BRANCH_PARA)
    _git(repo, "commit", "-qam", "branch example")
    _git(repo, "checkout", "-q", "main")
    _write(repo, "chapter.qmd", INTRO + "\n" + MAIN_PARA)
    _git(repo, "commit", "-qam", "main history")
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "merge", "-q", "main", check=False)  # conflicts, by construction
    assert "chapter.qmd" in _git(repo, "diff", "--name-only", "--diff-filter=U")
    return base


def _commit_merge(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "Merge main into feature")


def _find(repo: Path, base: str, **kw):
    kw.setdefault("globs", ["*.md", "*.qmd"])
    kw.setdefault("ignores", [])
    kw.setdefault("min_length", cmd._DEFAULT_MIN_LENGTH)
    result = cmd.find_drops(base, "HEAD", cwd=str(repo), **kw)
    assert result is not None
    return result


# ── the three acceptance cases ───────────────────────────────────────────────

def test_one_sided_resolution_is_reported(tmp_path):
    base = _conflicting_merge(tmp_path)
    _git(tmp_path, "checkout", "--ours", "chapter.qmd")  # keep the branch's whole file
    _commit_merge(tmp_path)
    drops, examined, unreadable = _find(tmp_path, base)
    assert examined == 1 and unreadable == []
    assert len(drops) == 1
    drop = drops[0]
    assert drop.parent_index == 2 and drop.path == "chapter.qmd"
    assert MAIN_LINE in drop.lines
    assert len(drop.lines) == 2


def test_hunk_by_hunk_resolution_is_not_reported(tmp_path):
    base = _conflicting_merge(tmp_path)
    _write(tmp_path, "chapter.qmd", INTRO + "\n" + BRANCH_PARA + "\n" + MAIN_PARA)
    _commit_merge(tmp_path)
    drops, examined, _ = _find(tmp_path, base)
    assert examined == 1
    assert drops == []


def test_paragraph_moved_to_another_file_is_not_reported(tmp_path):
    base = _conflicting_merge(tmp_path)
    _git(tmp_path, "checkout", "--ours", "chapter.qmd")
    _write(tmp_path, "notes.md", "# Notes\n\n" + MAIN_PARA)
    _commit_merge(tmp_path)
    drops, _, _ = _find(tmp_path, base)
    assert drops == []


# ── what else must not be reported ───────────────────────────────────────────

def test_rewrapped_paragraph_is_not_reported(tmp_path):
    base = _conflicting_merge(tmp_path)
    rewrapped = " ".join(MAIN_PARA.split()).replace(" who first", "\nwho first")
    rewrapped = rewrapped.replace("method came", "method\ncame")
    _write(tmp_path, "chapter.qmd", INTRO + "\n" + BRANCH_PARA + "\n" + rewrapped + "\n")
    _commit_merge(tmp_path)
    drops, _, _ = _find(tmp_path, base)
    assert drops == []


def test_reworded_line_is_a_near_twin_unless_similarity_is_one(tmp_path):
    base = _conflicting_merge(tmp_path)
    reworded = MAIN_PARA.replace("history paragraph", "short history note")
    _write(tmp_path, "chapter.qmd", INTRO + "\n" + BRANCH_PARA + "\n" + reworded)
    _commit_merge(tmp_path)
    drops, _, _ = _find(tmp_path, base)
    assert drops == []
    drops, _, _ = _find(tmp_path, base, similarity=1.0)
    assert [d.lines for d in drops] == [[MAIN_LINE]]


def test_short_lines_are_skipped(tmp_path):
    base = _conflicting_merge(tmp_path)
    _git(tmp_path, "checkout", "--ours", "chapter.qmd")
    _commit_merge(tmp_path)
    drops, _, _ = _find(tmp_path, base, min_length=500)
    assert drops == []


def test_paths_ignore_and_globs_exclude_the_file(tmp_path):
    base = _conflicting_merge(tmp_path)
    _git(tmp_path, "checkout", "--ours", "chapter.qmd")
    _commit_merge(tmp_path)
    ignores = cmd.compile_ignores(["chapter.qmd"])
    assert _find(tmp_path, base, ignores=ignores)[0] == []
    assert _find(tmp_path, base, globs=["*.md"])[0] == []


def test_non_merge_commits_are_not_examined(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _write(tmp_path, "a.md", "A line long enough to be checked by the tool.\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "one")
    base = _git(tmp_path, "rev-parse", "HEAD")
    _write(tmp_path, "a.md", "")
    _git(tmp_path, "commit", "-qam", "delete it")
    drops, examined, _ = _find(tmp_path, base)
    assert (drops, examined) == ([], 0)


# ── main(): skips, exit codes, report ────────────────────────────────────────

def test_main_warns_only_by_default_and_fails_when_asked(tmp_path, capsys, monkeypatch):
    base = _conflicting_merge(tmp_path)
    _git(tmp_path, "checkout", "--ours", "chapter.qmd")
    _commit_merge(tmp_path)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert cmd.main(["--base", base, "-C", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "::warning title=Merge dropped content::" in out
    assert MAIN_LINE in summary.read_text()
    assert cmd.main(["--base", base, "-C", str(tmp_path), "--fail"]) == 1
    assert "::error title=Merge dropped content::" in capsys.readouterr().out


def test_main_env_fail_true_blocks(tmp_path, monkeypatch):
    base = _conflicting_merge(tmp_path)
    _git(tmp_path, "checkout", "--ours", "chapter.qmd")
    _commit_merge(tmp_path)
    monkeypatch.setenv("MERGE_DROPS_FAIL", "true")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert cmd.main(["--base", base, "-C", str(tmp_path)]) == 1


@pytest.mark.parametrize("base", ["", "0000000000000000000000000000000000000000"])
def test_main_skips_without_a_base(base, capsys, monkeypatch):
    monkeypatch.delenv("MERGE_DROPS_BASE_REF", raising=False)
    assert cmd.main(["--base", base]) == 0
    assert "::warning::Skipping the merge-drops check" in capsys.readouterr().out


def test_main_skips_an_unknown_base(tmp_path, capsys):
    _git(tmp_path, "init", "-q", "-b", "main")
    assert cmd.main(["--base", "no-such-ref", "-C", str(tmp_path)]) == 0
    assert "could not list merges" in capsys.readouterr().out


# ── diff parsing ─────────────────────────────────────────────────────────────

def test_added_line_starting_with_plus_plus_space_is_content_not_a_header():
    diff = (
        "diff --git a/x.md b/x.md\n"
        "--- a/x.md\n"
        "+++ b/x.md\n"
        "@@ -0,0 +1,2 @@\n"
        "+++ looks like a header but is content\n"
        "+second line\n"
    )
    assert cmd.parse_added_lines(diff) == {
        "x.md": ["++ looks like a header but is content", "second line"]
    }


def test_deleted_file_contributes_no_added_lines():
    diff = "diff --git a/x.md b/x.md\n--- a/x.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-gone\n"
    assert cmd.parse_added_lines(diff) == {}


# ── defaults agree across the script and both YAML files ─────────────────────

def _yaml_default(path: Path, name: str) -> str:
    """Read ``name``'s ``default:`` with a line scan (only pytest is installed in CI)."""
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f"{name}:":
            indent = len(line) - len(line.lstrip())
            for follow in lines[i + 1:]:
                if follow.strip() and len(follow) - len(follow.lstrip()) <= indent:
                    break
                if follow.strip().startswith("default:"):
                    return follow.split("default:", 1)[1].strip().strip("'\"")
    raise AssertionError(f"{path}: no default for {name}")


@pytest.mark.parametrize("path", [
    _DIR / "action.yml",
    _DIR.parent / ".github" / "workflows" / "check-merge-drops.yml",
])
def test_yaml_defaults_agree_with_the_script(path):
    assert _yaml_default(path, "globs") == cmd._DEFAULT_GLOBS
    assert _yaml_default(path, "min-length") == str(cmd._DEFAULT_MIN_LENGTH)
    assert float(_yaml_default(path, "similarity")) == cmd._DEFAULT_SIMILARITY
    assert _yaml_default(path, "fail") == str(cmd._DEFAULT_FAIL).lower()
