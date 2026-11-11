"""Unit tests for check-extracted-lemmas.

Covers which bodies are read (solutions, examples, proofs), what counts as a
general fact stated without a lemma, what is not flagged, and diff scoping.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_extracted_lemmas", _DIR / "check-extracted-lemmas.py"
)
assert _spec is not None and _spec.loader is not None
el = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(el)

GENERAL = "For any random variable $Z$, $E[Z^2] = Var(Z) + (E Z)^2$."


def div(ident: str, body: str) -> str:
    return f"::: {{#{ident}}}\n\n{body}\n\n:::\n\n"


def proof(body: str) -> str:
    return f"::: {{.proof}}\n\n{body}\n\n:::\n\n"


def msgs(text: str):
    stream = el.flatten("p.qmd", {"p.qmd": text.split("\n")})
    return [f.message for f in el.check_page(stream, None)]


def test_solution_stating_a_general_fact_is_flagged():
    out = msgs(div("sol-a", GENERAL))
    assert len(out) == 1 and "#sol-a" in out[0]


def test_example_is_not_read():
    assert msgs(div("exm-a", GENERAL)) == []


def test_proof_following_a_theorem_is_flagged():
    out = msgs(div("thm-a", "T.") + proof(GENERAL))
    assert len(out) == 1 and "#thm-a" in out[0]


def test_proof_nested_in_a_theorem_is_flagged():
    out = msgs(div("thm-a", "T.\n\n" + proof(GENERAL).rstrip()))
    assert len(out) == 1 and "#thm-a" in out[0]


@pytest.mark.parametrize("word", ["any", "every", "all", "Any"])
def test_general_words_are_recognized(word):
    assert len(msgs(div("sol-a", f"For {word} real number $x$, $x^2 \\ge 0$."))) == 1


@pytest.mark.parametrize("sentence", [
    "The value is $y$ for every $i$.",
    "It is negative for every year up to 1950, and $f > 0$ later.",
    "Each fit uses the same $p$ for every mother.",
])
def test_a_quantifier_over_a_setting_specific_index_is_not_flagged(sentence):
    assert msgs(div("sol-a", sentence)) == []


@pytest.mark.parametrize("sentence", [
    # lds sol-how-many-units-part6 (gha#1480): a denied universal claim.
    "The $O(2^n)$ is the cost of the construction, not a floor for any particular function.",
    "There is no bound for every function $f$.",
    "It isn't true for all real numbers $x$.",
])
def test_a_negated_quantifier_is_not_flagged(sentence):
    assert msgs(div("sol-a", sentence)) == []


@pytest.mark.parametrize("sentence", [
    # A negation far from the quantifier, or after it, does not cancel it.
    "Do not forget: the identity holds for any real number $x$ and any $y$.",
    "For any real number $x$, $x^2 \\ge 0$, so it is not negative.",
    "The square is never negative, so we also have $x^2 + 1 > 0$ for every real number $x$.",
])
def test_a_negation_outside_the_window_does_not_cancel_the_quantifier(sentence):
    assert len(msgs(div("sol-a", sentence))) == 1


def test_a_quantifier_inside_inline_code_is_not_flagged():
    assert msgs(div("sol-a", "Run `for all real number x` and see $x$.")) == []


def test_theorem_statement_itself_is_not_read():
    assert msgs(div("thm-a", GENERAL)) == []


def test_lemma_and_definition_statements_are_not_read():
    assert msgs(div("lem-a", GENERAL) + div("def-a", GENERAL)) == []


@pytest.mark.parametrize("cite", [
    "By @lem-second-moment, ", "By @thm-b, ", "By @cor-c, ", "By @prp-d, ",
    "By the [lemma](https://x.example/p.html#lem-second-moment), ",
    "By the [result](other.qmd#thm-b), "])
def test_citing_a_result_passes(cite):
    assert msgs(div("sol-a", cite + GENERAL.lower())) == []


def test_citing_a_solution_does_not_count():
    assert len(msgs(div("sol-a", "As in @sol-b, " + GENERAL))) == 1


def test_general_words_without_math_are_not_flagged():
    assert msgs(div("sol-a", "For any reader, this is clear.")) == []


def test_math_in_another_sentence_is_not_flagged():
    assert msgs(div("sol-a", "For any reader, this is clear. Then $x = 1$.")) == []


def test_fact_in_display_math_only_is_not_flagged():
    assert msgs(div("sol-a", "$$\n\\text{for any } x\n$$")) == []


def test_allow_comment_exempts():
    assert msgs(div("sol-a", "<!-- lemma-ok: stated in the exercise -->\n" + GENERAL)) == []
    assert msgs(div("thm-a", "T.") + proof("<!-- lemma-ok: reason -->\n" + GENERAL)) == []


def test_proof_after_unrelated_div_is_not_the_theorem_proof():
    assert msgs(div("thm-a", "T.") + div("rem-a", "Note.") + proof(GENERAL)) == []


def test_theorem_without_a_proof_is_not_flagged():
    assert msgs(div("thm-a", "T.")) == []


def test_fact_in_a_subfile_is_found():
    files = {
        "page.qmd": "{{< include _s/_sol.qmd >}}\n".split("\n"),
        "_s/_sol.qmd": div("sol-a", GENERAL).split("\n"),
    }
    assert len(el.check_page(el.flatten("page.qmd", files), None)) == 1


def test_include_inside_a_code_fence_is_not_expanded():
    files = {"p.qmd": "```\n{{< include q.qmd >}}\n```".split("\n"), "q.qmd": ["x"]}
    assert len(el.flatten("p.qmd", files)) == 3


# -- diff scoping ------------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow: synthetic test address
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "p.qmd").write_text(div("sol-a", GENERAL))
    (tmp_path / "q.qmd").write_text("Prose.\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(whole_tree=False, base="HEAD"):
    return el.run_check(base, ["*.qmd"], [], whole_tree)


def test_old_violation_is_not_reflagged_in_diff_mode(repo):
    _git(repo, "checkout", "-q", "-b", "pr")
    (repo / "q.qmd").write_text("Other.\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "other")
    assert run(base="main").findings == []


def test_whole_tree_reports_the_old_violation(repo):
    assert len(run(whole_tree=True).findings) == 1


def test_edited_body_is_reported_in_diff_mode(repo):
    _git(repo, "checkout", "-q", "-b", "pr")
    (repo / "p.qmd").write_text(div("sol-a", GENERAL + "\n\nMore."))
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "edit")
    assert len(run(base="main").findings) == 1


def test_no_base_skips(repo):
    assert run(base="").skipped


def test_blocks_by_default(repo, monkeypatch, capsys):
    # gha#1480: the default is fail, and EL_FAIL=false only warns.
    monkeypatch.setenv("EL_WHOLE_TREE", "true")
    monkeypatch.delenv("EL_FAIL", raising=False)
    assert el.main() == 1
    assert "::error" in capsys.readouterr().out
    monkeypatch.setenv("EL_FAIL", "false")
    assert el.main() == 0
    assert "::warning" in capsys.readouterr().out
    monkeypatch.setenv("EL_FAIL", "true")
    assert el.main() == 1
    assert "::error" in capsys.readouterr().out


@pytest.mark.parametrize("sentence", [
    # Spaced math counts as one word, so the negation stays in the window.
    "It is not true that $x + y = 0$ for every real number $x$.",
    # Emphasis, quotes and brackets around the negation do not hide it.
    "It is **not** a bound for every real number $x$.",
    'It is "not" a bound for every real number $x$.',
    "It is (*not*) a bound for every real number $x$.",
])
def test_a_negation_with_markup_or_spaced_math_still_cancels(sentence):
    assert not el.states_general_fact(sentence)


@pytest.mark.parametrize("path, pattern", [
    ("action.yml", r"\n  fail:\n(?:    .*\n)*?    default: '(\w+)'"),
    (".github/workflows/check-extracted-lemmas.yml",
     r"\n      fail:\n(?:        .*\n)*?        default: (\w+)"),
])
def test_yaml_fail_defaults_agree_with_the_script(path, pattern):
    import re
    root = _DIR if path == "action.yml" else _DIR.parent
    text = (root / path).read_text()
    m = re.search(pattern, text)
    assert m is not None, path
    assert (m.group(1) == "true") is el._DEFAULT_FAIL
