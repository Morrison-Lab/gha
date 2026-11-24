r"""Unit tests for check-double-inequalities.

Covers what counts as a finding (three operands joined by two order
relations pointing the same way, at any group depth), what does not (a
longer chain, a chain mixing in ``=``, opposite directions, a clause split by
a separator or a connective), what is skipped (code fences and spans,
comments, front matter, the allow comment, which needs a reason), the diff
scoping, and the defaults the script, the action and the reusable workflow
must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_double_inequalities", _DIR / "check-double-inequalities.py"
)
assert _spec is not None and _spec.loader is not None
cdi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cdi)


def found(text: str):
    """[(line, detail)] for a document given as one string."""
    hits, _ = cdi.scan_file(text.split("\n"))
    return [(h.line, h.detail) for h in hits]


# -- what is flagged ---------------------------------------------------------

@pytest.mark.parametrize("math", [
    "a < x < b",
    "0 \\le p \\le 1",
    "0 < \\varpar < \\infty",
    "a \\lt x \\leq b",
    "t \\le T < t + h",
    "b > x \\ge a",
    "1 \\geq p \\gt 0",
    "0 ≤ p ≤ 1",
    "x \\preceq y \\prec z",
    "0 \\leqslant p \\leqslant 1",
])
def test_double_inequality_is_flagged(math):
    assert len(cdi.check_math(math)) == 1


def test_event_inside_a_macro_argument_is_flagged():
    assert cdi.check_math("\\Pr{a < X \\le b} = F(b) - F(a)") == ["a < X \\le b"]


def test_each_clause_of_a_list_is_checked():
    assert len(cdi.check_math("0 < a < 1, \\quad 0 < b < 1")) == 2


def test_message_names_the_clause_and_the_rule():
    message = cdi.format_message(cdi.Finding(3, "0 < x < 1"))
    assert "'0 < x < 1'" in message
    assert "x \\in (a, b)" in message
    assert "Avoiding double inequalities" in message


# -- what is not flagged -----------------------------------------------------

@pytest.mark.parametrize("math", [
    "x \\in (a, b)",
    "p \\in [0, 1]",
    "a < b",                               # one relation
    "x_1 < x_2 < x_3 < x_4",               # an ordering chain
    "x_1 < x_2 < \\dots < x_n",
    "a \\le b = c",                        # a derivation
    "a = b \\le c",
    "a < x > b",                           # opposite directions
    "a \\le x \\ge b",
    "0 < a, b < 1",                        # the comma ends the clause
    "a < x \\land x < b",                  # a connective ends it too
    "a < x \\text{ and } x < b",
    "a < x & < b",                         # an aligned row's step
    "< x < b",                             # an empty operand
])
def test_single_or_out_of_scope_is_not_flagged(math):
    assert cdi.check_math(math) == []


# -- math spans --------------------------------------------------------------

def test_prose_outside_math_is_not_read():
    assert found("Take a < x < b in words, or 0 <= p <= 1.") == []


def test_display_math_lines_are_read():
    assert [line for line, _ in found("$$\n0 \\le p \\le 1\n$$")] == [2]


# -- skips -------------------------------------------------------------------

BAD = "$0 \\le p \\le 1$"


def test_code_fence_is_skipped():
    assert found(f"```\n{BAD}\n```") == []
    assert len(found(f"```tex\n{BAD}\n```\n{BAD}")) == 1


def test_code_span_is_skipped():
    assert found("Type `$0 \\le p \\le 1$` here.") == []


def test_html_comment_is_skipped():
    assert found(f"<!-- {BAD} -->") == []


def test_front_matter_is_skipped():
    assert [line for line, _ in found(f"---\ntitle: '{BAD}'\n---\n{BAD}")] == [4]


def test_allow_comment_on_the_line_or_the_line_before():
    allow = "<!-- check-double-inequalities: allow: the rule's own example -->"
    assert found(f"{BAD} {allow}") == []
    assert found(f"{allow}\n{BAD}") == []
    assert len(found(f"{allow}\n\n{BAD}")) == 1


def test_allow_comment_needs_a_reason():
    assert len(found(f"{BAD} <!-- check-double-inequalities: allow -->")) == 1
    assert len(found(f"{BAD} <!-- check-double-inequalities: allow: -->")) == 1


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
    return cdi.run_check(base_ref, ["*.qmd"], cdi.diffscope.compile_ignores([]),
                         whole_tree)


def test_existing_finding_in_an_untouched_line_is_not_reported(repo):
    (repo / "page.qmd").write_text(f"Old {BAD} stays.\nPlain line.\nNew line.\n")
    report = _run()
    assert report.findings == [] and not report.skipped


def test_added_finding_is_reported(repo):
    (repo / "page.qmd").write_text(
        f"Old {BAD} stays.\nPlain line.\nNew $a < x < b$.\n")
    assert [f.line for _, f in _run().findings] == [3]


def test_moved_line_is_not_new(repo):
    (repo / "page.qmd").write_text(f"Plain line.\nOld {BAD} stays.\n")
    assert _run().findings == []


def test_whole_tree_reports_the_existing_finding(repo):
    assert [f.line for _, f in _run(whole_tree=True).findings] == [1]


def test_no_base_ref_skips_instead_of_scanning(repo):
    assert _run(base_ref="").skipped


def test_unresolvable_base_ref_skips(repo):
    assert _run(base_ref="no-such-ref").skipped


# -- main() ------------------------------------------------------------------

def test_main_blocks_by_default(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text(f"New {BAD}.\n")
    monkeypatch.setenv("CDI_BASE_REF", "HEAD")
    monkeypatch.delenv("CDI_FAIL", raising=False)
    assert cdi.main() == 1
    assert "::error file=page.qmd,line=1::" in capsys.readouterr().out


def test_main_warns_when_fail_is_false(repo, monkeypatch, capsys):
    (repo / "page.qmd").write_text(f"New {BAD}.\n")
    monkeypatch.setenv("CDI_BASE_REF", "HEAD")
    monkeypatch.setenv("CDI_FAIL", "false")
    assert cdi.main() == 0
    assert "::warning file=page.qmd,line=1::" in capsys.readouterr().out


def test_main_skips_without_a_base(repo, monkeypatch):
    (repo / "page.qmd").write_text(f"New {BAD}.\n")
    monkeypatch.delenv("CDI_BASE_REF", raising=False)
    assert cdi.main() == 0


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
          _ROOT / ".github" / "workflows" / "check-double-inequalities.yml"]


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_defaults_agree_with_the_script(path):
    assert _default(path, "globs") == cdi.DEFAULT_GLOBS
    assert _default(path, "fail") == str(cdi._DEFAULT_FAIL).lower()
