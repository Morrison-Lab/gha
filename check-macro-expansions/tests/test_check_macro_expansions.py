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
    "\\providecommand{\\bform}[3]{\\tp{#2} #1 #3}\n"
    "\\providecommand{\\soprod}[1]{#1 \\tp{#1}}\n"
    "\\providecommand{\\oprod}[2]{#1 \\tp{#2}}\n"
    "\\providecommand{\\tprod}[2]{\\tp{#1} #2}\n"
    "\\providecommand{\\ccprod}[2]{\\tp{#1} #2}\n"
    "\\providecommand{\\stprod}[1]{\\ccprod{#1}{#1}}\n"
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
    # transpose products are kept although their bodies are short
    assert {"soprod", "oprod", "tprod", "ccprod", "stprod"} <= names
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
    # \bform's three wildcards match a quadratic form too; \qform's repeated
    # #2 matches only when both sides are the same.
    assert found(table, r"$\tp{X} W X$") == {1: ("qform", "bform")}
    assert found(table, r"$\tp{X} W Z$") == {1: ("bform",)}


def test_flags_a_self_outer_product(table):
    assert found(table, r"$\vX \tp{\vX}$") == {1: ("soprod", "oprod")}


def test_flags_an_outer_product_of_a_braced_argument(table):
    text = r"$\paren{\vX - \vmu} \tp{\paren{\vX - \vmu}}$"
    assert found(table, text) == {1: ("soprod", "oprod")}


def test_flags_an_outer_product_of_two_vectors(table):
    assert found(table, r"$\va \tp{\vb}$") == {1: ("oprod",)}


def test_flags_a_transpose_product(table):
    assert found(table, r"$\tp{\va} \vX$") == {1: ("tprod", "ccprod")}


def test_flags_a_gram_matrix_through_the_macro_it_calls(table):
    assert found(table, r"$\tp{\mX} \mX$") == {1: ("tprod", "ccprod", "stprod")}


def test_an_outer_product_inside_an_expectation_is_flagged(table):
    # The pds#478 text that went unflagged before.
    assert found(table, r"$\E{\vX \tp{\vX}}$") == {1: ("soprod", "oprod")}
    text = r"$\paren{\Expp\vX} \tp{\paren{\Expp\vX}}$"
    assert found(table, text) == {1: ("soprod", "oprod")}


def test_the_inside_of_one_factor_is_not_a_product(table):
    assert found(table, r"$\mQ \matr{\Eigvals}\tp{\mQ}$") == {}


def test_two_transposes_are_not_an_outer_product(table):
    assert found(table, r"$\tp{\va} \tp{\vb}$") == {}


def test_a_scalar_or_text_is_not_a_product_factor(table):
    assert found(table, r"$2\tp{\vb}$") == {}
    assert found(table, r"$\mA^{-1}\tp{\mQ}$") == {1: ("oprod",)}
    # the last two factors of a longer product are not flagged alone
    assert found(table, r"$\mQ \mA^{-1}\tp{\mQ}$") == {}
    assert found(table, r"$\tp{\va} \text{, with } \vb$") == {}
    assert found(table, r"$\begin{bmatrix} \tp{\vone} \end{bmatrix}$") == {}
    assert found(table, r"$\tp{\mU} \begin{bmatrix} a \end{bmatrix}$") == {}


def test_only_products_take_a_braced_argument(table):
    # \prederrf is \paren{#1 - \newoutvar}; its #1 stays narrow.
    assert found(table, r"$\paren{\E{Y} - \newoutvar}$") == {}


def test_a_lone_transpose_is_clean(table):
    # \vX is one argument; it is not split into \v and X.
    assert found(table, r"$\tp{\vX}$") == {}


def test_a_macro_written_as_its_call_is_still_matched(tmp_path):
    macros = tmp_path / "macros.qmd"
    macros.write_text(MACROS)
    loaded = cme.load_expansions(str(macros), set())
    bodies = {exp.body for exp in loaded if "stprod" in exp.names}
    # Tokens drop braces; "\ccprod #1 #1" has three tokens and no \tp, so only
    # the expanded form is kept.
    assert bodies == {"\\tp #1 #1"}


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
    ignores = cme.diffscope.compile_ignores(["new.qmd"])
    report = cme.run_check("main", ["*.qmd"], ignores, table, False)
    assert report.findings == []


# -- the defaults must agree -------------------------------------------------

def _inputs(path: Path) -> str:
    return path.read_text()


def test_action_and_script_agree_on_defaults():
    action = _inputs(_DIR / "action.yml")
    assert "latex-macros/macros.qmd" in action
    assert cme.DEFAULT_MACROS_FILE == "latex-macros/macros.qmd"
    fail_input = action.split("\n  fail:\n", 1)[1].split("\nruns:", 1)[0]
    assert fail_input.rstrip().endswith("default: 'false'")
    assert cme._DEFAULT_FAIL is False
    for var in ("CME_BASE_REF", "CME_WHOLE_TREE", "CME_MACROS_FILE", "CME_GLOBS",
                "CME_PATHS_IGNORE", "CME_EXCLUDE", "CME_FAIL"):
        assert var in action
