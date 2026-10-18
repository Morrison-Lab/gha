#!/usr/bin/env python3
"""Fail a workflow run that carries an annotation nobody allowed.

Reads every other job's annotations in the current run through the REST API.
A `notice`, `warning` or `failure` annotation fails the gate unless its
message matches an allow pattern. Environment:

  GITHUB_TOKEN        token with `actions: read` and `checks: read`
  GITHUB_REPOSITORY   owner/repo
  GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT
  GITHUB_API_URL      defaults to https://api.github.com
  GATE_JOB_NAME       skip the job(s) whose name starts with this (the gate)
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


def main():
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    gate = os.environ.get("GATE_JOB_NAME", "")
    levels = parse_levels(os.environ.get("GATE_LEVELS", ",".join(LEVELS_ALL)))
    allow = split_lines(os.environ.get("GATE_DEFAULT_ALLOW")) + split_lines(os.environ.get("GATE_ALLOW"))

    jobs_url = f"{base}/repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs"
    annotations, checked = [], 0
    for job in paged(jobs_url, token, "jobs"):
        if gate and job["name"].startswith(gate):
            continue
        checked += 1
        url = f"{base}/repos/{repo}/check-runs/{job['id']}/annotations"
        for ann in paged(url, token):
            annotations.append((job["name"], ann))

    bad = find_violations(annotations, levels, allow)
    print(f"annotation-gate: {checked} job(s), {len(annotations)} annotation(s), {len(bad)} not allowed.")
    for job, ann in bad:
        message = (ann.get("message") or "").replace("\n", " ")[:300]
        print(f"::error title=Unallowed {ann['annotation_level']} annotation::[{job}] {message}")
    if bad:
        print("Fix the cause, or allow a tracked exception with the `allow-patterns` input.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
