"""Unit tests for check-equation-labels.

Covers a labeled and an unlabeled equation, one-line and multi-line, two on
one line, what does not count (code fences, code spans, HTML comments, an
escaped dollar, inline math), the blank-line guard against a stray `$$`, the
allow pragma and its reason, diff scoping, the skip-not-fallback guard, and
the defaults the action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_equation_labels", _DIR / "check-equation-labels.py"
)
assert _spec is not None and _spec.loader is not None
cel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cel)

FENCE = "`" * 3
LABELED = "Text.\n\n$$\na = b\n$$ {#eq-a}\n\nMore.\n"
UNLABELED = "Text.\n\n$$\na = b\n$$\n\nMore.\n"


def found(text: str):
    """(start, end) of each finding, for a document string."""
    return [(f.start, f.end) for f in cel.scan_file(text.split("\n"))]


# -- what is flagged -----------------------------------------------------------

def test_labeled_multiline_equation_is_clean():
    assert found(LABELED) == []


def test_unlabeled_multiline_equation_is_flagged():
    assert found(UNLABELED) == [(3, 5)]


def test_one_line_equations():
    assert found("$$a = b$$ {#eq-a}\n") == []
    assert found("$$a = b$$\n") == [(1, 1)]


def test_label_with_other_attributes_is_clean():
    assert found("$$a = b$$ {#eq-a .unnumbered}\n") == []
    assert found("$$a = b$$ {.foo #eq-a}\n") == []


def test_attribute_block_without_eq_label_is_flagged():
    assert found("$$a = b$$ {#fig-a}\n") == [(1, 1)]


def test_aligned_environment_inside_display_math():
    doc = "$$\n\\begin{aligned}\na &= b\n\\end{aligned}\n$$ {#eq-b}\n"
    assert found(doc) == []


def test_two_equations_on_one_line_are_judged_apart():
    assert found("$$a$$ {#eq-a} and $$b$$\n") == [(1, 1)]


def test_second_of_two_equations_is_flagged():
    doc = "$$\na = b\n$$ {#eq-a}\n\ntext\n\n$$c = d$$\n"
    assert found(doc) == [(7, 7)]


def test_body_is_reported():
    (f,) = cel.scan_file("$$\nx  =\n  y\n$$\n".split("\n"))
    assert f.body == "x = y"
    assert "x = y" in cel.format_message(f)


# -- what is not counted -------------------------------------------------------

def test_code_fence_is_ignored():
    assert found(FENCE + "r\nx <- '$$a$$'\n" + FENCE + "\n") == []


def test_tilde_fence_is_ignored():
    assert found("~~~\n$$a$$\n~~~\n") == []


def test_code_span_is_ignored():
    assert found("Write `$$a$$` for display math.\n") == []


def test_html_comment_is_ignored():
    assert found("<!--\n$$a = b$$\n-->\n") == []
    assert found("text <!-- $$a$$ --> text\n") == []


def test_escaped_dollar_is_not_a_delimiter():
    assert found("It costs \\$$5 and \\$$6.\n") == []


def test_inline_math_is_ignored():
    assert found("inline $x$ only\n") == []


def test_stray_opener_ends_at_a_blank_line():
    doc = "$$\na\n\n$$b$$ {#eq-b}\n"
    # The stray opener on line 1 never closes, so it is no equation, and the
    # labeled equation after the blank line still reads as labeled.
    assert found(doc) == []


# -- the allow pragma ----------------------------------------------------------

def test_allow_pragma_with_a_reason_exempts():
    doc = "<!-- check-equation-labels: allow: shows the syntax -->\n$$a$$\n"
    assert found(doc) == []
    assert found("$$a$$ <!-- check-equation-labels: allow: syntax -->\n") == []


def test_allow_pragma_without_a_reason_does_not_exempt():
    doc = "<!-- check-equation-labels: allow: -->\n$$a$$\n"
    assert found(doc) == [(2, 2)]


def test_allow_pragma_two_lines_up_does_not_exempt():
    doc = "<!-- check-equation-labels: allow: syntax -->\n\n$$a$$\n"
    assert found(doc) == [(3, 3)]


# -- diff scoping --------------------------------------------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow: synthetic test address
    _git(tmp_path, "config", "user.name", "t")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", name)


def _commit(repo, name, text):
    _write(repo, name, text)
    _git(repo, "commit", "-q", "-m", "c")


def _run(base):
    return cel.run_check(base, [cel.DEFAULT_GLOBS], [], False)


def test_untouched_equation_is_grandfathered(repo):
    _commit(repo, "old.qmd", UNLABELED)
    _write(repo, "old.qmd", UNLABELED + "\nA new paragraph.\n")
    report = _run("HEAD")
    assert not report.skipped and report.findings == []


def test_editing_the_equation_flags_it(repo):
    _commit(repo, "old.qmd", UNLABELED)
    _write(repo, "old.qmd", UNLABELED.replace("a = b", "a = c"))
    assert [(p, f.start) for p, f in _run("HEAD").findings] == [("old.qmd", 3)]


def test_new_unlabeled_equation_is_flagged(repo):
    _commit(repo, "old.qmd", LABELED)
    _write(repo, "old.qmd", LABELED + "\n$$c = d$$\n")
    assert [(p, f.start) for p, f in _run("HEAD").findings] == [("old.qmd", 9)]


def test_labeling_one_equation_does_not_flag_its_neighbour(repo):
    two = UNLABELED + "\n$$\nc = d\n$$\n"
    _commit(repo, "old.qmd", two)
    _write(repo, "old.qmd", two.replace("a = b\n$$\n", "a = b\n$$ {#eq-a}\n", 1))
    assert _run("HEAD").findings == []


def test_no_base_ref_skips_instead_of_scanning_the_tree(repo):
    _commit(repo, "old.qmd", UNLABELED)
    assert _run("").skipped


def test_unresolvable_base_ref_skips(repo):
    _commit(repo, "old.qmd", UNLABELED)
    assert _run("no-such-ref").skipped


def test_whole_tree_flags_every_equation(repo):
    _commit(repo, "old.qmd", UNLABELED)
    _commit(repo, "sub/_part.qmd", "$$x$$\n")
    report = cel.run_check("", [cel.DEFAULT_GLOBS], [], True)
    assert [(p, f.start) for p, f in report.findings] == [
        ("old.qmd", 3), ("sub/_part.qmd", 1)]
    assert report.files == 2


def test_paths_ignore_is_honoured(repo):
    _commit(repo, "old.qmd", UNLABELED)
    ignores = cel.diffscope.compile_ignores(["old.qmd"])
    assert cel.run_check("", [cel.DEFAULT_GLOBS], ignores, True).findings == []


# -- defaults agree across script, action and workflow ----------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-equation-labels.yml").read_text(encoding="utf-8")
    assert cel._DEFAULT_FAIL is True
    assert "default: 'true'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: true" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert f"default: '{cel.DEFAULT_GLOBS}'" in action
    assert f"default: '{cel.DEFAULT_GLOBS}'" in workflow
    for name in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"CEL_{name}" in action


def test_main_exit_codes(repo, monkeypatch):
    _commit(repo, "old.qmd", UNLABELED)
    monkeypatch.setenv("CEL_WHOLE_TREE", "true")
    assert cel.main() == 1
    monkeypatch.setenv("CEL_FAIL", "false")
    assert cel.main() == 0
