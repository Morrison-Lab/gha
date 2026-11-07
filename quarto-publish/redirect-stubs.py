#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""
Write a Quarto profile that leaves redirect stubs out of a non-html render.

A page whose front matter sets ``redirect-stub: true`` is an html-only
redirect. ``quarto render --to FORMAT`` renders every page in the project,
so a per-format publish would still build the stub's slides, PDF and Word file.

Usage: ``redirect-stubs.py PROJECT_PATH PROFILE_NAME [ACTIVE_PROFILES]``
(``ACTIVE_PROFILES`` is the render's comma-joined profile list).
Writes ``PROJECT_PATH/_quarto-PROFILE_NAME.yml`` and prints the stub count;
it writes no file and prints ``0`` when there are none, or when ``quarto
inspect`` fails (gha#1214) and the project sets no ``project.render`` list.
When inspect fails and the project does set one, the file holds the
``!<stub path>`` entries.

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
    """Return the JSON of ``quarto inspect`` for the project, or None.

    ``quarto inspect`` fails on a project that writes nested includes through
    a self-symlink, as mds and pds do (gha#1214); that returns None.
    """
    cmd = ["quarto", "inspect", project]
    if active:
        cmd += ["--profile", active]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    print("quarto inspect %s failed (exit %d); reading the project "
          "config instead.\n%s" % (project, result.returncode, result.stderr.strip()),
          file=sys.stderr, flush=True)
    return None


def fallback_config(project, active):
    """The project config under the active profiles, read without Quarto.

    Returns None when PyYAML is missing. QUARTO_PROFILE is set only while
    the config is read.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from per_file.project_config import project_config
    saved = os.environ.get("QUARTO_PROFILE")
    if active:
        os.environ["QUARTO_PROFILE"] = active
    try:
        return project_config(project)
    except ImportError as err:  # load_yaml imports PyYAML when called
        print("::warning::cannot read the project config (%s)." % err,
              file=sys.stderr, flush=True)
        return None
    finally:
        if saved is None:
            os.environ.pop("QUARTO_PROFILE", None)
        else:
            os.environ["QUARTO_PROFILE"] = saved


def render_entries(project, active, stubs):
    """Return the ``project.render`` entries for the skip profile, or None.

    Without ``quarto inspect`` the pages Quarto would render are not known
    (``.md`` and ``.ipynb`` count too), so only the exclusions appended to
    the project's own render list are safe; with no such list, None.
    """
    info = inspect_project(project, active)
    if info is None:
        config = fallback_config(project, active) or {}
        if (config.get("project") or {}).get("render"):
            return ["!%s" % stub for stub in stubs]
        return None
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
        # Exit 0 for a stub: a single-file render ignores the profile's list.
        return 0 if is_stub(argv[2]) else 1
    project, profile = argv[1], argv[2]
    active = argv[3] if len(argv) > 3 else ""
    stubs = find_stubs(project)
    entries = render_entries(project, active, stubs) if stubs else None
    if stubs and entries is None:
        print("::warning::%d redirect stub(s) found, but the pages the project "
              "renders are not known, so every format renders them." % len(stubs),
              file=sys.stderr, flush=True)
        print(0)
        return 0
    if stubs:
        out = os.path.join(project, "_quarto-%s.yml" % profile)
        with open(out, "w", encoding="utf-8") as handle:
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
