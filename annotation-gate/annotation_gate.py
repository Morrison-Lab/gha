#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Fail a workflow run that carries an annotation nobody allowed.

Reads every other job's annotations in the current run through the REST API.
A `notice`, `warning` or `failure` annotation fails the gate unless its
message matches an allow pattern. Environment:

  GITHUB_TOKEN        token with `actions: read` and `checks: read`
  GITHUB_REPOSITORY   owner/repo
  GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT
  GATE_RUN_ID, GATE_RUN_ATTEMPT
                      gate another run (the `workflow_run` mode); then no job is
                      skipped as the gate's own, and the result is also posted
                      as a check run named `annotation-gate` on GATE_HEAD_SHA
                      (needs `checks: write`)
  GATE_ALL_RUNS       "true", with GATE_HEAD_SHA: gate the latest completed run of
                      every workflow and event on that commit in one pass,
                      skipping the caller's own workflow (GITHUB_WORKFLOW), and
                      post one check run. One commit-wide check-run listing
                      gives each job's annotation count, so a job with none
                      costs no request.
  GITHUB_API_URL      defaults to https://api.github.com
  GITHUB_JOB          the gate's own job id; it and `<caller> / <id>` are skipped
  GATE_JOB_NAME       optional extra name prefix to skip
  GATE_LEVELS         comma list of levels to enforce
  GATE_ALLOW          newline list of regexes; a message matching one is allowed
  GATE_DEFAULT_ALLOW  newline list of regexes allowed for every caller
"""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

LEVELS_ALL = ("notice", "warning", "failure")


def split_lines(text):
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def parse_levels(text):
    levels = [x.strip().lower() for x in (text or "").split(",") if x.strip()]
    bad = [x for x in levels if x not in LEVELS_ALL]
    if bad or not levels:
        raise ValueError(f"levels must be a comma list from {LEVELS_ALL}, got {text!r}")
    return set(levels)


def is_gate_job(name, own_job, prefix):
    """True for the job running this script.

    A job called through a reusable workflow is named `<caller job> / <callee
    job>`, and the callee job id is GITHUB_JOB, so the gate is found whatever
    the caller named it. `prefix` is an extra, optional name prefix.
    """
    if own_job and (name == own_job or name.endswith(f" / {own_job}")):
        return True
    return bool(prefix) and name.startswith(prefix)


def find_violations(annotations, levels, allow_patterns):
    """annotations: list of (job_name, annotation dict). Returns those not allowed."""
    compiled = [re.compile(p, re.IGNORECASE) for p in allow_patterns]
    out = []
    for job, ann in annotations:
        if ann.get("annotation_level") not in levels:
            continue
        message = ann.get("message") or ""
        if any(rx.search(message) for rx in compiled):
            continue
        out.append((job, ann))
    return out


def api(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def post_check_run(base, repo, token, sha, ok, summary):
    body = json.dumps({
        "name": "annotation-gate",
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success" if ok else "failure",
        "output": {"title": "Annotation gate", "summary": summary[:60000]},
    }).encode()
    req = urllib.request.Request(f"{base}/repos/{repo}/check-runs", data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def paged(url, token, key=None):
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        data = api(f"{url}{sep}per_page=100&page={page}", token)
        items = data[key] if key else data
        yield from items
        if len(items) < 100:
            return
        page += 1


def latest_runs(runs, own_workflow):
    """The newest completed run of each (workflow, event), skipping own_workflow.

    A run still queued or in progress is left out: its completion fires its own
    gate, which re-evaluates the whole commit.
    """
    newest = {}
    for run in runs:
        if run.get("status") != "completed" or run.get("name") == own_workflow:
            continue
        key = (run["workflow_id"], run["event"])
        if key not in newest or run["run_number"] > newest[key]["run_number"]:
            newest[key] = run
    return sorted(newest.values(), key=lambda run: run["id"])


def gate_targets(runs, own_workflow, trigger_id="", trigger_attempt=""):
    """(run id, attempt) of the latest completed run of each workflow and event.

    The run that triggered this gate is gated at no earlier attempt than the one
    the event reports. The runs listing can lag a re-run by seconds and still
    show the previous attempt, whose job annotations (a timeout, a cancellation)
    describe an attempt the event's own attempt superseded.
    """
    targets = []
    for r in latest_runs(runs, own_workflow):
        attempt = r["run_attempt"]
        if trigger_id and str(r["id"]) == str(trigger_id) and str(trigger_attempt).isdigit():
            attempt = max(attempt, int(trigger_attempt))
        targets.append((r["id"], attempt))
    return targets


def current_attempts(base, repo, token, targets):
    """Targets raised to the attempt each run reports now.

    The runs listing can show an earlier attempt for a run that a re-run has
    finished since, so a gate triggered by another workflow read the superseded
    attempt's annotations (gha#1742). One read per run settles it.
    """
    out = []
    for run_id, attempt in targets:
        latest = api(f"{base}/repos/{repo}/actions/runs/{run_id}", token).get("run_attempt")
        out.append((run_id, max(attempt, latest) if isinstance(latest, int) else attempt))
    return out


def unfinished_runs(runs, own_workflow):
    """Runs other than own_workflow still queued or in progress."""
    return [r for r in runs if r.get("name") != own_workflow and r.get("status") in ("queued", "in_progress")]


def waiting_lines(waiting, now=None):
    """One line per unfinished run: name, status, minutes since creation, link (gha#2151)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    lines = []
    for r in waiting:
        age = ""
        created = r.get("created_at")
        if created:
            start = datetime.datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
            age = f" for {int((now - start).total_seconds() // 60)} min"
        link = f" ({r['html_url']})" if r.get("html_url") else ""
        lines.append(f"{r.get('name', '?')}: {r.get('status')}{age}{link}")
    return lines


def command_data(text):
    """Escape `text` for the data part of a workflow command, as GitHub's toolkit does.

    A run name or URL holding `%`, CR or LF would otherwise end the command
    early or start a new one.
    """
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report_deferral(head_sha, waiting, now=None):
    """Report a deferred gate: count the waiting runs in the log, and name them in a notice and the job summary.

    A deferred gate posts no check run, so without this a held-back gate reads
    as one that never started (gha#2151).
    """
    lines = waiting_lines(waiting, now)
    print(f"annotation-gate: deferred, {len(waiting)} run(s) on {head_sha[:7]} still queued or in progress; the last to finish gates the commit.")
    print(f"::notice title=Annotation gate deferred::{head_sha[:7]} waits on: " + command_data("; ".join(lines)))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"### Annotation gate deferred on {head_sha[:7]}\n\n")
            fh.write("The last of these runs to finish will gate the commit:\n\n")
            fh.writelines(f"- {line}\n" for line in lines)


