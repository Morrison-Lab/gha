#!/usr/bin/env python3
"""Fail a major-tag slide unless every test and check run on the commit is done and green.

`slide-major-tag.yml` tags `$GITHUB_SHA`, and the standing tag-slide policy in
CLAUDE.md sets the readiness bar: every check run on that exact commit is
green or skipped, none pending.
Two kinds of run are exempt:

- Dependabot updater runs, named `Dependabot`.
  They are not tests of the commit and can stay in progress for a long time
  (coordinator, 2026-10-28).
- The slide job itself, which is in progress by definition.

The check fails closed: a listing shorter than the API's `total_count`,
or one with no runs at all, is an error, not a clean bill.

Usage::

    GITHUB_TOKEN=... audit_slide_readiness.py --repo OWNER/REPO --sha SHA \\
        [--exempt NAME ...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections.abc import Callable

DEFAULT_EXEMPT = ("Dependabot",)
PASSING = ("success", "skipped", "neutral")
PAGE_SIZE = 100


def blocking_runs(check_runs: list[dict], exempt: set[str]) -> list[dict]:
    """Return the check runs that are unfinished or not green, minus the exempt names."""
    return [
        run
        for run in check_runs
        if run["name"] not in exempt
        and (run["status"] != "completed" or run.get("conclusion") not in PASSING)
    ]


def fetch_page(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def list_check_runs(
    repo: str, sha: str, fetch: Callable[[str], dict]
) -> tuple[list[dict], int]:
    """Page through the commit's check runs; return them with the API's total_count."""
    base = f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs"
    runs: list[dict] = []
    page = 1
    while True:
        data = fetch(f"{base}?per_page={PAGE_SIZE}&page={page}")
        runs.extend(data["check_runs"])
        total = data["total_count"]
        if len(runs) >= total or not data["check_runs"]:
            return runs, total
        page += 1


def audit(
    repo: str, sha: str, exempt: set[str], fetch: Callable[[str], dict]
) -> int:
    runs, total = list_check_runs(repo, sha, fetch)
    if total == 0 or len(runs) < total:
        print(
            f"::error::Read {len(runs)} of {total} check runs on {sha}; "
            "cannot judge readiness."
        )
        return 2
    blockers = blocking_runs(runs, exempt)
    for run in blockers:
        state = run.get("conclusion") or run["status"]
        print(f"::error::{run['name']} on {sha} is {state}.")
    if blockers:
        print(
            f"{len(blockers)} of {len(runs)} check runs block the slide. "
            "Wait for them or fix them, then dispatch again."
        )
        return 1
    print(
        f"Examined {len(runs)} check runs on {sha}; "
        f"all green or skipped (exempt: {', '.join(sorted(exempt)) or 'none'})."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument(
        "--exempt",
        action="append",
        default=[],
        help="check run name to ignore; Dependabot is always ignored",
    )
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("::error::GITHUB_TOKEN is not set.")
        return 2
    exempt = set(DEFAULT_EXEMPT) | set(args.exempt)
    return audit(args.repo, args.sha, exempt, lambda url: fetch_page(url, token))


if __name__ == "__main__":
    sys.exit(main())
