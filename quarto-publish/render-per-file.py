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
"""
import fnmatch
import json
import os
import pathlib
import subprocess
import sys

import yaml


def inspect(project, target):
    """Return `quarto inspect TARGET` as a dict, or None (with its stderr) on failure."""
    result = subprocess.run(
        ["quarto", "inspect", target], cwd=project,
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"::warning::quarto inspect {target} failed "
              f"(exit {result.returncode}); falling back to the project files.\n"
              f"{result.stderr.strip()}", flush=True)
        return None
    return json.loads(result.stdout)


def load_yaml(path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def merge(base, extra):
    """Merge `extra` into `base` as Quarto does: mappings deeply, lists joined."""
    for key, value in extra.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            merge(base[key], value)
        elif isinstance(base.get(key), list) and isinstance(value, list):
            base[key] = base[key] + value
        else:
            base[key] = value
    return base


def project_config(project):
    config = {}
    profile = os.environ.get("QUARTO_PROFILE", "")
    names = ["_quarto.yml", "_quarto.yaml"]
    names += [f"_quarto-{p}.{ext}" for p in profile.split(",") if p
              for ext in ("yml", "yaml")]
    for name in names:
        path = pathlib.Path(project) / name
        if path.exists():
            merge(config, load_yaml(path))
    return config


def format_names(value):
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set(value)
    if isinstance(value, list):
        names = set()
        for item in value:
            names |= format_names(item)
        return names
    return set()


def project_inputs(project, config):
    """The files the project's `render:` globs select, as Quarto would."""
    root = pathlib.Path(project)
    patterns = (config.get("project") or {}).get("render") or ["*.qmd"]
    include = [p for p in patterns if not p.startswith("!")]
    exclude = [p[1:] for p in patterns if p.startswith("!")]
    found = set()
    for pattern in include:
        for path in root.glob(pattern):
            rel = path.relative_to(root)
            if (path.is_file() and path.suffix == ".qmd"
                    and not any(part.startswith(("_", ".")) for part in rel.parts)):
                found.add(rel.as_posix())

    def excluded(rel):
        for pattern in exclude:
            if pattern.endswith("/"):
                if rel.startswith(pattern):
                    return True
            elif fnmatch.fnmatch(rel, pattern):
                return True
        return False

    return sorted(str(root / rel) for rel in found if not excluded(rel))


def front_matter_formats(path, config):
    """Format names a file declares, else the project's."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    meta = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            try:
                meta = yaml.safe_load(text[3:end]) or {}
            except yaml.YAMLError:
                meta = {}
    declared = format_names(meta.get("format")) if isinstance(meta, dict) else set()
    return declared or format_names(config.get("format"))


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    project, output_dir, wanted = argv[1], argv[2], argv[3:]
    config = project_config(project)
    listing = inspect(project, ".")
    if listing is not None:
        inputs = listing["files"]["input"]
    else:
        inputs = project_inputs(project, config)
    failures = []
    rendered = 0
    for path in sorted(inputs):
        rel = os.path.relpath(path, project)
        info = inspect(project, rel)
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
