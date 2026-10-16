r"""Unit tests for check-local-macros.

Covers what counts as a definition, what is skipped and why, the override-file
rule, the diff scoping (flag what a diff adds, never what was already there),
the skip-not-fallback guard, and the defaults the action, the reusable
workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_local_macros", _DIR / "check-local-macros.py"
)
assert _spec is not None and _spec.loader is not None
lm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lm)


def found(text: str, rel: str = "page.qmd"):
    """{line number: name} for a document given as one string."""
    hits, _ = lm.scan_file(rel, text.split("\n"))
    return dict(hits)


# -- definitions -------------------------------------------------------------

@pytest.mark.parametrize("text,name", [
    (r"\newcommand{\foo}[1]{#1}", r"\foo"),
    (r"\renewcommand{\foo}{x}", r"\foo"),
    (r"\providecommand{\foo}{x}", r"\foo"),
    (r"\newcommand*{\foo}{x}", r"\foo"),
    (r"\newcommand\foo{x}", r"\foo"),
    (r"\DeclareMathOperator{\foo}{foo}", r"\foo"),
    (r"\DeclarePairedDelimiter{\foo}{(}{)}", r"\foo"),
    (r"\def\foo#1{#1}", r"\foo"),
    (r"\gdef\foo{x}", r"\foo"),
    (r"\NewDocumentCommand{\foo}{m}{#1}", r"\foo"),
])
def test_each_definition_command_is_found(text, name):
    assert lm.definitions(text) == [name]


def test_other_commands_are_not_definitions():
    assert lm.definitions(r"\define \default \foo{x} \defined") == []


def test_escaped_backslash_is_not_a_definition():
    assert lm.definitions(r"\\newcommand{\foo}{x}") == []


# -- markdown-family files ---------------------------------------------------

def test_definition_in_display_math_is_flagged():
    assert found("text\n$$\n\\newcommand{\\foo}{x}\n$$") == {3: r"\foo"}


def test_definition_in_inline_math_is_flagged():
    assert found(r"Use $\newcommand{\foo}{x}$ here.") == {1: r"\foo"}


def test_code_span_is_skipped():
    assert found(r"Write `\newcommand{\foo}{x}` to define.") == {}


def test_plain_code_fence_is_skipped():
    assert found("```r\n# \\newcommand{\\foo}{x}\n```") == {}


@pytest.mark.parametrize("lang", ["tex", "latex", "{=tex}", "{=latex}", "{=html}"])
def test_raw_tex_fence_is_scanned(lang):
    assert found(f"```{lang}\n\\newcommand{{\\foo}}{{x}}\n```") == {2: r"\foo"}


def test_text_after_a_fence_is_scanned_again():
    assert found("```r\nx\n```\n$\\def\\foo{x}$") == {4: r"\foo"}


def test_html_comment_is_skipped():
    assert found(r"<!-- \newcommand{\foo}{x} -->") == {}


def test_multiline_html_comment_is_skipped():
    assert found("<!--\n\\newcommand{\\foo}{x}\n-->\n$\\def\\bar{x}$") == {4: r"\bar"}


def test_front_matter_is_skipped():
    assert found("---\ntitle: \\newcommand{\\foo}{x}\n---\nbody") == {}


def test_allow_comment_on_the_line_or_the_line_before():
    allow = "<!-- check-local-macros: allow -->"
    assert found(rf"$\def\foo{{x}}$ {allow}") == {}
    assert found(f"{allow}\n$\\def\\foo{{x}}$") == {}
    assert found(f"{allow}\n\n$\\def\\foo{{x}}$") == {3: r"\foo"}


# -- tex files ---------------------------------------------------------------

def test_tex_file_scans_every_line_and_skips_percent_comments():
    text = "% \\newcommand{\\a}{x}\n\\newcommand{\\b}{x}\n100\\% \\def\\c{x}"
    assert found(text, "macros.sty") == {2: r"\b", 3: r"\c"}


# -- overrides and the library -----------------------------------------------

def test_library_names_come_from_definitions(tmp_path):
    lib = tmp_path / "macros.qmd"
    lib.write_text("```{=tex}\n\\providecommand{\\outvar}{y}\n```\n"
                   "\\DeclareMathOperator{\\Var}{Var}\n")
    assert lm.library_names([str(lib), str(tmp_path / "missing")]) == {
        r"\outvar", r"\Var"}


def _repo(tmp_path):
    """A git repo with one commit; returns its path."""
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
    return lm.run_check(
        base, kw.get("globs", lm.DEFAULT_GLOBS.split()),
        lm.compile_globs(kw.get("ignores", [])),
        lm.compile_globs(lm.DEFAULT_OVERRIDES.split(",")),
        kw.get("library"), kw.get("whole_tree", False))


def test_override_of_a_library_macro_is_allowed(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "macros-override.qmd").write_text("$\\renewcommand{\\outvar}{Y}$\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD", library={r"\outvar"})
    assert report.findings == [] and report.definitions == 1


def test_override_of_an_unknown_macro_is_flagged(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "macros-override.qmd").write_text("$\\newcommand{\\mine}{Y}$\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD", library={r"\outvar"})
    assert [(f.name, f.kind) for _, f in report.findings] == [(r"\mine", "override")]


def test_override_is_unchecked_without_a_library(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "macros-override.qmd").write_text("$\\newcommand{\\mine}{Y}$\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD", library=None)
    assert report.findings == [] and report.unchecked_overrides == 1


def test_definition_outside_an_override_file_is_flagged(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("$\\renewcommand{\\outvar}{Y}$\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD", library={r"\outvar"})
    assert [(f.name, f.kind) for _, f in report.findings] == [(r"\outvar", "local")]


# -- diff scoping ------------------------------------------------------------

def test_existing_definition_is_not_reflagged(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("$\\def\\old{x}$\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    (repo / "new.qmd").write_text("$\\def\\new{x}$\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD")
    assert [(r, f.name) for r, f in report.findings] == [("new.qmd", r"\new")]


def test_moved_line_counts_as_old(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("$\\def\\old{x}$\nprose\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    (repo / "old.qmd").write_text("prose\n$\\def\\old{x}$\n")
    git("add", "-A")
    assert _run(monkeypatch, repo, "HEAD").findings == []


def test_whole_tree_flags_existing_definitions(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("$\\def\\old{x}$\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    report = _run(monkeypatch, repo, "", whole_tree=True)
    assert len(report.findings) == 1


@pytest.mark.parametrize("base", ["", "no-such-ref"])
def test_unusable_base_skips_instead_of_falling_back(tmp_path, monkeypatch, base):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("$\\def\\old{x}$\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    report = _run(monkeypatch, repo, base)
    assert report.skipped and report.findings == []


def test_paths_ignore_skips_a_file(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "skip.qmd").write_text("$\\def\\x{x}$\n")
    git("add", "-A")
    assert _run(monkeypatch, repo, "HEAD", ignores=["skip.qmd"]).findings == []


def test_report_counts_the_search_space(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "a.qmd").write_text("prose\n$\\def\\x{x}$\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD")
    assert (report.files, report.lines, report.definitions) == (1, 2, 1)


# -- the action, the workflow and the script agree ---------------------------

def test_defaults_agree_across_action_workflow_and_script():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-local-macros.yml").read_text()
    for text in (action, workflow):
        assert f"default: '{lm.DEFAULT_GLOBS}'" in text
        assert f"default: '{lm.DEFAULT_OVERRIDES}'" in text
    assert lm._DEFAULT_FAIL is False
    assert "default: 'false'" in action
    assert re.search(r"fail:\n(?:.*\n)*?\s+default: false", workflow)
