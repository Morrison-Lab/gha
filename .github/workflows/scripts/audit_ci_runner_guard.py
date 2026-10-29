#!/usr/bin/env python3
"""Fail when a workflow reads vars.CI_RUNNER without the private-repo guard.

A `runs-on` that uses the caller's `CI_RUNNER` variable must also test
`github.event.repository.private`, so a public repository's pull request
(fork code) never reaches a self-hosted runner even if the variable is set
at repository or organization level (gha#1167, gha#1320).

Usage::

    python3 audit_ci_runner_guard.py [--workflows-dir DIR]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import yaml

GUARD = "github.event.repository.private && vars.CI_RUNNER"


def runs_on_values(node):
    """Yield every `runs-on` value (string) anywhere in a parsed workflow."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "runs-on" and isinstance(value, str):
                yield value
            else:
                yield from runs_on_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from runs_on_values(item)


def audit(workflows_dir: pathlib.Path) -> list[str]:
    problems = []
    for path in sorted(workflows_dir.glob("*.yml")):
        doc = yaml.safe_load(path.read_text())
        for value in runs_on_values(doc):
            if "CI_RUNNER" in value and GUARD not in value:
                problems.append(f"{path.name}: runs-on reads CI_RUNNER unguarded: {value}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflows-dir", default=".github/workflows", type=pathlib.Path)
    args = parser.parse_args()
    problems = audit(args.workflows_dir)
    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        return 1
    print("every runs-on that reads CI_RUNNER carries the private-repo guard")
    return 0


if __name__ == "__main__":
    sys.exit(main())
