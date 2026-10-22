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
"""
import json
import os
import subprocess
import sys


def inspect(target, cwd):
    result = subprocess.run(
        ["quarto", "inspect", target],
        cwd=cwd, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"quarto inspect {target} failed")
    return json.loads(result.stdout)


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    project, output_dir, wanted = argv[1], argv[2], argv[3:]
    inputs = inspect(".", project)["files"]["input"]
    failures = []
    rendered = 0
    for path in sorted(inputs):
        rel = os.path.relpath(path, project)
        have = set(inspect(rel, project).get("formats", {}))
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
