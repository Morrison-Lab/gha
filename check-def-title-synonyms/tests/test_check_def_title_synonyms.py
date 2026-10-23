"""Unit tests for check-def-title-synonyms (the script's name has a hyphen, so load by path)."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_def_title_synonyms", _DIR / "check-def-title-synonyms.py")
assert _spec is not None and _spec.loader is not None
dts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dts)


@pytest.mark.parametrize("title", [
    "Logistic function (also called the sigmoid or expit)",
    "Level set (level curve, contour)",
    "Mean, also known as the average",
    "Norm a.k.a. length",
    "Function, or simply map",
])
def test_bad_titles(title):
    assert dts.bad_title(title)


@pytest.mark.parametrize("title", [
    "Logistic function, sigmoid, expit",
    "Level set, level curve, contour",
    "Almost everywhere ($f = g$ a.e.)",
    "Norm of $(1, 2)$",
    "Postulate, axiom",
])
def test_good_titles(title):
    assert not dts.bad_title(title)


def test_heading_inside_def_div_is_the_title():
    text = ":::{#def-a}\n\n#### Mean (average)\n\nBody (with parentheses).\n:::\n"
    assert dts.def_titles(text.split("\n")) == [(3, "Mean (average)")]


def test_non_def_div_is_ignored():
    assert dts.def_titles([":::{#thm-a}", "#### Thm (a)", ":::"]) == []


def test_title_attribute():
    assert dts.def_titles(['::: {#def-a title="Mean (average)"}', "x", ":::"]) == [
        (1, "Mean (average)")]


def test_added_lines_from_diff():
    diff = "+++ b/a.qmd\n@@ -1,0 +2,2 @@\n+x\n+y\n@@ -9 +11 @@\n+z\n"
    assert dts.added_lines(diff) == {"a.qmd": {2, 3, 11}}


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t",
                    *args], check=True, capture_output=True)


def _run(repo, monkeypatch, capsys, **env):
    monkeypatch.chdir(repo)
    for key in ("DTS_BASE_REF", "DTS_FAIL", "DTS_WHOLE_TREE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    code = dts.main()
    return code, capsys.readouterr().out


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "old.qmd").write_text(":::{#def-o}\n#### Old (legacy)\n:::\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "new.qmd").write_text(
        ":::{#def-n}\n#### New (also called fresh)\n:::\n\n:::{#def-g}\n#### Good, fine\n:::\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "pr")
    return tmp_path


def test_diff_scope_flags_only_added_title(repo, monkeypatch, capsys):
    code, out = _run(repo, monkeypatch, capsys, DTS_BASE_REF="HEAD~1", DTS_FAIL="true")
    assert code == 1
    assert "new.qmd,line=2" in out and "old.qmd" not in out and "Good, fine" not in out


def test_warn_only_by_default(repo, monkeypatch, capsys):
    code, out = _run(repo, monkeypatch, capsys, DTS_BASE_REF="HEAD~1")
    assert code == 0 and "::warning file=new.qmd" in out


def test_whole_tree_flags_existing(repo, monkeypatch, capsys):
    code, out = _run(repo, monkeypatch, capsys, DTS_WHOLE_TREE="true", DTS_FAIL="true")
    assert code == 1 and "old.qmd,line=2" in out


def test_no_base_ref_skips(repo, monkeypatch, capsys):
    code, out = _run(repo, monkeypatch, capsys, DTS_FAIL="true")
    assert code == 0 and "Skipping" in out
