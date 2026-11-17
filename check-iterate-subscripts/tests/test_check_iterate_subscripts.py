r"""Unit tests for check-iterate-subscripts.

Covers what counts as a finding (a configured symbol with a subscripted
iteration index), what does not (a number index, an index letter not
configured, a conforming ``\iterpoint``), what is skipped (code fences and
spans, comments, front matter, the allow comment), the diff scoping, and the
defaults the script, the action and the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_iterate_subscripts", _DIR / "check-iterate-subscripts.py"
)
assert _spec is not None and _spec.loader is not None
cis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cis)

PATTERN = cis.build_pattern(["vcoef", "steplen"], ["t", "\\iter"])


def found(text: str, pattern=PATTERN):
    """[(line, symbol, index)] for a document given as one string."""
    hits, _ = cis.scan_file(text.split("\n"), pattern)
    return [(h.line, h.symbol, h.index) for h in hits]


# -- what is flagged ---------------------------------------------------------

@pytest.mark.parametrize("math, index", [
    ("$\\vcoef_t$", "t"),
    ("$\\vcoef_{t}$", "t"),
    ("$\\vcoef_{t-1}$", "t-1"),
    ("$\\vcoef_{t + 1}$", "t + 1"),
    ("$\\vcoef_{\\iter}$", "\\iter"),
    ("$\\vcoef_{\\iter-1}$", "\\iter-1"),
    ("$\\vcoef_\\iter$", "\\iter"),
    ("$\\vcoef _ t$", "t"),
])
def test_subscripted_iterate_is_flagged(math, index):
    assert found(f"Step {math} here.") == [(1, "vcoef", index)]


def test_step_length_symbol_is_flagged():
    assert found("$\\steplen_t$") == [(1, "steplen", "t")]


def test_every_use_on_a_line_is_reported():
    hits = found("$\\vcoef_{t+1} = \\vcoef_t - \\steplen_t \\vg$")
    assert [(s, i) for _, s, i in hits] == [
        ("vcoef", "t+1"), ("vcoef", "t"), ("steplen", "t")]


def test_message_names_the_replacement():
    hit = cis.Finding(3, "vcoef", "t+1")
    assert "\\iterpoint{\\vcoef}{t+1}" in cis.format_message(hit)


# -- what is not flagged -----------------------------------------------------

@pytest.mark.parametrize("text", [
    "$\\iterpoint{\\vcoef}{\\iter}$",
    "$\\iterpoint{\\vcoef}{\\iter-1}$",
    "$\\vcoef_0$",                # a number alone: a true parameter
    "$\\vcoef_{0}$",
    "$\\vcoef_k$",                # k is not an index by default
    "$\\vcoef_{k+1}$",
    "$\\vcoef_{tx}$",             # not an iteration index
    "$\\vcoef_tx$",
    "$\\vcoef_{t,j}$",            # a coordinate of an iterate
    "$\\vcoef_{\\text{ridge}}$",
    "$\\vbeta_t$",                # a symbol that is not configured
    "$\\vcoefs_t$",               # a longer macro name
    "$\\\\vcoef_t$",              # an escaped backslash, not the macro
    "$\\vcoef^{(t)}$",            # raw superscript: a different rule
])
def test_conforming_or_out_of_scope_is_not_flagged(text):
    assert found(text) == []


def test_iterate_letter_is_configurable():
    pattern = cis.build_pattern(["vcoef"], ["t", "k", "\\iter"])
    assert found("$\\vcoef_k$ and $\\vcoef_{k+1}$", pattern) == [
        (1, "vcoef", "k"), (1, "vcoef", "k+1")]


def test_symbol_list_is_configurable():
    pattern = cis.build_pattern(["vw"], ["t"])
    assert found("$\\vw_t$ and $\\vcoef_t$", pattern) == [(1, "vw", "t")]


def test_split_words_takes_spaces_and_commas():
    assert cis.split_words("t, \\iter  k") == ["t", "\\iter", "k"]
    assert cis.split_words("") == []


# -- skips -------------------------------------------------------------------

def test_code_fence_is_skipped():
    assert found("```python\nx = '$\\vcoef_t$'\n```\n$\\vcoef_t$") == [
        (4, "vcoef", "t")]


def test_tilde_fence_is_skipped():
    assert found("~~~\n$\\vcoef_t$\n~~~") == []


def test_code_span_is_skipped():
    assert found("Write `\\vcoef_t` as `\\iterpoint`.") == []


def test_html_comment_is_skipped():
    assert found("<!-- \\vcoef_t -->") == []
    assert found("<!--\n\\vcoef_t\n-->\n$\\vcoef_t$") == [(4, "vcoef", "t")]


def test_front_matter_is_skipped():
    assert found("---\ntitle: $\\vcoef_t$\n---\n$\\vcoef_t$") == [
        (4, "vcoef", "t")]


def test_allow_comment_on_the_line_or_the_line_before():
    assert found("$\\vcoef_t$ <!-- check-iterate-subscripts: allow -->") == []
    assert found("<!-- check-iterate-subscripts: allow -->\n$\\vcoef_t$") == []
    assert found("<!-- check-iterate-subscripts: allow -->\n\n$\\vcoef_t$") == [
        (3, "vcoef", "t")]


# -- diff scoping ------------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "page.qmd").write_text(
        "Old $\\vcoef_t$ stays.\nPlain line.\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(base_ref="HEAD", whole_tree=False):
    ignores = cis.compile_globs([])
    return cis.run_check(base_ref, ["*.qmd"], ignores, PATTERN, whole_tree)


def test_existing_iterate_in_an_untouched_line_is_not_reported(repo):
    (repo / "page.qmd").write_text(
        "Old $\\vcoef_t$ stays.\nPlain line.\nNew line.\n")
    report = _run()
    assert report.findings == [] and not report.skipped


def test_added_iterate_is_reported(repo):
    (repo / "page.qmd").write_text(
        "Old $\\vcoef_t$ stays.\nPlain line.\nNew $\\vcoef_{t+1}$.\n")
    report = _run()
    assert [(f.line, f.index) for _, f in report.findings] == [(3, "t+1")]


def test_moved_line_is_not_new(repo):
    (repo / "page.qmd").write_text(
        "Plain line.\nOld $\\vcoef_t$ stays.\n")
    assert _run().findings == []


def test_whole_tree_reports_the_existing_iterate(repo):
    report = _run(whole_tree=True)
    assert [(f.line, f.index) for _, f in report.findings] == [(1, "t")]


def test_no_base_ref_skips_instead_of_scanning(repo):
    assert _run(base_ref="").skipped


def test_unresolvable_base_ref_skips(repo):
    assert _run(base_ref="no-such-ref").skipped


# -- main() ------------------------------------------------------------------

def test_main_blocks_by_default(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text("New $\\vcoef_t$.\n")
    monkeypatch.setenv("CIS_BASE_REF", "HEAD")
    monkeypatch.delenv("CIS_FAIL", raising=False)
    assert cis.main() == 1
    assert "::error file=page.qmd,line=1::" in capsys.readouterr().out


def test_main_warns_when_fail_is_false(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text("New $\\vcoef_t$.\n")
    monkeypatch.setenv("CIS_BASE_REF", "HEAD")
    monkeypatch.setenv("CIS_FAIL", "false")
    assert cis.main() == 0
    assert "::warning file=page.qmd,line=1::" in capsys.readouterr().out


def test_main_reads_symbols_and_indices(repo, monkeypatch):
    (repo / "page.qmd").write_text("New $\\vw_k$.\n")
    monkeypatch.setenv("CIS_BASE_REF", "HEAD")
    monkeypatch.setenv("CIS_SYMBOLS", "vw")
    monkeypatch.setenv("CIS_INDICES", "k")
    assert cis.main() == 1


def test_main_skips_without_a_base(repo, monkeypatch):
    (repo / "page.qmd").write_text("New $\\vcoef_t$.\n")
    monkeypatch.delenv("CIS_BASE_REF", raising=False)
    assert cis.main() == 0


# -- defaults declared in three places ---------------------------------------

def _default(path: Path, name: str) -> str:
    """The ``default:`` of input ``name`` in an action or workflow file."""
    lines = path.read_text().split("\n")
    for number, line in enumerate(lines):
        if re.fullmatch(rf"\s+{re.escape(name)}:\s*", line):
            for follow in lines[number + 1:number + 12]:
                found_default = re.match(r"\s+default:\s*(.*)", follow)
                if found_default:
                    return found_default.group(1).strip().strip("'\"")
    raise AssertionError(f"no default for {name} in {path}")


_ROOT = _DIR.parent
_FILES = [_DIR / "action.yml",
          _ROOT / ".github" / "workflows" / "check-iterate-subscripts.yml"]


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_defaults_agree_with_the_script(path):
    assert _default(path, "globs") == cis.DEFAULT_GLOBS
    assert _default(path, "symbols") == cis.DEFAULT_SYMBOLS
    assert _default(path, "indices") == cis.DEFAULT_INDICES
    assert _default(path, "fail") == str(cis._DEFAULT_FAIL).lower()
