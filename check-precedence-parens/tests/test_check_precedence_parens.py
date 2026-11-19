r"""Unit tests for check-precedence-parens.

Covers what counts as a finding (a relation beside a connective, two kinds
of connective at one level, a repeated implication), what does not (each
comparison parenthesized, a repeated ``\land`` or ``\lor``, the single
arrows, a set-builder colon, a quantifier's comma, an aligned derivation's
leading connective), what is skipped (code fences and spans, comments, front
matter, the allow comment), the diff scoping, and the defaults the script,
the action and the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_precedence_parens", _DIR / "check-precedence-parens.py"
)
assert _spec is not None and _spec.loader is not None
cpp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpp)


def found(text: str):
    """[(line, rule, detail)] for a document given as one string."""
    hits, _ = cpp.scan_file(text.split("\n"))
    return [(h.line, h.rule, h.detail) for h in hits]


def rules(math: str):
    """The rules ``math`` breaks, in order."""
    return [rule for rule, _ in cpp.check_math(math)]


# -- what is flagged ---------------------------------------------------------

def test_the_set_builder_example_is_flagged():
    hits = found("$A \\cup B = \\set{x : x \\in A \\lor x \\in B}$")
    assert [(r, d) for _, r, d in hits] == [
        ("relation", "x \\in A"), ("relation", "x \\in B")]


@pytest.mark.parametrize("math", [
    "x \\in A \\land x \\notin B",
    "x > 0 \\Rightarrow x^2 > 0",
    "0 < x \\land x < 1",
    "P(x) \\lor x = 3",
    "x \\in A \\Leftrightarrow x \\in B",
    "A \\subseteq B \\implies B \\subseteq A",
    "a \\mid b \\iff b \\equiv 0",
    "x ∈ A ∨ x ∈ B",
    "x \\le y \\wedge y \\le z",
])
def test_relation_beside_a_connective_is_flagged(math):
    assert "relation" in rules(math)


@pytest.mark.parametrize("math", [
    "P \\land Q \\lor R",
    "P \\lor Q \\Rightarrow R",
    "P \\Rightarrow Q \\Rightarrow R",
    "P \\iff Q \\iff R",
    "\\neg P \\land Q \\Leftrightarrow R",
])
def test_mixed_or_non_associative_connectives_are_flagged(math):
    assert rules(math) == ["mixed"]


def test_a_relation_inside_a_macro_argument_is_flagged():
    assert rules("\\set{x \\in \\mathbb{Z} : x > 0 \\lor x < -3}") == [
        "relation", "relation"]


def test_message_names_the_operand():
    hit = cpp.Finding(3, "relation", "x \\in A")
    assert "'x \\in A'" in cpp.format_message(hit)
    assert "(x \\in A) \\lor (x \\in B)" in cpp.format_message(hit)


def test_message_names_the_connectives():
    hit = cpp.Finding(3, "mixed", "\\land \\lor")
    assert "'\\land \\lor'" in cpp.format_message(hit)


# -- what is not flagged -----------------------------------------------------

@pytest.mark.parametrize("math", [
    "\\set{x : (x \\in A) \\lor (x \\in B)}",
    "(x > 0) \\Rightarrow (x^2 > 0)",
    "\\left( x \\in A \\right) \\land \\left( x \\notin B \\right)",
    "\\paren{x \\in A} \\lor \\paren{x \\in B}",
    "P \\land Q \\land R",                 # associative
    "P \\lor Q \\lor R",
    "(P \\land Q) \\lor R",
    "P \\Rightarrow (Q \\Rightarrow R)",
    "f : A \\to B",                        # function arrow
    "\\lim_{x \\to 0} f(x) = L",
    "1 \\to 2 \\to 3",                     # a path, not an implication
    "x \\in A",                            # no connective at all
    "\\forall x \\in A, P(x)",             # the comma ends the domain
    "\\forall x \\in A, P(x) \\land Q(x)",
    "A \\cup B \\eqdef \\set{x : (x \\in A) \\lor (x \\in B)}",
    "x \\in A \\text{ or } x \\in B",      # words, not a connective
    "P \\land Q, \\quad x = 1",            # separate clauses
    "x \\in A & \\iff x \\in B",           # an aligned row's step
])
def test_explicit_or_out_of_scope_is_not_flagged(math):
    assert rules(math) == []


def test_thin_space_is_not_a_comma():
    assert rules("x = 1 \\, \\land \\, y = 2") == ["relation", "relation"]


def test_aligned_row_still_checks_its_own_connectives():
    assert rules("& \\iff x \\in A \\lor x \\in B") == [
        "relation", "relation"]


def test_stray_closer_does_not_crash():
    assert rules("x \\in A) \\lor (x") == ["relation"]


# -- math spans --------------------------------------------------------------

def test_prose_outside_math_is_not_read():
    assert found("x in A or x = 2, and P implies Q.") == []


def test_display_math_lines_are_read():
    text = "$$\nx \\in A \\lor x \\in B\n$$"
    assert [line for line, _, _ in found(text)] == [2, 2]


# -- skips -------------------------------------------------------------------

BAD = "$x \\in A \\lor x \\in B$"


def test_code_fence_is_skipped():
    assert found(f"```\n{BAD}\n```") == []
    assert len(found(f"```tex\n{BAD}\n```\n{BAD}")) == 2


def test_code_span_is_skipped():
    assert found("Type `$x \\in A \\lor x \\in B$` here.") == []


def test_html_comment_is_skipped():
    assert found(f"<!-- {BAD} -->") == []


def test_front_matter_is_skipped():
    assert [line for line, _, _ in found(f"---\ntitle: '{BAD}'\n---\n{BAD}")] == [4, 4]


def test_allow_comment_on_the_line_or_the_line_before():
    allow = "<!-- check-precedence-parens: allow -->"
    assert found(f"{BAD} {allow}") == []
    assert found(f"{allow}\n{BAD}") == []
    assert len(found(f"{allow}\n\n{BAD}")) == 2


# -- diff scoping ------------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@example.com", *args],  # phi-allow
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "page.qmd").write_text(f"Old {BAD} stays.\nPlain line.\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(base_ref="HEAD", whole_tree=False):
    return cpp.run_check(base_ref, ["*.qmd"], cpp.compile_globs([]), whole_tree)


def test_existing_finding_in_an_untouched_line_is_not_reported(repo):
    (repo / "page.qmd").write_text(f"Old {BAD} stays.\nPlain line.\nNew line.\n")
    report = _run()
    assert report.findings == [] and not report.skipped


def test_added_finding_is_reported(repo):
    (repo / "page.qmd").write_text(
        f"Old {BAD} stays.\nPlain line.\nNew $P \\land Q \\lor R$.\n")
    report = _run()
    assert [(f.line, f.rule) for _, f in report.findings] == [(3, "mixed")]


def test_moved_line_is_not_new(repo):
    (repo / "page.qmd").write_text(f"Plain line.\nOld {BAD} stays.\n")
    assert _run().findings == []


def test_whole_tree_reports_the_existing_finding(repo):
    report = _run(whole_tree=True)
    assert [f.line for _, f in report.findings] == [1, 1]


def test_no_base_ref_skips_instead_of_scanning(repo):
    assert _run(base_ref="").skipped


def test_unresolvable_base_ref_skips(repo):
    assert _run(base_ref="no-such-ref").skipped


# -- main() ------------------------------------------------------------------

def test_main_blocks_by_default(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text(f"New {BAD}.\n")
    monkeypatch.setenv("CPP_BASE_REF", "HEAD")
    monkeypatch.delenv("CPP_FAIL", raising=False)
    assert cpp.main() == 1
    assert "::error file=page.qmd,line=1::" in capsys.readouterr().out


def test_main_warns_when_fail_is_false(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text(f"New {BAD}.\n")
    monkeypatch.setenv("CPP_BASE_REF", "HEAD")
    monkeypatch.setenv("CPP_FAIL", "false")
    assert cpp.main() == 0
    assert "::warning file=page.qmd,line=1::" in capsys.readouterr().out


def test_main_skips_without_a_base(repo, monkeypatch):
    (repo / "page.qmd").write_text(f"New {BAD}.\n")
    monkeypatch.delenv("CPP_BASE_REF", raising=False)
    assert cpp.main() == 0


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
          _ROOT / ".github" / "workflows" / "check-precedence-parens.yml"]


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_defaults_agree_with_the_script(path):
    assert _default(path, "globs") == cpp.DEFAULT_GLOBS
    assert _default(path, "fail") == str(cpp._DEFAULT_FAIL).lower()
