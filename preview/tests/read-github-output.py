#!/usr/bin/env python3
"""Read one value out of a `$GITHUB_OUTPUT` file written in the delimiter form.

Shared by the unit tests and the `changed-chapters` selftest job so both read
the outputs the same way the runner does, rather than each carrying its own
parser to drift out of step with the writer.

Usage: read-github-output.py <file> [key]

With a key, prints that value and exits 1 if it is absent. Without one, prints
every `key=value` pair, one per line, for a human reading a job log.
"""

import re
import sys

ASSIGNMENT_RE = re.compile(r"^([A-Za-z0-9_-]+)<<(.+)$")


def parse(text):
    values = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = ASSIGNMENT_RE.match(lines[index])
        if not match:
            raise SystemExit(f"unparsable GITHUB_OUTPUT line: {lines[index]!r}")
        key, delimiter = match.groups()
        index += 1
        collected = []
        while index < len(lines) and lines[index] != delimiter:
            collected.append(lines[index])
            index += 1
        if index >= len(lines):
            raise SystemExit(f"unterminated value for {key!r}")
        index += 1
        values[key] = "\n".join(collected)
    return values


def main(argv):
    if not 2 <= len(argv) <= 3:
        raise SystemExit(__doc__)
    with open(argv[1], encoding="utf-8") as handle:
        values = parse(handle.read())
    if len(argv) == 2:
        for key, value in values.items():
            print(f"{key}={value}")
        return 0
    if argv[2] not in values:
        raise SystemExit(f"no such output: {argv[2]}")
    print(values[argv[2]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