JOB_URL_RE = re.compile(r"/actions/runs/(\d+)/job/(\d+)")


def annotation_counts(base, repo, token, sha):
    """Check runs on the commit: (id -> annotation count, (run id, name) -> newest id).

    The second map names the newest check run of each job of each workflow run.
    A job of an earlier attempt has a lower id than its re-run, so it is
    superseded and its annotations describe an attempt that no longer counts
    (gha#1722).
    """
    url = f"{base}/repos/{repo}/commits/{sha}/check-runs?filter=latest"
    counts, newest = {}, {}
    for c in paged(url, token, "check_runs"):
        counts[c["id"]] = (c.get("output") or {}).get("annotations_count", 1)
        m = JOB_URL_RE.search(c.get("details_url") or "")
        if m and c.get("name"):
            key = (int(m.group(1)), c["name"])
            newest[key] = max(newest.get(key, 0), c["id"])
    return counts, newest


def gate_jobs(base, repo, token, run_id, attempt, own_job, gate, counts, newest=None):
    """Annotations of every job in one run attempt: (annotations, jobs checked)."""
    annotations, checked = [], 0
    jobs_url = f"{base}/repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs"
    for job in paged(jobs_url, token, "jobs"):
        if is_gate_job(job["name"], own_job, gate):
            continue
        if newest and newest.get((int(run_id), job["name"]), job["id"]) > job["id"]:
            continue
        checked += 1
        if counts.get(job["id"], 1) == 0:
            continue
        url = f"{base}/repos/{repo}/check-runs/{job['id']}/annotations"
        for ann in paged(url, token):
            annotations.append((job["name"], ann))
    return annotations, checked


BACKFILL_HOURS = 24


