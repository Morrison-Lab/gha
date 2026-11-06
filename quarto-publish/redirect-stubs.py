#!/usr/bin/env python3
"""
Write a Quarto profile that leaves redirect stubs out of a non-html render.

A page whose front matter sets ``redirect-stub: true`` is an html-only
redirect. ``quarto render --to FORMAT`` renders every page in the project, so a
per-format publish would still build the stub's slides, PDF and Word file.

Usage: ``redirect-stubs.py PROJECT_PATH PROFILE_NAME``

Writes ``PROJECT_PATH/_quarto-PROFILE_NAME.yml`` with ``project.render``
entries ``!<stub path>``, one per stub. Quarto appends them to the render list
of the other active profiles. A project with no ``project.render`` list renders every page, but a list that
holds only exclusions renders nothing, so then the file also lists the pages
Quarto renders by default. ``ACTIVE_PROFILES`` is the comma-joined profile
list the render uses. Prints the number of stubs, and writes no file
when there are none.
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


def has_render_list(project, active):
    """True when the project config, under ``active`` profiles, lists pages."""
    cmd = ["quarto", "inspect", project]
    if active:
        cmd += ["--profile", active]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    config = json.loads(out).get("config", {})
    return bool((config.get("project") or {}).get("render"))


def main(argv):
    project, profile = argv[1], argv[2]
    active = argv[3] if len(argv) > 3 else ""
    stubs = find_stubs(project)
    if stubs:
        out = os.path.join(project, "_quarto-%s.yml" % profile)
        with open(out, "w", encoding="utf-8") as handle:
            handle.write("project:\n  render:\n")
            if not has_render_list(project, active):
                for ext in ("qmd", "md", "ipynb", "Rmd"):
                    handle.write('    - "**/*.%s"\n' % ext)
            for stub in stubs:
                handle.write('    - "!%s"\n' % stub)
    print(len(stubs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
