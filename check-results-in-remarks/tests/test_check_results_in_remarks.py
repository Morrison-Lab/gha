r"""Unit tests for check-results-in-remarks.

Fixtures: a remark that holds a result (flagged), a remark that holds only
commentary (not flagged), and a remark with the opt-out comment (not flagged);
plus diff scoping, other div kinds, and main()'s exit codes.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_results_in_remarks", _DIR / "check-results-in-remarks.py")
assert _spec is not None and _spec.loader is not None
rr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rr)

RESULT = """\
::: {#rem-log-rarity}
The surprisal equals the log of the rarity, for every outcome:

$$
-\\log p(x) = \\log \\frac{1}{p(x)}
$$
:::
"""

COMMENTARY = """\
::: {#rem-log-rarity}
This is why the logarithm appears in the definition.
Compare the display in @eq-surprisal with the entropy.

$$
-\\log p(x)
$$
:::
"""

OPTED_OUT = RESULT.replace(
    "{#rem-log-rarity}\n",
    "{#rem-log-rarity}\n<!-- check-results-in-remarks: allow -->\n")


def run(text: str, touched=None):
    return rr.check_file("a.qmd", text.split("\n"), touched)


def test_remark_with_a_result_is_flagged():
    findings = run(RESULT)
    assert len(findings) == 1
    assert "#rem-log-rarity" in findings[0].message
    assert findings[0].line == 1


def test_remark_with_only_commentary_is_not_flagged():
    assert run(COMMENTARY) == []


def test_opt_out_comment_exempts_the_remark():
    assert run(OPTED_OUT) == []


def test_claim_without_a_display_is_not_flagged():
    assert run("::: {#rem-a}\nThe bound always holds for every x.\n:::\n") == []


@pytest.mark.parametrize("claim", [
    "equals", "is at least", "is at most", "never exceeds", "exactly when",
    "if and only if", "for all x", "holds", "satisfies",
])
def test_each_claim_word_is_flagged(claim):
    text = f"::: {{#rem-a}}\nThe value {claim} one.\n\n$$\nx = 1\n$$\n:::\n"
    assert len(run(text)) == 1


def test_only_remarks_are_read():
    text = RESULT.replace("#rem-log-rarity", "#thm-log-rarity")
    assert run(text) == []


def test_claim_inside_the_display_does_not_count():
    text = "::: {#rem-a}\nSee the display.\n\n$$\n\\text{for all } x\n$$\n:::\n"
    assert run(text) == []


def test_code_fence_in_a_remark_is_skipped():
    text = ("::: {#rem-a}\nSee the code.\n\n```r\n# it holds\n```\n\n"
            "$$\nx = 1\n$$\n:::\n")
    assert run(text) == []


def test_only_touched_remarks_are_checked():
    assert run(RESULT, touched={99}) == []
    assert len(run(RESULT, touched={3})) == 1


def test_default_is_warn_only():
    assert rr._DEFAULT_FAIL is False


# -- main(): exit codes and annotations ---------------------------------------

def _repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")  # phi-allow
    git("config", "user.name", "t")
    (tmp_path / "README.md").write_text("base\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    return tmp_path, git


def _env(monkeypatch, repo, **extra):
    monkeypatch.chdir(repo)
    for key in ("RIR_BASE_REF", "RIR_GLOBS", "RIR_PATHS_IGNORE", "RIR_FAIL",
                "RIR_WHOLE_TREE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RIR_BASE_REF", "HEAD")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_main_warns_by_default_and_fails_when_asked(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text(RESULT)
    git("add", "-A")
    _env(monkeypatch, repo)
    assert rr.main() == 0
    assert "::warning file=page.qmd,line=1::" in capsys.readouterr().out
    monkeypatch.setenv("RIR_FAIL", "true")
    assert rr.main() == 1
    assert "::error file=page.qmd,line=1::" in capsys.readouterr().out


def test_main_passes_commentary(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text(COMMENTARY)
    git("add", "-A")
    _env(monkeypatch, repo, RIR_FAIL="true")
    assert rr.main() == 0
    assert "No touched remark states a result." in capsys.readouterr().out


def test_main_skips_without_a_base(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text(RESULT)
    git("add", "-A")
    _env(monkeypatch, repo, RIR_FAIL="true", RIR_BASE_REF="")
    assert rr.main() == 0
    assert capsys.readouterr().out.startswith("Skipping the results-in-remarks check")


def test_whole_tree_checks_untouched_remarks(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text(RESULT)
    git("add", "-A")
    git("commit", "-q", "-m", "page")
    _env(monkeypatch, repo, RIR_BASE_REF="HEAD")
    assert rr.main() == 0
    assert "No touched remark" in capsys.readouterr().out
    monkeypatch.setenv("RIR_WHOLE_TREE", "true")
    rr.main()
    assert "::warning file=page.qmd" in capsys.readouterr().out