def recent_pr_heads(base, repo, token, now=None):
    """Commits that a pull request run touched in the last BACKFILL_HOURS hours.

    Read from the runs listing, not the pulls listing: a pull request read
    needs `pull-requests: read`, and widening a reusable workflow's permissions
    breaks every caller that grants less. A closed pull request's head is
    included, and gating it is harmless.
    """
    since = (now or datetime.datetime.now(datetime.timezone.utc)) - datetime.timedelta(hours=BACKFILL_HOURS)
    url = f"{base}/repos/{repo}/actions/runs?event=pull_request&created=>={since:%Y-%m-%dT%H:%M:%SZ}"
    return list(dict.fromkeys(run["head_sha"] for run in paged(url, token, "workflow_runs")))


def gate_posted_at(base, repo, token, sha):
    """When the newest `annotation-gate` check run on the commit finished, or "" for none."""
    data = api(f"{base}/repos/{repo}/commits/{sha}/check-runs?check_name=annotation-gate&per_page=100", token)
    return max((c.get("completed_at") or "" for c in data.get("check_runs", [])), default="")


def gate_is_stale(base, repo, token, sha, own_workflow):
    """True when the commit has no check run, or a run finished after the newest one.

    A deferred gate posts nothing and relies on the last finishing run to start
    the gate that posts. When that event never arrives, the commit keeps the
    check it had before: none (gha#1754), so GitHub blocks the merge with
    nothing to re-run, or an earlier failure that a re-run has since fixed
    (gha#1752).
    """
    posted = gate_posted_at(base, repo, token, sha)
    if not posted:
        return True
    runs = paged(f"{base}/repos/{repo}/actions/runs?head_sha={sha}", token, "workflow_runs")
    return any(r.get("status") == "completed" and r.get("name") != own_workflow and (r.get("updated_at") or "") > posted for r in runs)


def stale_heads(base, repo, token, own_workflow):
    """Recent pull request commits whose `annotation-gate` check is missing or out of date."""
    return [sha for sha in recent_pr_heads(base, repo, token) if gate_is_stale(base, repo, token, sha, own_workflow)]


def report(settings, head_sha, targets, annotations, checked, post):
    """Print the result, post the check run when asked, and return the exit code."""
    bad = find_violations(annotations, settings["levels"], settings["allow"])
    print(f"annotation-gate: {len(targets)} run(s), {checked} job(s), {len(annotations)} annotation(s), {len(bad)} not allowed.")
    lines = []
    for job, ann in bad:
        message = (ann.get("message") or "").replace(chr(10), " ")[:300]
        print(f"::error title=Unallowed {ann['annotation_level']} annotation::[{job}] {message}")
        lines.append(f"- {ann['annotation_level']} in `{job}`: {message}")
    if post and head_sha:
        summary = chr(10).join(lines) or f"{len(annotations)} annotation(s) in {checked} job(s), all allowed."
        post_check_run(settings["base"], settings["repo"], settings["token"], head_sha, not bad, summary)
    if bad:
        print("Fix the cause, or allow a tracked exception with the `allow-patterns` input.")
        return 1
    return 0


def gate_commit(settings, head_sha, trigger_id="", trigger_attempt=""):
    """Gate every workflow's latest run on one commit and post the check run.

    Returns the exit code: 0 clean or deferred, 1 an annotation nobody allowed.
    """
    base, repo, token = settings["base"], settings["repo"], settings["token"]
    runs = list(paged(f"{base}/repos/{repo}/actions/runs?head_sha={head_sha}", token, "workflow_runs"))
    own = settings["workflow"]
    waiting = unfinished_runs(runs, own)
    if settings["defer"] and waiting:
        settings["deferred"] = True
        report_deferral(head_sha, waiting)
        return 0
    targets = gate_targets(runs, own, trigger_id, trigger_attempt)
    targets = current_attempts(base, repo, token, targets)
    counts, newest = annotation_counts(base, repo, token, head_sha)
    annotations, checked = [], 0
    for target_id, target_attempt in targets:
        found, n = gate_jobs(base, repo, token, target_id, target_attempt, "", settings["gate"], counts, newest)
        annotations += found
        checked += n
    return report(settings, head_sha, targets, annotations, checked, True)


def backfill(settings):
    """Gate each recent pull request commit whose `annotation-gate` check is missing or stale."""
    stale = stale_heads(settings["base"], settings["repo"], settings["token"], settings["workflow"])
    print(f"annotation-gate: backfill, {len(stale)} recent pull request commit(s) with no check run or an out-of-date one.")
    codes = [gate_commit(settings, sha) for sha in stale]
    return 1 if any(codes) else 0


