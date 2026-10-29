r"""Unit tests for check-proof-statements.

Covers the hidden-proof rule (wrapper forms, includes, the touched-file scope),
the statement-reasoning rule (what counts, what passes, the proof boundary),
masking, the allow comment, main()'s exit codes under the CPS_ prefix, and the
defaults the action, the reusable workflow and the script must agree on. The
diff model is the shared engine in check-write-idiom, which has its own tests.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_proof_statements", _DIR / "check-proof-statements.py"
)
assert _spec is not None and _spec.loader is not None
cps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cps)

# The theorem file of Morrison-Lab/mds#534 as pushed in commit 073a459: the
# statement carries "so ..." clauses and the proof is hidden from the slides.
MDS_534 = """\
:::{#thm-second-derivative-test}
#### Second derivative test

Let $c$ be a [flat point](#def-flat-point) of $f$,
where the [second derivative](calculus-derivatives.qmd#def-second-derivative) $f''(c)$ is defined.

- If $f''(c) > 0$, then $f(x) > f(c)$ for every $x \\ne c$ in some [open interval](sets.qmd#def-open-interval) around $c$,
  so $c$ is a [local minimizer](algebra.qmd#def-local-minimizer).
- If $f''(c) < 0$, then $f(x) < f(c)$ for every $x \\ne c$ in some open interval around $c$,
  so $f$ is largest at $c$ among the points near $c$.

:::

{{< slidebreak >}}

::: {.content-hidden when-format="revealjs"}

::: proof

Suppose $f''(c) > 0$.
Because $f'(c) = 0$, the [derivative](calculus-derivatives.qmd#def-derivative) of $f'$ at $c$ is

$$f''(c) = \\lim_{x \\to c} \\frac{f'(x)}{x - c}.$$

Hence $f' < 0$ to the left of $c$ and $f' > 0$ to the right of $c$,
so $f$ is decreasing to the left of $c$ and increasing to the right of $c$.

:::

:::
"""


def scan(text: str, keep=None):
    """[(line, rule, phrase)] for a document given as one string."""
    hits, _ = cps.scan_file(text.split("\n"), keep)
    return [(h.line, h.rule, h.phrase) for h in hits]


HIDDEN = '::: {.content-hidden when-format="revealjs"}'


# -- hidden proofs -----------------------------------------------------------

def test_mds_534_theorem_is_flagged_for_both_rules():
    assert scan(MDS_534) == [
        (8, "statement", "so"),
        (10, "statement", "so"),
        (18, "proof", "proof"),
    ]


@pytest.mark.parametrize("wrapper", [
    '::: {.content-hidden when-format="revealjs"}',
    "::: {.content-hidden when-format='revealjs'}",
    '::: {.content-hidden when-format="revealjs pdf"}',
    '::: {.content-visible unless-format="revealjs"}',
    '::::: {.content-hidden when-format="revealjs"}',
])
def test_hidden_wrapper_forms(wrapper):
    colons = wrapper.split()[0]
    text = f"{wrapper}\n\n::: proof\nBy cases.\n:::\n\n{colons}\n"
    assert scan(text) == [(3, "proof", "proof")]


@pytest.mark.parametrize("opening", [
    "::: proof",
    "::: {.proof}",
    "::: {#prf-main}",
    "::: {#prf-main .proof}",
])
def test_proof_div_spellings(opening):
    text = f"{HIDDEN}\n{opening}\nBy cases.\n:::\n:::\n"
    assert scan(text) == [(2, "proof", "proof")]


def test_include_of_a_proof_subfile_in_a_hidden_wrapper_is_flagged():
    text = f"{HIDDEN}\n{{{{< include _prf-main.qmd >}}}}\n:::\n"
    assert scan(text) == [(2, "proof", "proof")]


def test_include_of_another_subfile_in_a_hidden_wrapper_passes():
    text = f"{HIDDEN}\n{{{{< include _exm-main.qmd >}}}}\n:::\n"
    assert scan(text) == []


def test_proof_with_the_hidden_class_on_the_same_div_is_flagged():
    text = '::: {.proof .content-hidden when-format="revealjs"}\nBy cases.\n:::\n'
    assert scan(text) == [(1, "proof", "proof")]


@pytest.mark.parametrize("text", [
    "::: proof\nBy cases.\n:::\n",
    '::: {.content-hidden when-format="pdf"}\n::: proof\nBy cases.\n:::\n:::\n',
    '::: {.content-hidden when-format="html"}\n::: proof\nx\n:::\n:::\n',
    '::: {.content-visible when-format="revealjs"}\n::: proof\nx\n:::\n:::\n',
    '::: {.content-visible unless-format="pdf"}\n::: proof\nx\n:::\n:::\n',
])
def test_shown_proofs_pass(text):
    assert scan(text) == []


def test_proof_after_a_closed_hidden_wrapper_passes():
    text = f"{HIDDEN}\nHidden note.\n:::\n\n::: proof\nBy cases.\n:::\n"
    assert scan(text) == []


def test_hidden_remark_without_a_proof_passes():
    assert scan(f"{HIDDEN}\n::: {{#rem-x}}\nA remark.\n:::\n:::\n") == []


def test_hidden_proof_is_reported_when_the_file_is_touched_elsewhere():
    text = f"Intro line.\n{HIDDEN}\n::: proof\nx\n:::\n:::\n"
    assert scan(text, keep={1}) == [(3, "proof", "proof")]


def test_hidden_proof_is_not_reported_in_an_untouched_file():
    text = f"Intro line.\n{HIDDEN}\n::: proof\nx\n:::\n:::\n"
    assert scan(text, keep=set()) == []


# -- reasoning in a theorem statement ----------------------------------------

@pytest.mark.parametrize("word", ["so", "because", "hence", "therefore", "thus", "since"])
def test_reasoning_words_are_flagged_in_a_statement(word):
    text = f"::: {{#thm-a}}\nThe sum is finite, {word} the mean exists.\n:::\n"
    assert scan(text) == [(2, "statement", word)]


@pytest.mark.parametrize("opening", ["#lem-a", "#cor-a", "#prp-a", "#thm-a"])
def test_every_theorem_type_is_a_statement(opening):
    text = f"::: {{{opening}}}\nIt holds, so it works.\n:::\n"
    assert scan(text) == [(2, "statement", "so")]


@pytest.mark.parametrize("line", [
    "Choose $\\delta$ so that the bound holds.",
    "A so-called flat point is a zero of $f'$.",
    "Let $f$ be continuous.",
    "The estimator is unbiased and the interval is also valid.",
    "Sodium is a solution of $a + b$.",
    "The variance is finite if $x$ is bounded.",
])
def test_statement_wording_that_passes(line):
    assert scan(f"::: {{#thm-a}}\n{line}\n:::\n") == []


def test_words_in_math_are_not_read():
    text = "::: {#thm-a}\nIf $a \\text{ so } b$ then\n\n$$x = y \\text{ because } z$$\n\nholds.\n:::\n"
    assert scan(text) == []


def test_multiline_display_math_is_not_read():
    text = "::: {#thm-a}\n$$\nx = y\n\\text{because } z\n$$\nholds.\n:::\n"
    assert scan(text) == []


def test_the_proof_inside_the_theorem_div_is_not_a_statement():
    text = "::: {#thm-a}\nIt holds.\n\n::: proof\nIt holds, because $x$.\n:::\n:::\n"
    assert scan(text) == []


def test_statement_resumes_after_a_nested_proof_closes():
    text = ("::: {#thm-a}\nIt holds.\n\n::: proof\nBecause $x$.\n:::\n\n"
            "Also it works, so done.\n:::\n")
    assert scan(text) == [(8, "statement", "so")]


def test_a_sibling_proof_div_is_not_a_statement():
    text = "::: {#thm-a}\nIt holds.\n:::\n\n::: proof\nIt holds, because $x$.\n:::\n"
    assert scan(text) == []


def test_other_divs_and_prose_are_not_statements():
    text = ("::: {#exm-a}\nSo it works, because $x$.\n:::\n\n"
            "::: {#def-a}\nA set is closed since it holds.\n:::\n\n"
            "Hence done.\n")
    assert scan(text) == []


def test_heading_in_a_statement_is_not_read():
    assert scan("::: {#thm-a}\n#### Since the limit exists\n\nIt holds.\n:::\n") == []


def test_statement_findings_are_limited_to_added_lines():
    text = "::: {#thm-a}\nOne, so two.\nThree, so four.\n:::\n"
    assert scan(text, keep={3}) == [(3, "statement", "so")]
    assert scan(text, keep=set()) == []


# -- masking and the allow comment -------------------------------------------

def test_code_fence_comment_and_front_matter_are_skipped():
    text = ("---\ntitle: so\n---\n"
            "::: {#thm-a}\n```\nso because\n```\n<!-- so hence -->\n"
            "`so` holds.\n:::\n")
    assert scan(text) == []


def test_allow_comment_on_the_line_or_the_line_before():
    allow = "<!-- check-proof-statements: allow -->"
    assert scan(f"::: {{#thm-a}}\nIt holds, so done. {allow}\n:::\n") == []
    assert scan(f"::: {{#thm-a}}\n{allow}\nIt holds, so done.\n:::\n") == []
    assert scan(f"{HIDDEN}\n{allow}\n::: proof\nx\n:::\n:::\n") == []


def test_allow_comment_on_a_div_line_keeps_the_div_state_balanced():
    allow = "<!-- check-proof-statements: allow -->"
    text = f"::: {{#thm-a}} {allow}\nIt holds.\n:::\n\nHence done.\n"
    assert scan(text) == []


def test_messages_name_the_fix_and_the_source():
    proof = cps.format_message(cps.Finding(1, "proof", "proof"))
    statement = cps.format_message(cps.Finding(1, "statement", "so"))
    assert "Show every proof on slides" in proof and "psw#426" in proof
    assert '"so"' in statement and "proof" in statement and "psw#426" in statement


# -- main(): the shared engine under this check's prefix and wording ---------

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


def _main_env(monkeypatch, repo, **extra):
    monkeypatch.chdir(repo)
    for key in ("CPS_BASE_REF", "CPS_GLOBS", "CPS_PATHS_IGNORE", "CPS_FAIL",
                "CPS_WHOLE_TREE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CPS_BASE_REF", "HEAD")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_main_warns_by_default_and_fails_on_request(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "thm.qmd").write_text(MDS_534)
    git("add", "-A")
    _main_env(monkeypatch, repo)
    assert cps.main() == 0
    out = capsys.readouterr().out
    assert "::warning file=thm.qmd,line=8::" in out
    assert "::warning file=thm.qmd,line=18::Show every proof on slides" in out
    monkeypatch.setenv("CPS_FAIL", "true")
    assert cps.main() == 1
    assert "::error file=thm.qmd,line=18::" in capsys.readouterr().out


def test_main_flags_a_hidden_proof_in_a_file_only_touched_elsewhere(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    page = repo / "thm.qmd"
    page.write_text(f"Intro.\n{HIDDEN}\n::: proof\nx\n:::\n:::\n")
    git("add", "-A")
    git("commit", "-q", "-m", "page")
    page.write_text(f"Intro, edited.\n{HIDDEN}\n::: proof\nx\n:::\n:::\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CPS_FAIL="true")
    assert cps.main() == 1
    assert "::error file=thm.qmd,line=3::" in capsys.readouterr().out


def test_main_does_not_sweep_an_untouched_file(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "old.qmd").write_text(MDS_534)
    git("add", "-A")
    git("commit", "-q", "-m", "old")
    (repo / "new.qmd").write_text("::: {#thm-b}\nIt holds.\n:::\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CPS_FAIL="true")
    assert cps.main() == 0
    assert "No hidden proof" in capsys.readouterr().out


def test_main_ignores_a_statement_line_the_diff_did_not_add(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    page = repo / "thm.qmd"
    page.write_text("::: {#thm-a}\nOne, so two.\nThree.\n:::\n")
    git("add", "-A")
    git("commit", "-q", "-m", "page")
    page.write_text("::: {#thm-a}\nOne, so two.\nThree, edited.\n:::\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CPS_FAIL="true")
    assert cps.main() == 0


def test_main_without_base_skips_under_its_own_name(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "thm.qmd").write_text(MDS_534)
    git("add", "-A")
    _main_env(monkeypatch, repo, CPS_FAIL="true", CPS_BASE_REF="")
    assert cps.main() == 0
    assert capsys.readouterr().out.startswith("Skipping the proof-statements check")


def test_other_prefixes_are_not_read(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "thm.qmd").write_text(MDS_534)
    git("add", "-A")
    _main_env(monkeypatch, repo)
    monkeypatch.setenv("CAW_FAIL", "true")
    monkeypatch.setenv("CWI_FAIL", "true")
    assert cps.main() == 0


# -- the action, the workflow and the script agree ---------------------------

def test_defaults_agree_across_action_workflow_and_script():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-proof-statements.yml").read_text()
    for text in (action, workflow):
        assert f"default: '{cps.DEFAULT_GLOBS}'" in text
    assert cps._DEFAULT_FAIL is False
    assert "default: 'false'" in action
    assert re.search(r"fail:\n(?:.*\n)*?\s+default: false", workflow)


def test_action_passes_every_input_to_the_script_under_the_cps_prefix():
    action = (_DIR / "action.yml").read_text()
    for var in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"CPS_{var}:" in action


# -- review findings (gha#1355) ----------------------------------------------

@pytest.mark.parametrize("wrapper", [
    '::: {when-format="revealjs" .content-hidden}',
    "::: {.content-hidden when-format=revealjs}",
    '::: {.content-hidden when-format="html, revealjs"}',
    '::: {unless-format="revealjs" .content-visible}',
])
def test_hidden_wrapper_attribute_order_and_quoting(wrapper):
    assert scan(f"{wrapper}\n::: proof\nx\n:::\n:::\n") == [(2, "proof", "proof")]


def test_a_word_in_a_quoted_attribute_is_not_a_class():
    text = '::: {#thm-a title="a proof of concept"}\nSo x holds.\n:::\n'
    assert scan(text) == [(2, "statement", "so")]
    hidden = f'{HIDDEN}\n::: {{.callout title="proof"}}\nx\n:::\n:::\n'
    assert scan(hidden) == []


@pytest.mark.parametrize("line", [
    "See [the set](sets.qmd#def-so-called-x) for details.",
    "See [y](#def-since-a).",
    "See <https://so.example.com/since>.",
    "See https://so.example.com/since for details.",
    "By @eq-hence-x the bound holds.",
    "The bound holds. {#sec-since}",
])
def test_links_urls_and_references_are_not_prose(line):
    assert scan(f"::: {{#thm-a}}\n{line}\n:::\n") == []


def test_prose_next_to_a_link_is_still_read():
    text = "::: {#thm-a}\nSee [the set](sets.qmd#def-x), so it holds.\n:::\n"
    assert scan(text) == [(2, "statement", "so")]


def test_display_math_closed_mid_line_hands_the_rest_back_to_prose():
    text = "::: {#thm-a}\n$$\nx = y\n$$ hence z.\n:::\n"
    assert scan(text) == [(4, "statement", "hence")]


def test_inline_display_pair_then_standalone_pair():
    text = "::: {#thm-a}\nLet $$ x = y $$\n$$\nz\n$$ hence w.\n:::\n"
    assert scan(text) == [(5, "statement", "hence")]


def test_main_finds_files_under_mnemonic_prefix_and_quoted_paths(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "ch").mkdir()
    page = f"{HIDDEN}\n::: proof\nx\n:::\n:::\n"
    (repo / "ch" / 'q"u.qmd').write_text(page)
    (repo / "plain.qmd").write_text(page)
    git("add", "-A")
    _main_env(monkeypatch, repo)
    for key, value in (("GIT_CONFIG_COUNT", "1"),
                       ("GIT_CONFIG_KEY_0", "diff.mnemonicPrefix"),
                       ("GIT_CONFIG_VALUE_0", "true")):
        monkeypatch.setenv(key, value)
    assert cps.main() == 0
    out = capsys.readouterr().out
    assert "across 2 file(s)" in out
    assert "::warning file=plain.qmd,line=2::" in out
    assert 'file=ch/q"u.qmd,line=2::' in out
