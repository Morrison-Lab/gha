import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import annotation_gate as g  # noqa: E402

DEFAULT = [
    r"The ubuntu-latest label will migrate to",
    r"Node\.js \d+ is deprecated\. The following actions target Node",
    r"^Canceling since a higher priority waiting request for",
    r"not posting a stale review",
    r"^PR edits workflow files; restored",
    r"^Skipping element-level diff highlighting: \d+ old / \d+ new candidate elements exceed the \d+-element cap",
]


def ann(level, message):
    return ("job", {"annotation_level": level, "message": message})


def test_unallowed_warning_is_a_violation():
    bad = g.find_violations([ann("warning", "'bias' is a defined term")], set(g.LEVELS_ALL), DEFAULT)
    assert len(bad) == 1


def test_unallowed_notice_is_a_violation():
    assert g.find_violations([ann("notice", "Running dry-run mode")], set(g.LEVELS_ALL), DEFAULT)


def test_runner_migration_notice_is_allowed():
    msg = "The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026."
    assert not g.find_violations([ann("notice", msg)], set(g.LEVELS_ALL), DEFAULT)


def test_node_deprecation_is_allowed():
    msg = "Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced"
    assert not g.find_violations([ann("warning", msg)], set(g.LEVELS_ALL), DEFAULT)


def test_superseded_review_cancellation_is_allowed():
    msg = "Canceling since a higher priority waiting request for claude-review-348 exists"
    assert not g.find_violations([ann("failure", msg)], set(g.LEVELS_ALL), DEFAULT)


def test_stale_review_skip_is_allowed():
    msg = "PR head moved (aaa -> bbb); not posting a stale review."
    assert not g.find_violations([ann("failure", msg)], set(g.LEVELS_ALL), DEFAULT)


def test_workflow_edit_restore_notice_is_allowed():
    msg = (
        "PR edits workflow files; restored .github/workflows/ from the default branch and passing "
        "github_token so the review can run without executing PR-head workflow YAML (gha#598)."
    )
    assert not g.find_violations([ann("notice", msg)], set(g.LEVELS_ALL), DEFAULT)


def test_workflow_edit_restore_pattern_is_anchored_to_the_message_start():
    msg = "Warning: PR edits workflow files; restored something else"
    assert g.find_violations([ann("warning", msg)], set(g.LEVELS_ALL), DEFAULT)


def test_diff_highlight_cap_notice_is_allowed():
    msg = "Skipping element-level diff highlighting: 581 old / 603 new candidate elements exceed the 500-element cap"
    assert not g.find_violations([ann("notice", msg)], set(g.LEVELS_ALL), DEFAULT)


def test_cancellation_pattern_is_anchored_to_the_message_start():
    msg = "Warning: Canceling since a higher priority waiting request for x was ignored"
    assert g.find_violations([ann("warning", msg)], set(g.LEVELS_ALL), DEFAULT)


def test_allow_match_is_case_insensitive_search():
    assert not g.find_violations([ann("warning", "Skipping the X check")], set(g.LEVELS_ALL), ["skipping the"])


def test_level_not_enforced_is_ignored():
    assert not g.find_violations([ann("notice", "anything")], {"warning", "failure"}, [])


def test_failure_level_counts():
    assert g.find_violations([ann("failure", "Process completed with exit code 1.")], set(g.LEVELS_ALL), DEFAULT)


def test_parse_levels_rejects_unknown():
    with pytest.raises(ValueError):
        g.parse_levels("warning,error")


def test_parse_levels_rejects_empty():
    with pytest.raises(ValueError):
        g.parse_levels("")


def test_split_lines_drops_blanks():
    assert g.split_lines("a\n\n  b \n") == ["a", "b"]


def test_gate_job_found_through_reusable_workflow_name():
    assert g.is_gate_job("anything / annotation-gate", "annotation-gate", "")


def test_other_job_is_not_the_gate():
    assert not g.is_gate_job("check / check-term-links", "annotation-gate", "")


def test_prefix_still_skips_extra_job():
    assert g.is_gate_job("deploy / build", "", "deploy")


def test_exit_code_annotation_allowed_by_default():
    default = [r"^Process completed with exit code \d+"]
    assert not g.find_violations([ann("failure", "Process completed with exit code 1.")], set(g.LEVELS_ALL), default)


def run_main(monkeypatch, env, annotations):
    posted = []
    for key in ("GATE_RUN_ID", "GATE_RUN_ATTEMPT", "GATE_HEAD_SHA", "GITHUB_JOB", "GATE_ALLOW", "GATE_DEFAULT_ALLOW"):
        monkeypatch.delenv(key, raising=False)
    for key, value in {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "1", **env}.items():
        monkeypatch.setenv(key, value)

    def fake_paged(url, token, key=None):
        if key == "jobs":
            return iter([{"id": 7, "name": "annotation-gate"}, {"id": 8, "name": "build"}])
        return iter(annotations)

    monkeypatch.setattr(g, "paged", fake_paged)
    monkeypatch.setattr(g, "post_check_run", lambda *args: posted.append(args))
    return g.main(), posted


def test_run_mode_gates_the_named_run_and_posts_a_check_run(monkeypatch):
    code, posted = run_main(
        monkeypatch,
        {"GATE_RUN_ID": "99", "GATE_HEAD_SHA": "abc", "GITHUB_JOB": "annotation-gate"},
        [ann("warning", "something odd")[1]],
    )
    assert code == 1
    assert len(posted) == 1 and posted[0][3] == "abc" and posted[0][4] is False


def test_run_mode_does_not_skip_a_job_named_like_the_gate(monkeypatch, capsys):
    code, posted = run_main(
        monkeypatch,
        {"GATE_RUN_ID": "99", "GATE_HEAD_SHA": "abc", "GITHUB_JOB": "annotation-gate"},
        [ann("warning", "something odd")[1]],
    )
    assert code == 1
    assert "2 job" in capsys.readouterr().out


def test_run_mode_clean_run_posts_success(monkeypatch):
    code, posted = run_main(monkeypatch, {"GATE_RUN_ID": "99", "GATE_HEAD_SHA": "abc"}, [])
    assert code == 0 and posted[0][4] is True


def test_current_run_mode_posts_nothing(monkeypatch):
    code, posted = run_main(monkeypatch, {"GITHUB_JOB": "annotation-gate"}, [])
    assert code == 0 and posted == []
