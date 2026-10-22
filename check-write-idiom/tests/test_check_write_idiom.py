r"""Unit tests for check-write-idiom.

Covers what counts as a finding (a line opening with "Write the", "Write a" or
"Write an", after an optional list marker and label), what is not (notation,
"Write down", mid-line use), what is skipped (code fences and spans, comments,
front matter), the diff scoping including moved lines, main()'s exit codes,
and the defaults the action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_write_idiom", _DIR / "check-write-idiom.py"
)
assert _spec is not None and _spec.loader is not None
wi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wi)


def found(text: str):
    """{line number: phrase} for a document given as one string."""
    hits, _ = wi.scan_file(text.split("\n"))
    return {h.line: h.phrase for h in hits}


# -- findings ----------------------------------------------------------------

@pytest.mark.parametrize("text, phrase", [
    ("Write the likelihood.", "Write the"),
    ("Write a function that returns the mean.", "Write a"),
    ("Write an expression for the risk.", "Write an"),
    ("  Write the likelihood.", "Write the"),
    ("- Write the likelihood.", "Write the"),
    ("* Write the likelihood.", "Write the"),
    ("1. Write the likelihood.", "Write the"),
    ("12) Write the likelihood.", "Write the"),
    ("(a) Write the likelihood.", "Write the"),
    ("a) Write the likelihood.", "Write the"),
    ("- (b) Write an estimator.", "Write an"),
    ("1. a) Write a bound.", "Write a"),
    ("(a)Write the likelihood.", "Write the"),
])
def test_flagged_forms(text, phrase):
    assert found(text) == {1: phrase}


@pytest.mark.parametrize("text", [
    "Write $\\hat\\beta$ for the estimate.",
    "Write $x$ for the data.",
    "Write down the likelihood.",
    "Write this down.",
    "Writer the likelihood.",
    "Writes the likelihood.",
    "write the likelihood.",
    "WRITE the likelihood.",
    "Rewrite the likelihood.",
    "Please write the likelihood.",
    "First, Write the likelihood.",
    "Write the",
    "Write",
    "Derive the likelihood.",
])
def test_unflagged_forms(text):
    assert found(text) == {}


def test_each_line_is_found_with_its_number():
    text = "Intro.\n\n1. Write the a.\n2. State b.\n3. Write an c."
    assert found(text) == {3: "Write the", 5: "Write an"}


def test_message_names_the_alternatives_and_the_source():
    msg = wi.format_message(wi.Finding(1, "Write the"))
    assert msg == (
        '"Write ..." means derive, express, state or give here; name the '
        'action literally ("Derive an expression for", "Express", "State", '
        '"Give") (psw#297).')


# -- skips -------------------------------------------------------------------

def test_code_fence_is_skipped():
    assert found("```r\nWrite the x\n```") == {}


def test_tilde_fence_is_skipped_and_text_after_is_scanned():
    assert found("~~~\nWrite the x\n~~~\nWrite the y") == {4: "Write the"}


def test_code_span_is_skipped():
    assert found("`Write the` likelihood.") == {}


def test_html_comment_is_skipped():
    assert found("<!-- Write the likelihood. -->") == {}


def test_multiline_html_comment_is_skipped():
    text = "<!--\nWrite the x\n-->\nWrite the y"
    assert found(text) == {4: "Write the"}


def test_front_matter_is_skipped():
    assert found("---\ntitle: Write the x\n---\nbody") == {}


def test_allow_comment_on_the_line_or_the_line_before():
    allow = "<!-- check-write-idiom: allow -->"
    assert found(f"Write the x. {allow}") == {}
    assert found(f"{allow}\nWrite the x.") == {}
    assert found(f"{allow}\n\nWrite the x.") == {3: "Write the"}


# -- diff scoping, over throwaway git repos ----------------------------------

def _repo(tmp_path):
    """A git repo with one commit; returns its path and a git runner."""
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")  # phi-allow
    git("config", "user.name", "t")
    (tmp_path / "README.md").write_text("base\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    return tmp_path, git


def _run(monkeypatch, tmp_path, base, **kw):
    monkeypatch.chdir(tmp_path)
    return wi.run_check(
        base, kw.get("globs", wi.DEFAULT_GLOBS.split()),
        wi.compile_globs(kw.get("ignores", [])), kw.get("whole_tree", False))


def test_added_line_is_flagged_in_diff_mode(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("Write the x.\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD")
    assert [(r, f.line) for r, f in report.findings] == [("page.qmd", 1)]


def test_existing_use_is_not_reflagged(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("Write the x.\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    (repo / "new.qmd").write_text("Write the y.\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD")
    assert [r for r, _ in report.findings] == ["new.qmd"]


def test_only_added_lines_of_a_changed_file_are_flagged(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "a.qmd").write_text("Write the old.\nprose\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    (repo / "a.qmd").write_text("Write the old.\nprose\nWrite a new.\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD")
    assert [(f.line, f.phrase) for _, f in report.findings] == [(3, "Write a")]


def test_moved_line_is_not_flagged(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("Write the x.\nprose\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    (repo / "old.qmd").write_text("prose\nWrite the x.\n")
    git("add", "-A")
    assert _run(monkeypatch, repo, "HEAD").findings == []


def test_whole_tree_flags_existing_uses(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("Write the x.\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    assert len(_run(monkeypatch, repo, "", whole_tree=True).findings) == 1


@pytest.mark.parametrize("base", ["", "no-such-ref"])
def test_unusable_base_skips_instead_of_falling_back(tmp_path, monkeypatch, base):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("Write the x.\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    report = _run(monkeypatch, repo, base)
    assert report.skipped and report.findings == []


def test_other_extensions_are_not_read(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "notes.txt").write_text("Write the x.\n")
    (repo / "page.Rmd").write_text("Write the x.\n")
    git("add", "-A")
    assert _run(monkeypatch, repo, "HEAD").findings == []


def test_md_files_are_read(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "notes.md").write_text("- (a) Write an x.\n")
    git("add", "-A")
    assert len(_run(monkeypatch, repo, "HEAD").findings) == 1


def test_paths_ignore_skips_a_file(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "skip.qmd").write_text("Write the x.\n")
    git("add", "-A")
    assert _run(monkeypatch, repo, "HEAD", ignores=["skip.qmd"]).findings == []


def test_report_counts_the_search_space(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "a.qmd").write_text("prose\nWrite the x.\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD")
    assert (report.files, report.lines) == (1, 2)


# -- main(): the exit code ---------------------------------------------------

def _main_env(monkeypatch, repo, **extra):
    monkeypatch.chdir(repo)
    for key in ("CWI_BASE_REF", "CWI_GLOBS", "CWI_PATHS_IGNORE", "CWI_FAIL",
                "CWI_WHOLE_TREE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CWI_BASE_REF", "HEAD")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_main_warns_by_default_and_fails_on_request(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("prose\nWrite the x.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo)
    assert wi.main() == 0
    out = capsys.readouterr().out
    assert "::warning file=page.qmd,line=2::" in out
    assert "(psw#297)" in out
    monkeypatch.setenv("CWI_FAIL", "true")
    assert wi.main() == 1
    assert "::error file=page.qmd,line=2::" in capsys.readouterr().out


def test_main_passes_notation_and_write_down(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text(
        "Write $x$ for the data.\nWrite down the answer.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CWI_FAIL="true")
    assert wi.main() == 0
    assert "No line opens" in capsys.readouterr().out


def test_main_without_base_skips_even_when_failing(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("Write the x.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CWI_FAIL="true", CWI_BASE_REF="")
    assert wi.main() == 0
    out = capsys.readouterr().out
    assert out.startswith("Skipping the write-idiom check")
    assert "::warning::" not in out


def test_main_with_unresolvable_base_warns(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("Write the x.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CWI_FAIL="true", CWI_BASE_REF="no-such-ref")
    assert wi.main() == 0
    assert capsys.readouterr().out.startswith(
        "::warning::Skipping the write-idiom check")


def test_main_whole_tree_fail_mode(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("Write a x.\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    _main_env(monkeypatch, repo, CWI_FAIL="true", CWI_WHOLE_TREE="true",
              CWI_BASE_REF="")
    assert wi.main() == 1
    assert "::error file=old.qmd,line=1::" in capsys.readouterr().out


# -- the action, the workflow and the script agree ---------------------------

def test_defaults_agree_across_action_workflow_and_script():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-write-idiom.yml").read_text()
    for text in (action, workflow):
        assert f"default: '{wi.DEFAULT_GLOBS}'" in text
    assert wi._DEFAULT_FAIL is False
    assert "default: 'false'" in action
    assert re.search(r"fail:\n(?:.*\n)*?\s+default: false", workflow)


def test_action_passes_every_input_to_the_script_under_the_cwi_prefix():
    action = (_DIR / "action.yml").read_text()
    for var in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"CWI_{var}:" in action
        assert f"CWI_{var}" in (_DIR / "check-write-idiom.py").read_text()
