#!/usr/bin/env python3
"""
Flag `run:` blocks in GitHub Actions workflow/action YAML that are long
enough to warrant extracting into a separate script file, the way this repo's
own R/Python capabilities already do (e.g. check-phi/check-phi.py rather than
an inline check-phi/action.yml script block).

Configuration (all via environment variables, set by the composite action):
  SCRIPT_LENGTH_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  SCRIPT_LENGTH_MAX_LINES     Line-count threshold per `run:` block (default
                              150 -- the lab manual's function-length
                              heuristic, coding-practices/function-length-
                              limits.qmd).
  SCRIPT_LENGTH_FAIL          "true" => exit 1 on findings; "false" (default)
                              => warn only. Defaults to warn-only because the
                              lab manual documents its threshold as "a
                              provisional heuristic trigger ... not a hard
                              constraint".
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List, NamedTuple

import yaml

from _pathspec import compile_ignores, is_ignored, split_list


class Finding(NamedTuple):
    path: str
    line: int
    n_lines: int


def tracked_yaml_files(ignores) -> List[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", "*.yml", "*.yaml"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [f for f in out if not is_ignored(f, ignores)]


def iter_run_blocks(node: yaml.Node):
    """Yield each `run:` key/value pair anywhere in a composed YAML node
    tree, regardless of whether it's a workflow's `jobs.*.steps[].run` or a
    composite action's `runs.steps[].run`."""
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            if (
                isinstance(key_node, yaml.ScalarNode)
                and key_node.value == "run"
                and isinstance(value_node, yaml.ScalarNode)
            ):
                yield key_node, value_node
            yield from iter_run_blocks(value_node)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            yield from iter_run_blocks(item)


def find_long_scripts(path: str, max_lines: int) -> List[Finding]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        documents = list(yaml.compose_all(text))
    except yaml.YAMLError:
        # Not this check's job to catch malformed YAML -- yamllint already
        # does that, with a clearer error format.
        return []

    findings = []
    for doc in documents:
        if doc is None:
            continue
        for key_node, value_node in iter_run_blocks(doc):
            n_lines = value_node.end_mark.line - value_node.start_mark.line
            if n_lines > max_lines:
                findings.append(Finding(path, key_node.start_mark.line + 1, n_lines))
    return findings


def report(findings: List[Finding], max_lines: int) -> None:
    print(
        f"Found {len(findings)} `run:` block(s) longer than {max_lines} lines "
        "-- consider extracting into a separate script file:\n"
    )
    for f in findings:
        print(f"  {f.path}:{f.line}: run block is {f.n_lines} lines")
    print(
        "\nSee check-phi/check-phi.py or check-non-standard-chars/"
        "check-non-standard-chars.py for the extract-to-a-script pattern."
    )


def main() -> int:
    ignores = compile_ignores(split_list(os.environ.get("SCRIPT_LENGTH_PATHS_IGNORE", "")))
    max_lines = int(os.environ.get("SCRIPT_LENGTH_MAX_LINES", "150"))
    fail = os.environ.get("SCRIPT_LENGTH_FAIL", "false").strip().lower() == "true"

    findings = []
    for path in tracked_yaml_files(ignores):
        findings.extend(find_long_scripts(path, max_lines))

    if not findings:
        print(f"No `run:` blocks longer than {max_lines} lines.")
        return 0

    report(findings, max_lines)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
