"""Unit tests for check-rubric-checklists.

Covers which rubrics are flagged, what is ignored (checklists, code fences,
comments, the allow comment), diff scoping, the skip-not-fall-back guard, and
the defaults the action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_rubric_checklists", _DIR / "check-rubric-checklists.py"
)
assert _spec is not None and _spec.loader is not None
rcl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcl)


def flagged(text: str):
    """Marker line of each rubric that is not a checklist."""
    found, _ = rcl.scan_file(text.split("\n"))
    return [r.start for r in found]


# -- what is flagged ---------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Grading (10 points): (a) 5, one per shape; (b) 5.",
    "**Grading** (10 points): (a) 5.",
    "> Rubric: two points for the shape.",
    "## Grading",
    "Marking scheme:\n\n- 2 points for the shape\n- 3 points for the sum",
    "grading (6 points): one for each part.\n\nThe numbers come from a script.",
])
def test_prose_rubric_is_flagged(text):
    assert flagged(text) == [1]


def test_reports_the_marker_line():
    assert flagged("Answer.\n\nGrading (4 points): all or nothing.") == [3]


# -- what is compliant -------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Grading (6 points):\n\n- [ ] 2 points: gives r.\n- [ ] 4 points: explains.",
    "**Grading (6 points):**\n- [x] 6 points: correct.",
    "Rubric:\n\n- [ ] 3 points: first\n  continued here\n- [ ] 3 points: second",
    "> Grading:\n>\n> - [ ] 1 point: shape",
])
def test_checklist_is_not_flagged(text):
    assert flagged(text) == []


def test_checklist_after_stray_prose_is_not_in_the_block():
    text = "Grading (4 points): see below.\n\nSome other paragraph.\n\n- [ ] 4 points"
    assert flagged(text) == [1]


@pytest.mark.parametrize("text", [
    "```markdown\nGrading (6 points): prose.\n```",
    "<!-- Grading (6 points): prose. -->",
    "<!--\nGrading (6 points): prose.\n-->",
    "<!-- rubric-ok: one holistic judgment -->\nGrading (6 points): prose.",
    "Grading (6 points): prose. <!-- rubric-ok: holistic -->",
    "The grading scale is posted online.",
    "Gradings of the sample were mixed.",
])
def test_ignored(text):
    assert flagged(text) == []


# -- diff scoping ------------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow: synthetic
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "old.qmd").write_text("Grading (3 points): prose.\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(base="HEAD", whole_tree=False):
    return rcl.run_check(base, ["*.qmd"], [], whole_tree)


def test_old_rubric_is_not_reflagged(repo):
    (repo / "new.qmd").write_text("Question.\n")
    _git(repo, "add", ".")
    assert _run().findings == []


def test_added_prose_rubric_is_flagged(repo):
    (repo / "new.qmd").write_text("Grading (3 points): prose.\n")
    _git(repo, "add", ".")
    assert _run().findings == [("new.qmd", 1)]


def test_added_checklist_is_not_flagged(repo):
    (repo / "new.qmd").write_text("Grading (3 points):\n\n- [ ] 3 points: ok\n")
    _git(repo, "add", ".")
    assert _run().findings == []


def test_editing_an_old_rubric_flags_it(repo):
    (repo / "old.qmd").write_text("Grading (4 points): prose.\n")
    _git(repo, "add", ".")
    assert _run().findings == [("old.qmd", 1)]


def test_whole_tree_flags_old_rubric(repo):
    assert _run(whole_tree=True).findings == [("old.qmd", 1)]


def test_no_base_skips(repo):
    assert _run(base="").skipped


# -- defaults agree ----------------------------------------------------------

def _fail_default(path):
    import yaml
    doc = yaml.safe_load(path.read_text())
    inputs = doc["inputs"] if "inputs" in doc else doc[True]["workflow_call"]["inputs"]
    return inputs["fail"]["default"]


def test_default_is_warn_only():
    assert rcl._DEFAULT_FAIL is False
    assert str(_fail_default(_DIR / "action.yml")).lower() == "false"
    workflow = _DIR.parent / ".github/workflows/check-rubric-checklists.yml"
    assert str(_fail_default(workflow)).lower() == "false"


# -- exit codes --------------------------------------------------------------

def _main(monkeypatch, fail):
    monkeypatch.setenv("RCL_BASE_REF", "HEAD")
    monkeypatch.setenv("RCL_GLOBS", "*.qmd")
    if fail is None:
        monkeypatch.delenv("RCL_FAIL", raising=False)
    else:
        monkeypatch.setenv("RCL_FAIL", fail)
    return rcl.main()


def test_warns_with_exit_0_by_default(repo, monkeypatch):
    (repo / "new.qmd").write_text("Grading (3 points): prose.\n")
    _git(repo, "add", ".")
    assert _main(monkeypatch, None) == 0


def test_fails_with_exit_1_when_asked(repo, monkeypatch):
    (repo / "new.qmd").write_text("Grading (3 points): prose.\n")
    _git(repo, "add", ".")
    assert _main(monkeypatch, "true") == 1
