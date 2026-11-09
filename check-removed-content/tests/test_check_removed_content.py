"""Tests for check-removed-content (gha#1791)."""
import importlib.util
import os
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "check-removed-content.py")
_spec = importlib.util.spec_from_file_location("rco", SCRIPT)
rco = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rco)

SENT = "The estimator is unbiased when the errors have mean zero given the design."


def run(tmp_path, monkeypatch, before, after, body="", extra=None):
    """Commit ``before`` then ``after`` (dict path -> text; None deletes) and run main()."""
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True, text=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")  # phi-allow
    git("config", "user.name", "t")
    for path, text in before.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    for path, text in after.items():
        if text is None:
            (tmp_path / path).unlink()
        else:
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).write_text(text, encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "change")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RCO_BASE_REF", "HEAD~1")
    monkeypatch.setenv("RCO_PR_BODY", body)
    for key, val in (extra or {}).items():
        monkeypatch.setenv(key, val)
    return rco.main()


def test_deleted_sentence_fails(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {"a.qmd": SENT + "\n\nKeep this other sentence here.\n"},
               {"a.qmd": "Keep this other sentence here.\n"}) == 1


def test_moved_sentence_passes(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {"a.qmd": SENT + "\n", "b.qmd": "x\n"},
               {"a.qmd": "", "b.qmd": "x\n\n" + SENT + "\n"}) == 0


def test_reflow_passes(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {"a.qmd": SENT + "\n"},
               {"a.qmd": "The estimator is unbiased\nwhen the errors have mean zero\ngiven the design.\n"}) == 0


def test_light_rewording_passes(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {"a.qmd": SENT + "\n"},
               {"a.qmd": "The estimator is unbiased if the errors have mean zero given the design.\n"}) == 0


def test_body_marker_exempts(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {"a.qmd": SENT + "\n"}, {"a.qmd": "\n"},
               body="removed-content-ok: duplicate of the definition") == 0


def test_added_line_marker_exempts(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {"a.qmd": SENT + "\n"},
               {"a.qmd": "<!-- removed-content-ok: duplicate -->\n"}) == 0


def test_deleted_file_named_in_body_exempt(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {"old.qmd": SENT + "\n"}, {"old.qmd": None},
               body="Replaced old.qmd by the new page") == 0


def test_deleted_file_unnamed_fails(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {"old.qmd": SENT + "\n"}, {"old.qmd": None}) == 1


def test_non_prose_ignored(tmp_path, monkeypatch):
    before = "## A heading with many words in it\n\n```r\nx <- 1 + 2 + 3 + 4 + 5\n```\n\n$$a = b + c + d + e + f$$\n"
    assert run(tmp_path, monkeypatch, {"a.qmd": before}, {"a.qmd": "\n"}) == 0


def test_short_sentence_ignored(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {"a.qmd": "Too short here.\n"}, {"a.qmd": "\n"}) == 0


def test_fail_false_warns(tmp_path, monkeypatch, capsys):
    code = run(tmp_path, monkeypatch, {"a.qmd": SENT + "\n"}, {"a.qmd": "\n"},
               extra={"RCO_FAIL": "false"})
    assert code == 0 and "::warning file=a.qmd,line=1" in capsys.readouterr().out


def test_no_base_ref_skips(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RCO_BASE_REF", raising=False)
    assert rco.main() == 0


def test_normalize_drops_markup_and_math():
    assert rco.normalize("The **mean** $\\mu$ of [a link](http://x.y) is `x`.") == [
        "the", "mean", "of", "a", "link", "is", "x"]
