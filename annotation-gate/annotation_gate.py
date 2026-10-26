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
import json
import os
import re
import sys
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


def annotation_counts(base, repo, token, sha):
    """Map check run id -> annotation count for every check run on the commit."""
    url = f"{base}/repos/{repo}/commits/{sha}/check-runs?filter=latest"
    return {c["id"]: (c.get("output") or {}).get("annotations_count", 1) for c in paged(url, token, "check_runs")}


def gate_jobs(base, repo, token, run_id, attempt, own_job, gate, counts):
    """Annotations of every job in one run attempt: (annotations, jobs checked)."""
    annotations, checked = [], 0
    jobs_url = f"{base}/repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs"
    for job in paged(jobs_url, token, "jobs"):
        if is_gate_job(job["name"], own_job, gate):
            continue
        checked += 1
        if counts.get(job["id"], 1) == 0:
            continue
        url = f"{base}/repos/{repo}/check-runs/{job['id']}/annotations"
        for ann in paged(url, token):
            annotations.append((job["name"], ann))
    return annotations, checked


def main():
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    target_run = os.environ.get("GATE_RUN_ID", "")
    run_id = target_run or os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GATE_RUN_ATTEMPT") or os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    head_sha = os.environ.get("GATE_HEAD_SHA", "")
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    gate = os.environ.get("GATE_JOB_NAME", "")
    own_job = "" if target_run or os.environ.get("GATE_ALL_RUNS") == "true" else os.environ.get("GITHUB_JOB", "")
    levels = parse_levels(os.environ.get("GATE_LEVELS", ",".join(LEVELS_ALL)))
    allow = split_lines(os.environ.get("GATE_DEFAULT_ALLOW")) + split_lines(os.environ.get("GATE_ALLOW"))

    all_runs = os.environ.get("GATE_ALL_RUNS") == "true" and bool(head_sha)
    if all_runs:
        runs = paged(f"{base}/repos/{repo}/actions/runs?head_sha={head_sha}", token, "workflow_runs")
        targets = [(r["id"], r["run_attempt"]) for r in latest_runs(runs, os.environ.get("GITHUB_WORKFLOW", ""))]
        counts = annotation_counts(base, repo, token, head_sha)
    else:
        targets, counts = [(run_id, attempt)], {}
    annotations, checked = [], 0
    for target_id, target_attempt in targets:
        found, n = gate_jobs(base, repo, token, target_id, target_attempt, own_job, gate, counts)
        annotations += found
        checked += n

    bad = find_violations(annotations, levels, allow)
    print(f"annotation-gate: {len(targets)} run(s), {checked} job(s), {len(annotations)} annotation(s), {len(bad)} not allowed.")
    lines = []
    for job, ann in bad:
        message = (ann.get("message") or "").replace("\n", " ")[:300]
        print(f"::error title=Unallowed {ann['annotation_level']} annotation::[{job}] {message}")
        lines.append(f"- {ann['annotation_level']} in `{job}`: {message}")
    if (target_run or all_runs) and head_sha:
        summary = "\n".join(lines) or f"{len(annotations)} annotation(s) in {checked} job(s), all allowed."
        post_check_run(base, repo, token, head_sha, not bad, summary)
    if bad:
        print("Fix the cause, or allow a tracked exception with the `allow-patterns` input.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
