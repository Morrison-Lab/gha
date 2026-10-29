r"""Unit tests for check-avoided-words.

Covers what counts as a finding (position, effort and time-relative words),
what is not ("above the threshold", "just before"), what is skipped (code
fences and spans, comments, front matter), main()'s exit codes under the
CAW_ prefix, and the defaults the action, the reusable workflow and the
script must agree on. The diff model is the shared engine in
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
    "check_avoided_words", _DIR / "check-avoided-words.py"
)
assert _spec is not None and _spec.loader is not None
wi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wi)


def found(text: str):
    """{line number: (rule, phrase)} for a document given as one string."""
    hits, _ = wi.scan_file(text.split("\n"))
    return {h.line: (h.rule, h.phrase.lower()) for h in hits}


# -- findings ----------------------------------------------------------------

@pytest.mark.parametrize("text, rule, phrase", [
    ("The fits behind the table above.", "position", "the table above"),
    ("See the derivation below.", "position", "the derivation below"),
    ("As shown below, the result holds.", "position", "shown below"),
    ("This was derived above.", "position", "derived above"),
    ("It follows from the lemma, above.", "position", ", above."),
    ("This is easy.", "effort", "easy"),
    ("Compute it easily.", "effort", "easily"),
    ("Just add the terms.", "effort", "just"),
    ("The sum is just the mean.", "effort", "just"),
    ("We recently studied Bayes' rule.", "time", "recently"),
    ("It currently holds.", "time", "currently"),
    ("Nowadays this is routine.", "time", "nowadays"),
    ("At present the bound is loose.", "time", "at present"),
    ("The mode is a point in domain A.", "generic", "domain a"),
    ("Let the range B be finite.", "generic", "range b"),
    ("Take some domain and a map.", "generic", "some domain"),
    ("Domain A is finite.", "generic", "domain a"),
    ("Some domain works.", "generic", "some domain"),
    ("Let the sample  space S be finite.", "generic", "sample  space s"),
])
def test_flagged_forms(text, rule, phrase):
    assert found(text) == {1: (rule, phrase)}


@pytest.mark.parametrize("text", [
    "A value above the threshold is large.",
    "The curve falls below zero.",
    "Items above and below the median are counted.",
    "The error just before the end is small.",
    "Just as before, the sum is finite.",
    "We justify the step.",
    "The new observation is held out.",
    "Now we compute the mean.",
    "Uneasy about the bound.",
    "The mode is a point in the range of X.",
    "The range of values is wide.",
    "The domain $A$ is finite.",
    "The domain Alpha is finite.",
])
def test_unflagged_forms(text):
    assert found(text) == {}


def test_each_line_is_found_with_its_number():
    text = "fine\nthe table above\nfine\nThis is easy."
    assert found(text) == {2: ("position", "the table above"),
                           4: ("effort", "easy")}


def test_one_finding_per_rule_per_line():
    hits, _ = wi.scan_file(["It is easy and it is easily done, currently."])
    assert [h.rule for h in hits] == ["effort", "time"]


def test_message_names_the_alternative_and_the_source():
    hits, _ = wi.scan_file(["the table above"])
    message = wi.format_message(hits[0])
    assert "label" in message
    assert "Google style guide" in message
    assert "psw#418" in message


# -- skips -------------------------------------------------------------------

def test_code_fence_is_skipped():
    assert found("```r\n# the table above\n```") == {}


def test_tilde_fence_is_skipped_and_text_after_is_scanned():
    assert found("~~~\nthe table above\n~~~\nthe table above") == {
        4: ("position", "the table above")}


def test_code_span_is_skipped():
    assert found("Use `the table above` literally.") == {}


def test_html_comment_is_skipped():
    assert found("<!-- the table above -->") == {}


def test_multiline_html_comment_is_skipped():
    assert found("<!--\nthe table above\n-->\nplain") == {}


def test_front_matter_is_skipped():
    assert found("---\ntitle: it is easy\n---\nplain") == {}


def test_allow_comment_on_the_line_or_the_line_before():
    allow = "<!-- check-avoided-words: allow -->"
    assert found(f"the table above {allow}") == {}
    assert found(f"{allow}\nthe table above") == {}
    assert found(f"{allow}\n\nthe table above") == {
        3: ("position", "the table above")}


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
    for key in ("CAW_BASE_REF", "CAW_GLOBS", "CAW_PATHS_IGNORE", "CAW_FAIL",
                "CAW_WHOLE_TREE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CAW_BASE_REF", "HEAD")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_main_warns_by_default_and_fails_on_request(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("prose\nSee the table above.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo)
    assert wi.main() == 0
    out = capsys.readouterr().out
    assert "::warning file=page.qmd,line=2::" in out
    assert "(psw#418;" in out
    monkeypatch.setenv("CAW_FAIL", "true")
    assert wi.main() == 1
    assert "::error file=page.qmd,line=2::" in capsys.readouterr().out


def test_main_passes_comparisons_and_temporal_just(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text(
        "A value above the threshold.\nJust before the end.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CAW_FAIL="true")
    assert wi.main() == 0
    assert "No position, effort, time-relative or generic" in capsys.readouterr().out


def test_main_without_base_skips_under_its_own_name(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("See the table above.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo, CAW_FAIL="true", CAW_BASE_REF="")
    assert wi.main() == 0
    assert capsys.readouterr().out.startswith("Skipping the avoided-words check")


def test_write_idiom_prefix_is_not_read(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text("See the table above.\n")
    git("add", "-A")
    _main_env(monkeypatch, repo)
    monkeypatch.setenv("CWI_FAIL", "true")
    assert wi.main() == 0


# -- the action, the workflow and the script agree ---------------------------

def test_defaults_agree_across_action_workflow_and_script():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-avoided-words.yml").read_text()
    for text in (action, workflow):
        assert f"default: '{wi.DEFAULT_GLOBS}'" in text
    assert wi._DEFAULT_FAIL is False
    assert "default: 'false'" in action
    assert re.search(r"fail:\n(?:.*\n)*?\s+default: false", workflow)


def test_action_passes_every_input_to_the_script_under_the_caw_prefix():
    action = (_DIR / "action.yml").read_text()
    for var in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"CAW_{var}:" in action
