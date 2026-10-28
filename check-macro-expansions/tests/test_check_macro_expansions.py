r"""Unit tests for check-macro-expansions.

Covers what counts as a finding (math that spells out a macro's expansion), what
is not (the macro itself, a lone font wrapper, text outside math, a deliberate
derivation step marked as allowed), what is skipped (code fences and spans,
comments, front matter, the macro's own definition), the reading of the macros
file, the diff scoping, the missing-macros-file skip, and the defaults the
action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_macro_expansions", _DIR / "check-macro-expansions.py"
)
assert _spec is not None and _spec.loader is not None
cme = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cme)

MACROS = (
    "```{=tex}\n"
    "\\providecommand{\\sumin}{\\sum_{i=1}^n}\n"
    "\\providecommand{\\sumto}[2]{\\sum_{#1=1}^{#2}}\n"
    "\\providecommand{\\sqf}[1]{\\powf{#1}{2}}\n"
    "\\providecommand{\\powf}[2]{{\\paren{#1}}^{#2}}\n"
    "\\providecommand{\\prederrf}[1]{\\paren{#1 - \\newoutvar}}\n"
    "\\providecommand{\\qform}[2]{\\tp{#2} #1 #2}\n"
    "\\providecommand{\\modelfam}{\\mathcal{H}}\n"
    "\\providecommand{\\distop}[1]{\\operatorname{#1}}\n"
    "\\providecommand{\\ba}{\\begin{aligned}}\n"
    "\\providecommand{\\bfX}{\\mX}\n"
    "\\providecommand{\\hist}[2]{\\bar{#1}_{#2}}\n"
    "\\def\\Sumi{\\sumin}\n"
    "```\n"
)


@pytest.fixture(scope="module")
def table(tmp_path_factory):
    macros = tmp_path_factory.mktemp("m") / "macros.qmd"
    macros.write_text(MACROS)
    loaded = cme.load_expansions(str(macros), set())
    assert loaded is not None
    return loaded


def found(table, text: str):
    """{line number: names} for a document given as one string."""
    hits, _ = cme.scan_file(text.split("\n"), table)
    return {h.line: h.names for h in hits}


# -- the macros file ---------------------------------------------------------

def test_expansions_keep_structured_bodies_only(table):
    names = {n for exp in table for n in exp.names}
    # structured bodies are kept
    assert {"sumin", "sumto", "prederrf", "qform", "hist"} <= names
    # a lone font wrapper, an environment opener and an alias are not
    assert not {"modelfam", "distop", "ba", "bfX", "Sumi", "sqf"} & names


def test_missing_macros_file_is_none(tmp_path):
    assert cme.load_expansions(str(tmp_path / "nope.qmd"), set()) is None


def test_exclude_drops_a_macro(tmp_path):
    macros = tmp_path / "macros.qmd"
    macros.write_text(MACROS)
    loaded = cme.load_expansions(str(macros), {"hist"})
    assert "hist" not in {n for exp in loaded for n in exp.names}


# -- findings ----------------------------------------------------------------

def test_flags_a_hand_written_sum(table):
    assert found(table, r"Take $\sum_{i=1}^n y_i$.") == {1: ("sumin", "sumto")}


def test_flags_with_braces_and_spaces(table):
    assert found(table, r"$\sum_{ i = 1 }^{ n } y_i$") == {1: ("sumin", "sumto")}


def test_wildcard_arguments_are_captured(table):
    assert found(table, r"$\sum_{j=1}^{N} z_j$") == {1: ("sumto",)}


def test_repeated_placeholder_must_match_itself(table):
    assert found(table, r"$\tp{X} W X$") == {1: ("qform",)}
    assert found(table, r"$\tp{X} W Z$") == {}


def test_flags_the_prediction_error_chunk(table):
    assert found(table, r"$\paren{\predval - \newoutvar}$") == {1: ("prederrf",)}


def test_display_math_across_lines(table):
    text = "$$\n\\sum_{i=1}^n y_i\n$$"
    assert found(table, text) == {2: ("sumin", "sumto")}


def test_one_expression_is_reported_once_with_every_macro(table):
    hits, _ = cme.scan_file([r"$\sum_{i=1}^n$"], table)
    assert [h.names for h in hits] == [("sumin", "sumto")]


def test_message_names_the_macros(table):
    hits, _ = cme.scan_file([r"$\sum_{i=1}^n$"], table)
    message = cme.format_message(hits[0])
    assert "\\sumin" in message and "\\sumto" in message


# -- not findings ------------------------------------------------------------

def test_the_macro_itself_is_clean(table):
    assert found(table, r"$\sumin y_i$") == {}


def test_a_line_already_using_the_macro_is_not_flagged_for_it(table):
    # \sumin is used here, so only the other macro with this expansion remains.
    assert found(table, r"$\sumin y_i + \sum_{i=1}^n z_i$") == {1: ("sumto",)}


def test_a_lone_font_wrapper_is_clean(table):
    assert found(table, r"$\mathcal{H}$ and $\operatorname{rank}(A)$") == {}


def test_text_outside_math_is_clean(table):
    assert found(table, r"Write sum_{i=1}^n in words, or \sum_{i=1}^n.") == {}


def test_an_unrelated_sum_is_clean(table):
    assert found(table, r"$\sum_{k=0}^{K} a_k$") == {}


def test_a_longer_macro_name_is_not_a_match(table):
    assert found(table, r"$\sumx_{i=1}^n$") == {}


# -- opt-out and masking -----------------------------------------------------

def test_allow_comment_on_the_line(table):
    text = r"$\sum_{i=1}^n y_i$ <!-- check-macro-expansions: allow -->"
    assert found(table, text) == {}


def test_allow_comment_on_the_previous_line(table):
    text = "<!-- check-macro-expansions: allow -->\n$\\sum_{i=1}^n y_i$"
    assert found(table, text) == {}


def test_code_fence_span_comment_and_front_matter_are_skipped(table):
    text = "\n".join([
        "---", r"title: $\sum_{i=1}^n$", "---",
        "```r", r"x <- '$\sum_{i=1}^n$'", "```",
        r"A span `$\sum_{i=1}^n$` and <!-- $\sum_{i=1}^n$ --> here.",
    ])
    assert found(table, text) == {}


def test_a_macro_definition_line_is_skipped(table):
    assert found(table, r"\providecommand{\sumjn}{\sum_{i=1}^n}") == {}


# -- diff scoping and the skip -----------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch, table):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "old.qmd").write_text("$\\sum_{i=1}^n a_i$\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "checkout", "-q", "-b", "pr")
    (tmp_path / "new.qmd").write_text("$\\sum_{i=1}^n b_i$\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "pr")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_diff_scope_reports_added_lines_only(repo, table):
    report = cme.run_check("main", ["*.qmd"], [], table, False)
    assert not report.skipped
    assert [rel for rel, _ in report.findings] == ["new.qmd"]


def test_whole_tree_reports_everything(repo, table):
    report = cme.run_check("", ["*.qmd"], [], table, True)
    assert sorted(rel for rel, _ in report.findings) == ["new.qmd", "old.qmd"]


def test_no_base_ref_skips_rather_than_scanning_everything(repo, table):
    report = cme.run_check("", ["*.qmd"], [], table, False)
    assert report.skipped and not report.findings


def test_paths_ignore_exempts_a_file(repo, table):
    ignores = cme.compile_globs(["new.qmd"])
    report = cme.run_check("main", ["*.qmd"], ignores, table, False)
    assert report.findings == []


# -- the defaults must agree -------------------------------------------------

def _inputs(path: Path) -> str:
    return path.read_text()


def test_action_and_script_agree_on_defaults():
    action = _inputs(_DIR / "action.yml")
    assert "latex-macros/macros.qmd" in action
    assert cme.DEFAULT_MACROS_FILE == "latex-macros/macros.qmd"
    assert re.search(r"fail:\n\s+description:.*\n(?:\s+.*\n)*?\s+default: 'false'",
                     action)
    assert cme._DEFAULT_FAIL is False
    for var in ("CME_BASE_REF", "CME_WHOLE_TREE", "CME_MACROS_FILE", "CME_GLOBS",
                "CME_PATHS_IGNORE", "CME_EXCLUDE", "CME_FAIL"):
        assert var in action
