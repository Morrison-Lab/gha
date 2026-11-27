r"""Unit tests for check-citation-authors.

Covers what counts as a finding (a surname typed beside a citation whose key
starts with it), what is not (a suppressed author, crossrefs, emails, names in
link text or emphasis, a name in an earlier sentence), what is skipped (code
fences and spans, comments, front matter, the allow comment), main()'s exit
codes under the CCA_ prefix, and the defaults the action, the reusable
workflow and the script must agree on. The diff model is the shared engine in
check-write-idiom, which has its own tests.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_citation_authors", _DIR / "check-citation-authors.py"
)
assert _spec is not None and _spec.loader is not None
cca = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cca)


def found(text: str):
    """{line number: (word, key)} for a document given as one string."""
    hits, _ = cca.scan_file(text.split("\n"))
    return {h.line: (h.word, h.key) for h in hits}


# -- findings ----------------------------------------------------------------

@pytest.mark.parametrize("text, word, key", [
    # The case that prompted the rule (gha#2144).
    ("The figure follows the layout of a figure in James et al. "
     "[@james2021islr, Figure 6.7].", "James", "james2021islr"),
    ("James, Witten, Hastie and Tibshirani [@james2021islr] give it.",
     "James", "james2021islr"),
    ("Hastie and Tibshirani [@hastie1990additive] define it.",
     "Hastie", "hastie1990additive"),
    ("As shown by James et al. (@james2021islr).", "James", "james2021islr"),
    ("[James et al., @james2021islr]", "James", "james2021islr"),
    ("The idea follows James [see @james2021islr, p. 3].", "James", "james2021islr"),
    ("Starmer explains [ridge regression](https://x.org/v) [@starmer2018ridge].",
     "Starmer", "starmer2018ridge"),
    ("Imputation follows van Buuren [@vanbuuren2018].", "van Buuren", "vanbuuren2018"),
    ("Imputation follows Van Buuren [@vanbuuren2018].", "Van", "vanbuuren2018"),
    ("Bienaymé derived the bound [@bienayme1853].", "Bienaymé", "bienayme1853"),
    ("Brian Hutchinson's notes [@hutchinson2024data471] cover it.",
     "Hutchinson's", "hutchinson2024data471"),
    ("Abu-Mostafa covers it [@abumostafa2012lfd].", "Abu-Mostafa", "abumostafa2012lfd"),
    ("O'Brien showed it [@obrien1990].", "O'Brien", "obrien1990"),
    ("Allen and Cady [@AllenCady1982] use it.", "Allen", "AllenCady1982"),
])
def test_flagged_forms(text, word, key):
    assert found(text) == {1: (word, key)}


def test_a_name_ending_the_previous_line_is_read_with_the_citation():
    assert found("This follows James and\n[@james2021islr].") == {
        2: ("James", "james2021islr")}


def test_a_blank_line_ends_the_carry_over():
    assert found("This follows James.\n\n[@james2021islr] is the book.") == {}


def test_each_citation_on_a_line_is_judged_on_the_words_before_it():
    text = "Hastie [@hastie2009esl] and later Witten [@witten2011]."
    hits, _ = cca.scan_file([text])
    assert [(h.word, h.key) for h in hits] == [
        ("Hastie", "hastie2009esl"), ("Witten", "witten2011")]


# -- not flagged -------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "The figure follows the layout of @james2021islr [Figure 6.7].",
    "James et al. [-@james2021islr] show this.",
    "See @fig-james and Fig. @fig-x.",
    "Hastie showed this. Later work [@hastie2017] extends it.",
    "Mail james@james2021islr.org.",  # phi-allow
    "[Cook's distance](#def-cooks) [@cook1977detection] combines them.",
    "The **Cox proportional hazards** model [@cox1972regression] is used.",
    "- *Practical R for Epidemiologists* (@practicalr4epi)",
    "The Gaussian kernel [@gauss1809] is smooth.",
    "R [@r2024] runs it.",
    "A smoothing spline [@wahba1990] is fit.",
    "The book by Hastie, Tibshirani and Friedman is long. See @james2021islr.",
    "Witten [@james2021islr] is a coauthor.",
])
def test_unflagged_forms(text):
    assert found(text) == {}


def test_far_name_is_outside_the_window():
    text = "James wrote one of many accessible books on the topic [@james2021islr]."
    assert found(text) == {}


def test_code_fence_is_skipped():
    assert found("```\nJames [@james2021islr]\n```") == {}


def test_code_span_is_skipped():
    assert found("Type `James [@james2021islr]` here.") == {}


def test_html_comment_is_skipped():
    assert found("<!-- James [@james2021islr] -->") == {}


def test_front_matter_is_skipped():
    assert found("---\ntitle: James [@james2021islr]\n---\nbody") == {}


def test_allow_comment_with_a_reason_on_the_line_or_the_line_before():
    allow = "<!-- check-citation-authors: allow: names one author on purpose -->"
    assert found(f"James [@james2021islr] {allow}") == {}
    assert found(f"{allow}\nJames [@james2021islr]") == {}


def test_allow_comment_without_a_reason_does_not_exempt():
    assert found("James [@james2021islr] <!-- check-citation-authors: allow -->") == {
        1: ("James", "james2021islr")}
    assert found("James [@james2021islr] <!-- check-citation-authors: allow: -->") == {
        1: ("James", "james2021islr")}


def test_message_names_the_fix_and_the_source():
    message = cca.format_message(cca.Finding(1, "James", "james2021islr"))
    assert '"James"' in message
    assert "@james2021islr [Figure 6.7]" in message
    assert "[-@james2021islr]" in message
    assert "gha#2144" in message


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
    for key in ("CCA_BASE_REF", "CCA_GLOBS", "CCA_PATHS_IGNORE", "CCA_FAIL",
                "CCA_WHOLE_TREE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CCA_BASE_REF", "HEAD")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_main_warns_by_default_and_fails_when_fail_is_on(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("prose\nJames et al. [@james2021islr] show it.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo)
    assert cca.main() == 0
    assert "::warning file=page.qmd,line=2::" in capsys.readouterr().out
    monkeypatch.setenv("CCA_FAIL", "true")
    assert cca.main() == 1
    assert "::error file=page.qmd,line=2::" in capsys.readouterr().out


def test_main_reports_only_added_lines(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("James [@james2021islr] show it.\n")
    git("add", "-A")
    git("commit", "-q", "-m", "old prose")
    (repo / "page.qmd").write_text(
        "James [@james2021islr] show it.\nThe layout follows @james2021islr [Figure 6.7].\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CCA_FAIL="true")
    assert cca.main() == 0
    assert "No author name typed next to a citation" in capsys.readouterr().out


def test_main_without_base_skips_under_its_own_name(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("James [@james2021islr]\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CCA_FAIL="true", CCA_BASE_REF="")
    assert cca.main() == 0
    assert capsys.readouterr().out.startswith("Skipping the citation-authors check")


def test_write_idiom_prefix_is_not_read(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("James [@james2021islr]\n")
    git("add", "-A")
    _main_env(monkeypatch, repo)
    monkeypatch.setenv("CWI_FAIL", "true")
    assert cca.main() == 0


# -- the action, the workflow and the script agree ---------------------------

def test_defaults_agree_across_action_workflow_and_script():
    workflows = _DIR.parent / ".github/workflows"
    if (workflows / ".restored-from-default-branch").is_file():
        # The review job restores the default branch's workflows (gha#765),
        # which may not hold this one yet.
        pytest.skip("workflows restored from the default branch")
    action = (_DIR / "action.yml").read_text()
    workflow = (workflows / "check-citation-authors.yml").read_text()
    for text in (action, workflow):
        assert f"default: '{cca.DEFAULT_GLOBS}'" in text
    assert cca._DEFAULT_FAIL is False
    assert re.search(r"fail:\n(?:.*\n)*?\s+default: 'false'", action)
    assert re.search(r"fail:\n(?:.*\n)*?\s+default: false", workflow)


def test_action_passes_every_input_to_the_script_under_the_cca_prefix():
    action = (_DIR / "action.yml").read_text()
    for var in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"CCA_{var}:" in action
