r"""Unit tests for check-swallowed-citations.

Covers what counts as a finding (an in-text crossref followed by a citation
bracket on the same line or at the start of the next one), what is not
(punctuation between them, a crossref inside a bracket, a link, a blank line,
an ordinary citation), what is skipped (code fences and spans, comments, front
matter, the allow comment), the two-line scope, main()'s exit codes under the
CSC_ prefix, and the defaults the action, the reusable workflow and the script
must agree on. The diff model is the shared engine in check-write-idiom, which
has its own tests.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_swallowed_citations", _DIR / "check-swallowed-citations.py"
)
assert _spec is not None and _spec.loader is not None
csc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csc)


def found(text: str, keep=None):
    """{bracket line: (ref line, ref, cite)} for a document given as one string."""
    hits, _ = csc.scan_file(text.split("\n"), keep)
    return {h.line: (h.ref_line, h.ref, h.cite) for h in hits}


# -- findings ----------------------------------------------------------------

@pytest.mark.parametrize("text, ref, cite", [
    ("as in @eq-recurrent-layer [@pascanu2014construct, section 3.3.2].",
     "eq-recurrent-layer", "[@pascanu2014construct, section 3.3.2]"),
    ("See @fig-x [@key].", "fig-x", "[@key]"),
    ("See @def-bias [-@key].", "def-bias", "[-@key]"),
    ("See @thm-clt [see @key, p. 3].", "thm-clt", "[see @key, p. 3]"),
    ("See @sec-intro   [@a; @b].", "sec-intro", "[@a; @b]"),
    ("Defined in @def-a.b-c [@key].", "def-a.b-c", "[@key]"),
])
def test_flagged_on_one_line(text, ref, cite):
    assert found(text) == {1: (1, ref, cite)}


def test_the_case_that_prompted_the_check_spans_a_line_break():
    # Morrison-Lab/lds#3239: the bracket opens the next line.
    text = "... as in @eq-recurrent-layer\n[@pascanu2014construct, section 3.3.2]."
    assert found(text) == {
        2: (1, "eq-recurrent-layer", "[@pascanu2014construct, section 3.3.2]")}


def test_leading_spaces_on_the_next_line_still_swallow():
    assert found("as in @eq-x\n   [@key]") == {2: (1, "eq-x", "[@key]")}


def test_each_crossref_on_a_line_is_judged():
    text = "@fig-a [@k1] and @fig-b [@k2]."
    hits, _ = csc.scan_file([text])
    assert [(h.ref, h.cite) for h in hits] == [("fig-a", "[@k1]"), ("fig-b", "[@k2]")]


# -- not flagged -------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "as in @eq-x, following [@key].",
    "as in @eq-x. [@key] shows it.",
    "as in @eq-x; [@key]",
    "as in [@eq-x] [@key].",
    "as in [see @eq-x] [@key].",
    "as in @eq-x [@key](https://example.org).",
    "as in @eq-x [text].",
    "as in @eq-x [a span]{.hl}.",
    "as in @eq-x [link][ref].",
    "@key [@other] is an ordinary citation pair.",
    "Mail me@eq-x.org [@key].",  # phi-allow
    "as in @eq-x and later [@key].",
    "@eq-x [email me@key.org]",  # phi-allow
])
def test_unflagged_forms(text):
    assert found(text) == {}


def test_punctuation_ending_the_line_breaks_the_carry():
    assert found("as in @eq-x.\n[@key] says so.") == {}


def test_a_blank_line_ends_the_carry():
    assert found("as in @eq-x\n\n[@key] says so.") == {}


def test_a_crossref_not_ending_its_line_is_not_carried():
    assert found("as in @eq-x here\n[@key] says so.") == {}


def test_carry_stops_after_one_line():
    assert found("as in @eq-x\nplain prose\n[@key]") == {}


def test_code_fence_is_skipped():
    assert found("```\nas in @eq-x [@key]\n```") == {}


def test_code_span_is_skipped():
    assert found("Type `@eq-x [@key]` here.") == {}


def test_html_comment_is_skipped():
    assert found("<!-- @eq-x [@key] -->") == {}


def test_front_matter_is_skipped():
    assert found("---\ntitle: '@eq-x [@key]'\n---\nbody") == {}


def test_allow_comment_with_a_reason_on_the_line_or_the_line_before():
    allow = "<!-- check-swallowed-citations: allow: suffix is deliberate -->"
    assert found(f"@eq-x [@key] {allow}") == {}
    assert found(f"{allow}\n@eq-x [@key]") == {}


def test_allow_comment_without_a_reason_does_not_exempt():
    assert found("@eq-x [@key] <!-- check-swallowed-citations: allow -->") == {
        1: (1, "eq-x", "[@key]")}
    assert found("@eq-x [@key] <!-- check-swallowed-citations: allow: -->") == {
        1: (1, "eq-x", "[@key]")}


# -- scope: a finding spans two lines ----------------------------------------

def test_kept_when_only_the_crossref_line_is_added():
    text = "as in @eq-x\n[@key]"
    assert found(text, keep={1}) == {2: (1, "eq-x", "[@key]")}


def test_kept_when_only_the_bracket_line_is_added():
    text = "as in @eq-x\n[@key]"
    assert found(text, keep={2}) == {2: (1, "eq-x", "[@key]")}


def test_dropped_when_neither_line_is_added():
    text = "prose\nas in @eq-x\n[@key]"
    assert found(text, keep={1}) == {}


def test_message_names_the_fix_and_the_source():
    message = csc.format_message(csc.Finding(2, 1, "eq-x", "[@key]"))
    assert "@eq-x" in message and "[@key]" in message
    assert '"@eq-x, following [@key]"' in message
    assert "lds#3239" in message


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
    for key in ("CSC_BASE_REF", "CSC_GLOBS", "CSC_PATHS_IGNORE", "CSC_FAIL",
                "CSC_WHOLE_TREE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CSC_BASE_REF", "HEAD")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_main_fails_by_default_and_warns_when_fail_is_off(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("prose\nas in @eq-x [@key].\n")
    git("add", "-A")
    _main_env(monkeypatch, repo)
    assert csc.main() == 1
    assert "::error file=page.qmd,line=2::" in capsys.readouterr().out
    monkeypatch.setenv("CSC_FAIL", "false")
    assert csc.main() == 0
    assert "::warning file=page.qmd,line=2::" in capsys.readouterr().out


def test_main_reports_a_bracket_under_an_added_crossref_line(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("as in the formula\n[@key] says so.\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old prose")
    (repo / "page.qmd").write_text("as in @eq-x\n[@key] says so.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo)
    assert csc.main() == 1
    assert "::error file=page.qmd,line=2::" in capsys.readouterr().out


def test_main_reports_only_added_lines(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("as in @eq-x [@key].\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old prose")
    (repo / "page.qmd").write_text("as in @eq-x [@key].\nNew prose.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo)
    assert csc.main() == 0
    assert "No citation is swallowed" in capsys.readouterr().out


def test_main_without_base_skips_under_its_own_name(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("@eq-x [@key]\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CSC_BASE_REF="")
    assert csc.main() == 0
    assert capsys.readouterr().out.startswith("Skipping the swallowed-citations check")


# -- the action, the workflow and the script agree ---------------------------

def test_defaults_agree_across_action_workflow_and_script():
    workflows = _DIR.parent / ".github/workflows"
    if (workflows / ".restored-from-default-branch").is_file():
        # The review job restores the default branch's workflows (gha#765),
        # which may not hold this one yet.
        pytest.skip("workflows restored from the default branch")
    action = (_DIR / "action.yml").read_text()
    workflow = (workflows / "check-swallowed-citations.yml").read_text()
    for text in (action, workflow):
        assert f"default: '{csc.DEFAULT_GLOBS}'" in text
    assert csc._DEFAULT_FAIL is True
    assert re.search(r"fail:\n(?:.*\n)*?\s+default: 'true'", action)
    assert re.search(r"fail:\n(?:.*\n)*?\s+default: true", workflow)


def test_action_passes_every_input_to_the_script_under_the_csc_prefix():
    action = (_DIR / "action.yml").read_text()
    for var in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"CSC_{var}:" in action
