r"""Unit tests for check-fform-paren.

Covers what counts as a finding (a macro directly followed by a paren macro
when its f form is defined), what is not (a bare paren macro, a macro with no
f form, the f form itself), what is skipped (code fences and spans, comments,
front matter), the reading of the macros file, the diff scoping, the
missing-macros-file skip, and the defaults the action, the reusable workflow
and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_fform_paren", _DIR / "check-fform-paren.py"
)
assert _spec is not None and _spec.loader is not None
fp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fp)

MACROS = (
    "```{=tex}\n"
    "\\providecommand{\\fitprocf}[1]{\\fitproc\\paren{#1}}\n"
    "\\newcommand{\\Ef}[1]{\\E\\paren{#1}}\n"
    "\\providecommand{\\fitproc}{f}\n"
    "\\def\\Epf{\\E}\n"
    "\\def\\Efx{\\E}\n"
    "```\n"
)


def found(text: str, fforms=frozenset({"fitprocf"})):
    """{line number: name} for a document given as one string."""
    hits, _ = fp.scan_file(text.split("\n"), set(fforms))
    return {h.line: h.name for h in hits}


# -- the macros file ---------------------------------------------------------

def test_fform_names_read_provide_new_command_and_def(tmp_path):
    macros = tmp_path / "macros.qmd"
    macros.write_text(MACROS)
    assert fp.fform_names(str(macros)) == {"fitprocf", "Ef", "Epf"}


def test_alias_operator_then_delimiter_is_flagged():
    hits, _ = fp.scan_file([r"Use $\Ep\sb{X}$ here."], {"Epf"})
    assert [(h.name, h.delimiter) for h in hits] == [("Ep", "sb")]
    assert "\\Ep\\sb{...} -> \\Epf{...}" in fp.format_message(hits[0])


def test_fform_names_missing_file_is_none(tmp_path):
    assert fp.fform_names(str(tmp_path / "nope.qmd")) is None


# -- findings ----------------------------------------------------------------

def test_name_then_paren_is_flagged_when_f_form_exists():
    assert found(r"Fit $\fitproc\paren{x}$ here.") == {1: "fitproc"}


def test_f_form_itself_passes():
    assert found(r"Fit $\fitprocf{x}$ here.") == {}


def test_bare_paren_passes():
    assert found(r"Group $\paren{x}$ here.") == {}
    assert found(r"Group $a + \paren{x}$ here.") == {}


def test_macro_without_f_form_passes():
    assert found(r"Use $\foo\paren{x}$ here.") == {}


def test_name_and_paren_separated_by_space_passes():
    assert found(r"Use $\fitproc \paren{x}$ here.") == {}


def test_each_use_on_a_line_is_found():
    hits, _ = fp.scan_file([r"$\fitproc\paren{a} + \fitproc\paren{b}$"], {"fitprocf"})
    assert [h.name for h in hits] == ["fitproc", "fitproc"]


@pytest.mark.parametrize(
    "delim", ["paren", "sb", "cb", "set", "abs", "norm", "angb"])
def test_each_delimiter_is_flagged_and_named_in_the_message(delim):
    text = "Fit $\\fitproc\\" + delim + "{x}$ here."
    hits, _ = fp.scan_file([text], {"fitprocf"})
    assert [(h.name, h.delimiter) for h in hits] == [("fitproc", delim)]
    msg = fp.format_message(hits[0])
    assert "\\fitproc\\" + delim + "{...} -> \\fitprocf{...}" in msg


def test_delimiter_list_is_a_constant():
    assert fp.DELIMITERS == (
        "paren", "sb", "cb", "set", "abs", "norm", "angb")


@pytest.mark.parametrize("delim", ["sb", "cb", "set", "abs", "norm", "angb"])
def test_bare_delimiters_pass(delim):
    assert found("Group $\\" + delim + "{x}$ and $a + \\" + delim + "{y}$.") == {}


@pytest.mark.parametrize("delim", ["sb", "cb", "set", "abs", "norm", "angb"])
def test_delimiters_without_f_form_pass(delim):
    assert found("Use $\\foo\\" + delim + "{x}$ here.") == {}


def test_longer_macro_names_starting_with_a_delimiter_pass():
    assert found(r"Use $\fitproc\sbx{x}$ and $\fitproc\parenthesis{x}$.") == {}


def test_message_names_both_forms():
    msg = fp.format_message(fp.Finding(3, "fitproc"))
    assert r"\fitproc\paren{...} -> \fitprocf{...}" in msg


# -- skips -------------------------------------------------------------------

def test_code_fence_is_skipped():
    assert found("```r\n# \\fitproc\\paren{x}\n```") == {}


def test_text_after_a_fence_is_scanned_again():
    assert found("```r\nx\n```\n$\\fitproc\\paren{x}$") == {4: "fitproc"}


def test_code_span_is_skipped():
    assert found(r"Write `\fitproc\paren{x}` for this.") == {}


def test_html_comment_is_skipped():
    assert found(r"<!-- \fitproc\paren{x} -->") == {}


def test_multiline_html_comment_is_skipped():
    text = "<!--\n\\fitproc\\paren{x}\n-->\n$\\fitproc\\paren{y}$"
    assert found(text) == {4: "fitproc"}


def test_front_matter_is_skipped():
    assert found("---\ntitle: \\fitproc\\paren{x}\n---\nbody") == {}


def test_allow_comment_on_the_line_or_the_line_before():
    allow = "<!-- check-fform-paren: allow -->"
    assert found(rf"$\fitproc\paren{{x}}$ {allow}") == {}
    assert found(f"{allow}\n$\\fitproc\\paren{{x}}$") == {}
    assert found(f"{allow}\n\n$\\fitproc\\paren{{x}}$") == {3: "fitproc"}


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
    return fp.run_check(
        base, kw.get("globs", fp.DEFAULT_GLOBS.split()),
        fp.compile_globs(kw.get("ignores", [])),
        kw.get("fforms", {"fitprocf"}), kw.get("whole_tree", False))


def test_added_line_is_flagged_in_diff_mode(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD")
    assert [(r, f.line, f.name) for r, f in report.findings] == [
        ("page.qmd", 1, "fitproc")]


def test_existing_use_is_not_reflagged(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    (repo / "new.qmd").write_text("$\\fitproc\\paren{y}$\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD")
    assert [r for r, _ in report.findings] == ["new.qmd"]


def test_moved_line_is_not_flagged(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("$\\fitproc\\paren{x}$\nprose\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    (repo / "old.qmd").write_text("prose\n$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    assert _run(monkeypatch, repo, "HEAD").findings == []


def test_whole_tree_flags_existing_uses(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    assert len(_run(monkeypatch, repo, "", whole_tree=True).findings) == 1


@pytest.mark.parametrize("base", ["", "no-such-ref"])
def test_unusable_base_skips_instead_of_falling_back(tmp_path, monkeypatch, base):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text("$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    report = _run(monkeypatch, repo, base)
    assert report.skipped and report.findings == []


def test_other_extensions_are_not_read(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "notes.txt").write_text("$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    assert _run(monkeypatch, repo, "HEAD").findings == []


def test_paths_ignore_skips_a_file(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "skip.qmd").write_text("$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    assert _run(monkeypatch, repo, "HEAD", ignores=["skip.qmd"]).findings == []


def test_report_counts_the_search_space(tmp_path, monkeypatch):
    repo, git = _repo(tmp_path)
    (repo / "a.qmd").write_text("prose\n$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    report = _run(monkeypatch, repo, "HEAD")
    assert (report.files, report.lines) == (1, 2)


# -- main(): the macros file, the exit code ----------------------------------

def _main_env(monkeypatch, repo, macros="latex-macros/macros.qmd", **extra):
    monkeypatch.chdir(repo)
    for key in ("CFP_BASE_REF", "CFP_MACROS_FILE", "CFP_GLOBS",
                "CFP_PATHS_IGNORE", "CFP_FAIL", "CFP_WHOLE_TREE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CFP_BASE_REF", "HEAD")
    monkeypatch.setenv("CFP_MACROS_FILE", macros)
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_missing_macros_file_skips_with_a_warning(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CFP_FAIL="true")
    assert fp.main() == 0
    out = capsys.readouterr().out
    assert out.startswith("::warning::Skipping the f-form check")
    assert "latex-macros/macros.qmd" in out


def test_main_warns_by_default_and_fails_on_request(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "latex-macros").mkdir()
    (repo / "latex-macros" / "macros.qmd").write_text(MACROS)
    (repo / "page.qmd").write_text("$\\fitproc\\paren{x}$\n")
    git("add", "-A")
    _main_env(monkeypatch, repo)
    assert fp.main() == 0
    out = capsys.readouterr().out
    assert "::warning file=page.qmd,line=1::" in out
    assert r"\fitproc\paren{...} -> \fitprocf{...}" in out
    monkeypatch.setenv("CFP_FAIL", "true")
    assert fp.main() == 1
    assert "::error file=page.qmd,line=1::" in capsys.readouterr().out


def test_main_passes_f_form_and_unknown_macro(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "latex-macros").mkdir()
    (repo / "latex-macros" / "macros.qmd").write_text(MACROS)
    (repo / "page.qmd").write_text(
        "$\\fitprocf{x}$ $\\paren{x}$ $\\foo\\paren{x}$\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CFP_FAIL="true")
    assert fp.main() == 0
    assert "No " in capsys.readouterr().out


# -- the action, the workflow and the script agree ---------------------------

def test_defaults_agree_across_action_workflow_and_script():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-fform-paren.yml").read_text()
    for text in (action, workflow):
        assert f"default: '{fp.DEFAULT_GLOBS}'" in text
        assert f"default: '{fp.DEFAULT_MACROS_FILE}'" in text
    assert fp._DEFAULT_FAIL is False
    assert "default: 'false'" in action
    assert re.search(r"fail:\n(?:.*\n)*?\s+default: false", workflow)
