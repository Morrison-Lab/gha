import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import annotation_gate as g  # noqa: E402

DEFAULT = [
    r"The ubuntu-latest label will migrate to",
    r"Node\.js \d+ is deprecated\. The following actions target Node",
    r"^Canceling since a higher priority waiting request for",
    r"^The operation was canceled\.$",
    r"not posting a stale review",
    r"^PR edits workflow files; restored",
    r"^Claude review verdict is not clean \(verdict: .+\)\.$",
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


def test_superseded_job_cancellation_is_allowed():
    assert not g.find_violations([ann("failure", "The operation was canceled.")], set(g.LEVELS_ALL), DEFAULT)


def test_non_clean_review_verdict_is_allowed():
    for verdict in ("needs-more-work", "not-ready", "unknown"):
        msg = f"Claude review verdict is not clean (verdict: {verdict})."
        assert not g.find_violations([ann("failure", msg)], set(g.LEVELS_ALL), DEFAULT)


def test_non_clean_review_verdict_pattern_is_anchored():
    for msg in (
        "Error: Claude review verdict is not clean (verdict: needs-more-work).",
        "Claude review verdict is not clean (verdict: needs-more-work). Extra text",
    ):
        assert g.find_violations([ann("failure", msg)], set(g.LEVELS_ALL), DEFAULT)


def run(wid, event, number, status="completed", name=None, rid=None):
    return {
        "id": rid or number,
        "workflow_id": wid,
        "event": event,
        "run_number": number,
        "run_attempt": 1,
        "status": status,
        "name": name or f"wf{wid}",
    }


def test_latest_runs_keeps_the_newest_completed_run_per_workflow_and_event():
    runs = [run(1, "push", 4), run(1, "push", 5), run(1, "pull_request", 2), run(2, "push", 1)]
    picked = g.latest_runs(runs, "Annotation gate")
    assert sorted((r["workflow_id"], r["event"], r["run_number"]) for r in picked) == [
        (1, "pull_request", 2),
        (1, "push", 5),
        (2, "push", 1),
    ]


def test_latest_runs_leaves_out_unfinished_runs_and_the_callers_own_workflow():
    runs = [run(1, "push", 3, status="in_progress"), run(2, "push", 1, name="Annotation gate"), run(3, "push", 1)]
    assert [r["workflow_id"] for r in g.latest_runs(runs, "Annotation gate")] == [3]


def test_a_newer_unfinished_run_does_not_hide_an_older_finished_one():
    runs = [run(1, "push", 4), run(1, "push", 5, status="in_progress")]
    assert [r["run_number"] for r in g.latest_runs(runs, "")] == [4]


def commit_mode(monkeypatch, runs, jobs_by_run, annotations_by_job, counts):
    posted, fetched = [], []
    for key in ("GATE_RUN_ID", "GATE_RUN_ATTEMPT", "GITHUB_JOB", "GATE_ALLOW", "GATE_DEFAULT_ALLOW"):
        monkeypatch.delenv(key, raising=False)
    env = {
        "GITHUB_TOKEN": "t",
        "GITHUB_REPOSITORY": "o/r",
        "GITHUB_RUN_ID": "1",
        "GITHUB_WORKFLOW": "Annotation gate",
        "GATE_ALL_RUNS": "true",
        "GATE_HEAD_SHA": "abc",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    def fake_paged(url, token, key=None):
        if key == "workflow_runs":
            return iter(runs)
        if key == "check_runs":
            return iter([{"id": job, "output": {"annotations_count": n}} for job, n in counts.items()])
        if key == "jobs":
            run_id = int(url.split("/runs/")[1].split("/")[0])
            return iter(jobs_by_run[run_id])
        job = int(url.split("/check-runs/")[1].split("/")[0])
        fetched.append(job)
        return iter(annotations_by_job[job])

    monkeypatch.setattr(g, "paged", fake_paged)
    monkeypatch.setattr(g, "post_check_run", lambda *args: posted.append(args))
    return g.main(), posted, fetched


def test_commit_mode_gates_every_workflow_and_posts_one_check_run(monkeypatch):
    runs = [run(1, "push", 1, rid=10), run(2, "push", 1, rid=20)]
    jobs = {10: [{"id": 100, "name": "a"}], 20: [{"id": 200, "name": "b"}]}
    bad = {"annotation_level": "warning", "message": "odd"}
    code, posted, fetched = commit_mode(monkeypatch, runs, jobs, {100: [], 200: [bad]}, {100: 0, 200: 1})
    assert code == 1
    assert len(posted) == 1 and posted[0][3] == "abc" and posted[0][4] is False
    assert fetched == [200]


def test_commit_mode_clean_commit_posts_success_and_skips_zero_annotation_jobs(monkeypatch):
    runs = [run(1, "push", 1, rid=10)]
    code, posted, fetched = commit_mode(monkeypatch, runs, {10: [{"id": 100, "name": "a"}]}, {}, {100: 0})
    assert code == 0 and posted[0][4] is True and fetched == []


def test_commit_mode_fetches_a_job_the_commit_listing_does_not_cover(monkeypatch):
    runs = [run(1, "push", 1, rid=10)]
    ann_ok = {"annotation_level": "notice", "message": "x"}
    code, posted, fetched = commit_mode(monkeypatch, runs, {10: [{"id": 100, "name": "a"}]}, {100: [ann_ok]}, {})
    assert code == 1 and fetched == [100]
