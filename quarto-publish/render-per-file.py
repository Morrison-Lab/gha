#!/usr/bin/env python3
"""Render chosen Quarto output formats one file at a time.

One `quarto render` process over a large project keeps growing in memory until
Deno hits its heap cap (Morrison-Lab/gha#1170).  Rendering each file in its
own process resets that.  A single-file render inside a project leaves the
other files' outputs and the shared site files alone, unlike a whole-project
`--to FORMAT` pass, which deletes the other formats' outputs unless
`--no-clean` is given.

Usage: render-per-file.py PROJECT_DIR OUTPUT_DIR FORMAT [FORMAT ...]
The Quarto profile, if any, is read from QUARTO_PROFILE.

`quarto inspect` resolves a nested include from the including file's directory,
and `quarto render` resolves it from the top-level file's directory.  A project
that writes nested includes through a self-symlink (`mds -> .`, as mds and pds
do) therefore renders but cannot be inspected (Morrison-Lab/gha#1214).  When
`quarto inspect` fails, the input list comes from the project's `render:`
globs and a file's formats from its front matter and then the project config.
The helpers are in `per_file/`, one function per file.
"""
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from per_file.front_matter_formats import front_matter_formats  # noqa: E402
from per_file.project_config import project_config  # noqa: E402
from per_file.project_inputs import project_inputs  # noqa: E402
from per_file.quarto_inspect import quarto_inspect  # noqa: E402


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    project, output_dir, wanted = argv[1], argv[2], argv[3:]
    config = project_config(project)
    listing = quarto_inspect(project, ".")
    if listing is not None:
        inputs = listing["files"]["input"]
    else:
        inputs = project_inputs(project, config)
    failures = []
    rendered = 0
    for path in sorted(inputs):
        rel = os.path.relpath(path, project)
        info = quarto_inspect(project, rel)
        if info is not None:
            have = set(info.get("formats", {}))
        else:
            have = front_matter_formats(path, config)
        for fmt in wanted:
            if fmt not in have:
                continue
            print(f"::group::quarto render {rel} --to {fmt}", flush=True)
            code = subprocess.run(
                ["quarto", "render", rel, "--to", fmt,
                 "--output-dir", output_dir],
                cwd=project, check=False,
            ).returncode
            print("::endgroup::", flush=True)
            rendered += 1
            if code != 0:
                failures.append(f"{rel} ({fmt})")
    print(f"Rendered {rendered} file/format pairs one file at a time.")
    if rendered == 0:
        print("::error::per-file-formats matched no file; check the format names.")
        return 1
    if failures:
        for item in failures:
            print(f"::error::per-file render failed: {item}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