def recently_finished_heads(base, repo, token, names, hours, now=None):
    """Commits whose run of a workflow in `names` finished in the last `hours` hours.

    A re-run of such a workflow (a Claude review after its 429, gha#2072) may
    never send the `workflow_run` event that starts a gate, so the commit keeps
    the failure its first attempt posted. Only the runs of these workflows are
    listed, a page or two a day, not every run in the repository.

    A first attempt is skipped: its completion sends a `workflow_run` event of
    its own, so the re-run case above is the one this pass is for. A first
    attempt can still go ungated when that event is lost or its gate dies (an
    API 403, a runner failure); the scheduled backfill covers those, as it did
    before this pass existed. Checking every recently finished head instead
    cost each gate two or more
    API calls per head. On Morrison-Lab/lds, where about 60 gates an hour each
    checked about 70 heads, that used up the repository's hourly
    `GITHUB_TOKEN` quota within 20 minutes of each reset.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    # A re-run keeps its original created_at, so the creation window reaches a
    # day further back than the finish window and grows with it.
    since = (now - datetime.timedelta(hours=hours + 24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = (now - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    heads = {}
    for workflow in paged(f"{base}/repos/{repo}/actions/workflows", token, "workflows"):
        if workflow.get("name") not in names:
            continue
        for run in paged(f"{base}/repos/{repo}/actions/workflows/{workflow['id']}/runs?status=completed&created=>={since}", token, "workflow_runs"):
            if (run.get("run_attempt") or 1) > 1 and (run.get("updated_at") or "") >= recent:
                heads[run["head_sha"]] = True
    return list(heads)


def repair(settings, exclude=""):
    """Gate again each recent commit whose gate predates a finished run of a watched workflow.

    Never fails the gate that called it: a commit's unallowed annotation fails
    that commit's own check run, not this one, and an API error here only
    leaves the commit to the scheduled backfill.
    """
    names = split_lines(os.environ.get("GATE_REPAIR_WORKFLOWS"))
    hours = float(os.environ.get("GATE_REPAIR_HOURS") or 3)
    if not names:
        return 0
    base, repo, token = settings["base"], settings["repo"], settings["token"]
    try:
        heads = [sha for sha in recently_finished_heads(base, repo, token, names, hours) if sha != exclude]
        stale = [sha for sha in heads if gate_is_stale(base, repo, token, sha, settings["workflow"])]
        print(f"annotation-gate: repair, {len(stale)} of {len(heads)} recently finished commit(s) have an out-of-date check.")
        for sha in stale:
            gate_commit({**settings, "defer": True}, sha)
    except (urllib.error.URLError, OSError) as err:
        print(f"annotation-gate: repair skipped: {err}")
    return 0


def main():
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    target_run = os.environ.get("GATE_RUN_ID", "")
    run_id = target_run or os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GATE_RUN_ATTEMPT") or os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    head_sha = os.environ.get("GATE_HEAD_SHA", "")
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    gate = os.environ.get("GATE_JOB_NAME", "")
    all_runs = os.environ.get("GATE_ALL_RUNS") == "true"
    own_job = "" if target_run or all_runs else os.environ.get("GITHUB_JOB", "")
    settings = {
        "base": base,
        "repo": repo,
        "token": token,
        "gate": gate,
        "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
        # A manual dispatch has no later run to gate the commit for it, so it never defers (gha#1762).
        "defer": os.environ.get("GATE_DEFER_WHILE_RUNNING") == "true" and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch",
        "levels": parse_levels(os.environ.get("GATE_LEVELS", ",".join(LEVELS_ALL))),
        "allow": split_lines(os.environ.get("GATE_DEFAULT_ALLOW")) + split_lines(os.environ.get("GATE_ALLOW")),
    }

    if os.environ.get("GATE_BACKFILL") == "true":
        return backfill({**settings, "defer": True})
    if all_runs and not head_sha:
        print("::error::all-runs needs head-sha, the commit to gate.")
        return 2
    if all_runs:
        code = gate_commit(settings, head_sha, target_run, os.environ.get("GATE_RUN_ATTEMPT", ""))
        if not settings.get("deferred"):
            repair(settings, head_sha)
        return code
    annotations, checked = gate_jobs(base, repo, token, run_id, attempt, own_job, gate, {}, {})
    return report(settings, head_sha, [(run_id, attempt)], annotations, checked, bool(target_run and head_sha))


if __name__ == "__main__":
    sys.exit(main())
