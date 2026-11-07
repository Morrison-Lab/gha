#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""
Write a Quarto profile that leaves redirect stubs out of a non-html render.

A page whose front matter sets ``redirect-stub: true`` is an html-only
redirect. ``quarto render --to FORMAT`` renders every page in the project,
so a per-format publish would still build the stub's slides, PDF and Word file.

Usage: ``redirect-stubs.py PROJECT_PATH PROFILE_NAME [ACTIVE_PROFILES]``

``ACTIVE_PROFILES`` is the comma-joined profile list that the render uses.

Writes ``PROJECT_PATH/_quarto-PROFILE_NAME.yml`` and prints the number of
stubs. It writes no file when there are none.

- When the project, under the active profiles, sets a ``project.render``
  list, the file holds one ``!<stub path>`` entry per stub.
  Quarto appends them to that list.
- When the project sets no such list, the file lists every page that
  ``quarto inspect`` reports as an input, except the stubs.
  A list that holds only exclusions renders nothing, and listing the inputs
  keeps Quarto's own choice of which pages to render.
"""

import json
import os
import re
import subprocess
import sys

STUB = re.compile(r"""^redirect-stub\s*:\s*["']?true["']?\s*(#.*)?$""")
SKIP_DIRS = {".git", ".quarto", "_site", "_freeze", "_extensions", "node_modules"}


def is_stub(path):
    """True when the page's front matter sets ``redirect-stub: true``."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() in ("---", "..."):
            return False
        if STUB.match(line):
            return True
    return False


def find_stubs(project):
    """Return the stub pages under ``project``, as paths relative to it."""
    stubs = []
    for root, dirs, files in os.walk(project):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name.endswith(".qmd") and not name.startswith("_"):
                full = os.path.join(root, name)
                if is_stub(full):
                    stubs.append(os.path.relpath(full, project).replace(os.sep, "/"))
    return stubs


def inspect_project(project, active):
    """Return the JSON of ``quarto inspect`` for the project."""
    cmd = ["quarto", "inspect", project]
    if active:
        cmd += ["--profile", active]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def render_entries(project, active, stubs):
    """Return the ``project.render`` entries for the skip profile."""
    info = inspect_project(project, active)
    if (info.get("config", {}).get("project") or {}).get("render"):
        return ["!%s" % stub for stub in stubs]
    entries = []
    for path in info.get("files", {}).get("input", []):
        rel = os.path.relpath(path, project).replace(os.sep, "/")
        if rel not in stubs:
            entries.append(rel)
    return entries


def main(argv):
    if argv[1] == "--is-stub":
        # Exit 0 when the file is a redirect stub. A single-file render
        # ignores the skip profile's project.render list (gha#1544).
        return 0 if is_stub(argv[2]) else 1
    project, profile = argv[1], argv[2]
    active = argv[3] if len(argv) > 3 else ""
    stubs = find_stubs(project)
    if stubs:
        out = os.path.join(project, "_quarto-%s.yml" % profile)
        with open(out, "w", encoding="utf-8") as handle:
            entries = render_entries(project, active, stubs)
            if entries:
                handle.write("project:\n  render:\n")
                for entry in entries:
                    handle.write('    - "%s"\n' % entry)
            else:
                # A bare `render:` parses as null, not as an empty list.
                handle.write("project:\n  render: []\n")
    print(len(stubs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
