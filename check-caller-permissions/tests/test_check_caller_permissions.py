"""Unit tests for check-caller-permissions.

Covers the motivating case (a caller lacking ``actions: read``, lds#1468),
the passes that must stay passes (a sufficient grant, a wider grant, the
workflow-level block, a narrower-than-required ``none``), the calls reported
as unchecked rather than clean, the non-calls (local refs, other owners), and
that an unreadable callee or caller fails closed.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_caller_permissions", _DIR / "check-caller-permissions.py"
)
assert _spec is not None and _spec.loader is not None
ccp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ccp)

CALLEE = """\
on:
  workflow_call:
jobs:
  cleanup:
    permissions:
      contents: write
      pull-requests: read
      actions: read
    runs-on: ubuntu-latest
    steps: []
"""


def caller(perms: str = "", top: str = "", uses: str = "Morrison-Lab/gha/.github/workflows/c.yml@v3") -> str:
    return f"""\
on: push
{top}jobs:
  cleanup:
{perms}    uses: {uses}
"""


@pytest.fixture
def tree(tmp_path):
    """A gha checkout holding c.yml, and a workflows dir for the caller."""
    gha = tmp_path / "gha" / ".github" / "workflows"
    gha.mkdir(parents=True)
    (gha / "c.yml").write_text(CALLEE)
    wf = tmp_path / "wf"
    wf.mkdir()
    return tmp_path / "gha", wf


def run(tree, text, name="caller.yml"):
    gha, wf = tree
    (wf / name).write_text(text)
    return [kind for p in sorted(wf.iterdir()) for kind, _ in ccp.check_workflow(p, str(gha))]


FULL = "    permissions:\n      contents: write\n      pull-requests: read\n      actions: read\n"


def test_missing_actions_read_is_flagged(tree):
    perms = "    permissions:\n      contents: write\n      pull-requests: read\n"
    assert run(tree, caller(perms)) == ["missing"]


def test_message_names_the_missing_grant(tree):
    gha, wf = tree
    (wf / "caller.yml").write_text(caller("    permissions:\n      contents: write\n      pull-requests: read\n"))
    (_, line), = ccp.check_workflow(wf / "caller.yml", str(gha))
    assert "actions: read" in line and "c.yml@v3" in line


def test_full_grant_passes(tree):
    assert run(tree, caller(FULL)) == ["ok"]


def test_wider_grant_passes(tree):
    perms = FULL.replace("pull-requests: read", "pull-requests: write")
    assert run(tree, caller(perms)) == ["ok"]


def test_read_where_write_is_needed_is_flagged(tree):
    perms = FULL.replace("contents: write", "contents: read")
    assert run(tree, caller(perms)) == ["missing"]


def test_workflow_level_block_is_the_grant(tree):
    top = "permissions:\n  contents: write\n  pull-requests: read\n  actions: read\n"
    assert run(tree, caller(top=top)) == ["ok"]


def test_job_block_overrides_workflow_block(tree):
    top = "permissions:\n  contents: write\n  pull-requests: read\n  actions: read\n"
    assert run(tree, caller("    permissions:\n      contents: read\n", top=top)) == ["missing"]


def test_no_block_anywhere_is_unchecked_not_clean(tree):
    assert run(tree, caller()) == ["unchecked"]


def test_callee_job_without_block_is_unchecked(tree):
    gha, _ = tree
    (gha / ".github" / "workflows" / "c.yml").write_text(CALLEE.replace(
        "    permissions:\n      contents: write\n      pull-requests: read\n      actions: read\n", ""))
    assert run(tree, caller(FULL)) == ["unchecked"]


def test_callee_workflow_level_block_counts(tree):
    gha, _ = tree
    (gha / ".github" / "workflows" / "c.yml").write_text(
        "on:\n  workflow_call:\npermissions:\n  actions: read\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps: []\n")
    assert run(tree, caller("    permissions:\n      contents: read\n")) == ["missing"]


def test_union_across_callee_jobs(tree):
    gha, _ = tree
    (gha / ".github" / "workflows" / "c.yml").write_text(
        "on:\n  workflow_call:\njobs:\n"
        "  a:\n    permissions:\n      actions: read\n    runs-on: x\n    steps: []\n"
        "  b:\n    permissions:\n      contents: write\n    runs-on: x\n    steps: []\n")
    assert run(tree, caller("    permissions:\n      actions: read\n")) == ["missing"]


def test_local_and_foreign_calls_are_not_examined(tree):
    assert run(tree, caller(uses="./.github/workflows/c.yml")) == []
    assert run(tree, caller(uses="someone/else/.github/workflows/c.yml@v3"), "b.yml") == []


def test_job_without_uses_is_not_examined(tree):
    assert run(tree, "on: push\njobs:\n  j:\n    runs-on: x\n    steps: []\n") == []


def test_unparsable_caller_raises(tree):
    gha, wf = tree
    (wf / "caller.yml").write_text("jobs: [unclosed\n")
    with pytest.raises(ccp.Unparsable):
        list(ccp.check_workflow(wf / "caller.yml", str(gha)))


def test_non_reusable_callee_raises(tree):
    gha, wf = tree
    (gha / ".github" / "workflows" / "c.yml").write_text("on: push\njobs:\n  j:\n    runs-on: x\n    steps: []\n")
    with pytest.raises(ccp.Unparsable):
        run(tree, caller(FULL))


def _main(monkeypatch, tree, text, **env):
    gha, wf = tree
    (wf / "caller.yml").write_text(text)
    monkeypatch.setenv("CCP_WORKFLOWS_DIR", str(wf))
    monkeypatch.setenv("CCP_GHA_DIR", str(gha))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return ccp.main()


BAD = caller("    permissions:\n      contents: write\n")


def test_main_blocks_by_default(monkeypatch, tree):
    assert _main(monkeypatch, tree, BAD) == 1


def test_main_warn_only_when_fail_false(monkeypatch, tree):
    assert _main(monkeypatch, tree, BAD, CCP_FAIL="false") == 0


def test_main_passes_a_good_caller(monkeypatch, tree):
    assert _main(monkeypatch, tree, caller(FULL)) == 0


def test_override_warns_and_every_call_names_its_source(monkeypatch, tree, capsys):
    assert _main(monkeypatch, tree, caller(FULL)) == 0
    out = capsys.readouterr().out
    assert "::warning::CCP_GHA_DIR=" in out
    assert "ignoring the pinned ref v3" in out


def test_source_label_names_the_pinned_ref_when_fetching():
    assert ccp.source_label("v3", None) == "v3 on raw.githubusercontent.com"


def test_main_missing_callee_fails_closed(monkeypatch, tree):
    gha, _ = tree
    (gha / ".github" / "workflows" / "c.yml").unlink()
    assert _main(monkeypatch, tree, caller(FULL)) == 2


def test_main_empty_workflows_dir_fails_closed(monkeypatch, tree):
    gha, wf = tree
    monkeypatch.setenv("CCP_WORKFLOWS_DIR", str(wf))
    monkeypatch.setenv("CCP_GHA_DIR", str(gha))
    assert ccp.main() == 2


def test_fail_default_agrees_across_action_and_workflow():
    import re
    action = (_DIR / "action.yml").read_text()
    wf = (_DIR.parent / ".github" / "workflows" / "check-caller-permissions.yml").read_text()
    assert re.search(r"fail:\n    description: >-(?:.|\n)*?default: 'true'", action)
    assert re.search(r"fail:\n(?:.|\n)*?default: true", wf)
    script = (_DIR / "check-caller-permissions.py").read_text()
    assert 'CCP_FAIL", "true"' in script
