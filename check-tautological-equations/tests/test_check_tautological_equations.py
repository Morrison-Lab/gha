r"""Unit tests for check-tautological-equations.

Covers the macro expansion (arguments, optional arguments, ``\def`` with
parameters, nesting), the split into sides (top-level relations only,
relation macros, alignments and their continuation rows), the normalization
(spacing, sizing, single-token groups, trailing punctuation), what is skipped
(code fences and spans, comments, front matter, macro definitions, the allow
comment), the diff scoping, the missing-macros-file skip, and the defaults
the action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_ROOT = _DIR.parent
_spec = importlib.util.spec_from_file_location(
    "check_tautological_equations", _DIR / "check-tautological-equations.py"
)
assert _spec is not None and _spec.loader is not None
te = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(te)

MACROS = r"""
```{=tex}
\providecommand{\tp}[1]{{#1}^{\top}}
\providecommand{\matr}[1]{\mathbf{#1}}
\providecommand{\vx}{\mathbf{x}}
\providecommand{\vy}{\mathbf{y}}
\providecommand{\bform}[3]{\tp{#2} #1 #3}
\providecommand{\dprod}[2]{#1 \cdot #2}
\providecommand{\paren}[1]{\mathopen{}\left(#1\right)\mathclose{}}
\providecommand{\cb}[1]{\left\{#1\right\}}
\def\eqdef{\stackrel{\text{def}}{=}}
\def\ba{\begin{aligned}}
\def\ea{\end{aligned}}
\def\sdpar{\sigma}
\def\varpar{\sdpar^2}
\def\pair#1#2{(#1, #2)}
\newcommand{\norm}[2][2]{\left\| #2 \right\|_{#1}}
\renewcommand{\vy}{\mathbf{y}}
\providecommand{\vx}{\mathbf{WRONG}}
\DeclareMathOperator{\rank}{rank}
```
"""


@pytest.fixture(scope="module")
def macros(tmp_path_factory):
    path = tmp_path_factory.mktemp("m") / "macros.qmd"
    path.write_text(MACROS)
    loaded = te.load_macros([str(path)])
    assert loaded is not None
    return loaded


def hits(macros, math):
    return [rel for rel, _, _ in te.tautologies(math, macros)]


# -- the macros file -----------------------------------------------------------

def test_reads_every_definition_form(macros):
    assert macros["\\bform"].nargs == 3
    assert macros["\\pair"].nargs == 2
    assert macros["\\norm"].nargs == 2 and macros["\\norm"].default == ["2"]
    assert macros["\\rank"].body[0] == "\\operatorname"


def test_providecommand_does_not_override(macros):
    assert "".join(macros["\\vx"].body) == "\\mathbf{x}"


def test_missing_macros_file_is_none(tmp_path):
    assert te.load_macros([str(tmp_path / "nope.qmd")]) is None


# -- what is flagged -------------------------------------------------------------

def test_flags_the_bilinear_form_definition(macros):
    math = r"\bform{\matr{A}}{\vx}{\vy} \eqdef \tp{\vx}\, \matr{A}\, \vy."
    assert hits(macros, math) == ["\\eqdef"]


def test_flags_a_macro_whose_body_is_the_other_side(macros):
    assert hits(macros, r"\dprod{\vx}{\vy} = \vx \cdot \vy") == ["="]
    assert hits(macros, r"\varpar = \sdpar^2") == ["="]


def test_flags_each_definitional_relation(macros):
    assert hits(macros, r"a := a") == [":="]
    assert hits(macros, r"a =: a") == ["=:"]
    assert hits(macros, r"a \coloneqq a") == ["\\coloneqq"]
    assert hits(macros, r"a \equiv a") == ["\\equiv"]
    assert hits(macros, r"a \overset{\text{def}}{=} a") == ["\\overset{\\text{def}}{=}"]


def test_single_token_groups_and_spacing_do_not_matter(macros):
    assert hits(macros, r"x^{2} = x^2") == ["="]
    assert hits(macros, r"\paren{x} = \left( x \right)") == ["="]
    assert hits(macros, r"\mathbf{x} = \mathbf x \quad .") == ["="]


def test_def_parameters_and_optional_arguments_expand(macros):
    assert hits(macros, r"\pair{a}{b} = (a, b)") == ["="]
    assert hits(macros, r"\norm{x} = \left\| x \right\|_2") == ["="]
    assert hits(macros, r"\norm[1]{x} = \left\| x \right\|_{1}") == ["="]
    assert hits(macros, r"\norm[1]{x} = \left\| x \right\|_2") == []


def test_aligned_continuation_rows_join_the_chain(macros):
    math = "\\ba\nf(x) &= g(x) \\\\\n&= g(x)\n\\ea"
    assert hits(macros, math) == ["="]


def test_a_relation_inside_parentheses_does_not_hide_the_outer_one(macros):
    assert hits(macros, "f(a = b) = f(a = b)") == ["="]


def test_left_right_pairs_count_once(macros):
    # A one-sided or mixed \left...\right pair opens and closes one level,
    # so the top-level relation after it still splits.
    assert hits(macros, r"\left\{ a \right. = \left\{ a \right.") == ["="]
    assert hits(macros, r"\left( 0, 1 \right] = \left( 0, 1 \right]") == ["="]
    assert hits(macros, r"\left ( a \right ) = \left( a \right)") == ["="]


def test_half_open_intervals_balance(macros):
    assert hits(macros, r"(0, 1] = (0, 1]") == ["="]
    assert hits(macros, r"[0, 1) = [0, 1)") == ["="]


def test_only_neighbouring_sides_are_compared(macros):
    assert hits(macros, r"a = b = a") == []


# -- what is not flagged -----------------------------------------------------------

def test_a_genuine_equation_is_clean(macros):
    assert hits(macros, r"\bform{\matr{A}}{\vx}{\vy} = \tp{\vy} \matr{A} \vx") == []


def test_nested_relations_do_not_split(macros):
    assert hits(macros, r"\Pr(X = x) = p") == []
    assert hits(macros, r"\cb{x : x = 0} = A") == []
    assert hits(macros, r"\paren{a = a} = b") == []
    assert hits(macros, r"\Pr(X \in [0, 1), Y = Y) = p") == []
    assert hits(macros, r"\Pr(\left[ 0, 1 \right), Y = Y) = p") == []
    assert hits(macros, r"\begin{cases} a = a \end{cases} = b") == []


def test_aligned_rows_with_their_own_left_side_start_new_chains(macros):
    math = "\\begin{aligned} a &= b \\\\ b &= c \\end{aligned}"
    assert hits(macros, math) == []


@pytest.mark.parametrize("env", ["alignat", "alignat*", "alignedat"])
def test_alignat_column_count_is_not_a_side(macros, env):
    # The {cols} argument of alignat and alignedat is not part of the
    # first side, so x = 2x is clean and x = x is a hit.
    begin, end = f"\\begin{{{env}}}{{2}}", f"\\end{{{env}}}"
    assert hits(macros, f"{begin} x &= 2x {end}") == []
    assert hits(macros, f"{begin} x &= x {end}") == ["="]


def test_alpha_x_is_not_alphax(macros):
    assert hits(macros, r"\alpha x = \alphax") == []


def test_an_empty_side_is_not_compared(macros):
    assert hits(macros, r"= x") == []


# -- scanning a file ----------------------------------------------------------------

def found(macros, text):
    return [f.line for _, _, f in te.scan_file(text.split("\n"), macros)[0]]


def test_inline_and_display_math_are_scanned(macros):
    text = "Here $a := a$ inline.\n\n$$\n\\dprod{\\vx}{\\vy} = \\vx \\cdot \\vy\n$$\n"
    assert found(macros, text) == [1, 3]


def test_code_comments_and_front_matter_are_skipped(macros):
    text = ("---\ntitle: $a = a$\n---\n"
            "```\n$a = a$\n```\n"
            "`$a = a$` and <!-- $a = a$ -->\n")
    assert found(macros, text) == []


def test_math_defining_a_macro_is_skipped(macros):
    assert found(macros, "$$\n\\newcommand{\\foo}{x} \\\\\na = a\n$$") == []


def test_allow_comment_on_or_before_the_equation(macros):
    assert found(macros, "<!-- check-tautological-equations: allow -->\n$a = a$") == []
    assert found(macros, "$a = a$ <!-- check-tautological-equations: allow -->") == []
    assert found(macros, "<!-- check-tautological-equations: allow -->\n\n$a = a$") == [3]


def test_message_names_both_sides(macros):
    (_, _, f), = te.scan_file(["$a := a$"], macros)[0]
    msg = te.format_message(f)
    assert "a := a" in msg and "check-tautological-equations: allow" in msg


# -- diff scoping -----------------------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t",
                        "GIT_AUTHOR_EMAIL": "t@example.com",  # phi-allow
                        "GIT_COMMITTER_EMAIL": "t@example.com"})  # phi-allow


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "macros.qmd").write_text(MACROS)
    (tmp_path / "old.qmd").write_text("$b = b$\n")
    (tmp_path / "page.qmd").write_text("$$\nx\n= y\n$$\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_diff_scope_reports_only_touched_equations(repo, macros):
    (repo / "page.qmd").write_text("$$\ny\n= y\n$$\n")
    _git(repo, "commit", "-qam", "edit")
    report = te.run_check("HEAD~1", ["*.qmd"], [], macros, False)
    assert [(rel, f.line) for rel, f in report.findings] == [("page.qmd", 1)]


def test_whole_tree_reports_everything(repo, macros):
    report = te.run_check("", ["*.qmd"], [], macros, True)
    assert [rel for rel, _ in report.findings] == ["old.qmd"]


def test_moved_line_is_not_new(repo, macros):
    (repo / "old.qmd").write_text("intro\n\n$b = b$\n")
    _git(repo, "commit", "-qam", "move")
    report = te.run_check("HEAD~1", ["*.qmd"], [], macros, False)
    assert report.findings == []


def test_no_base_skips(repo, macros):
    assert te.run_check("", ["*.qmd"], [], macros, False).skipped
    assert te.run_check("nope", ["*.qmd"], [], macros, False).skipped


def test_main_fails_by_default_and_skips_without_macros(repo, monkeypatch, capsys):
    monkeypatch.setenv("TE_WHOLE_TREE", "true")
    monkeypatch.setenv("TE_MACROS_FILE", "macros.qmd")
    assert te.main() == 1
    monkeypatch.setenv("TE_FAIL", "false")
    assert te.main() == 0
    monkeypatch.setenv("TE_FAIL", "true")
    monkeypatch.setenv("TE_MACROS_FILE", "missing.qmd")
    assert te.main() == 0
    assert "Skipping" in capsys.readouterr().out


def test_main_warns_when_no_base_ref_is_given(repo, monkeypatch, capsys):
    monkeypatch.setenv("TE_MACROS_FILE", "macros.qmd")
    monkeypatch.delenv("TE_BASE_REF", raising=False)
    monkeypatch.delenv("TE_WHOLE_TREE", raising=False)
    assert te.main() == 0
    assert "::warning::Skipping" in capsys.readouterr().out


# -- defaults agree ------------------------------------------------------------------------

def _yaml_default(path, name):
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f"{name}:":
            for nxt in lines[i + 1:i + 12]:
                if nxt.strip().startswith("default:"):
                    return nxt.split(":", 1)[1].strip().strip("'")
    raise AssertionError(f"no default for {name} in {path}")


@pytest.mark.parametrize("path", [
    _DIR / "action.yml",
    _ROOT / ".github" / "workflows" / "check-tautological-equations.yml",
])
def test_defaults_agree(path):
    assert _yaml_default(path, "globs") == te.DEFAULT_GLOBS
    assert _yaml_default(path, "macros-file") == te.DEFAULT_MACROS_FILE
    assert _yaml_default(path, "fail").lower() == str(te._DEFAULT_FAIL).lower()
