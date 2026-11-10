#!/usr/bin/env python3
"""Offline tests for update-snapshots.yml's "Detect a preinstalled R" step.

Runs the step's own script with a stub `sudo` that always fails and a stub
`Rscript` per case, and reads the step output and GITHUB_ENV (gha#1726).
Also pins that the install step falls back to remotes when pak is absent.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / "update-snapshots.yml"
FAILURES = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok else f": {detail}"))
    if not ok:
        FAILURES.append(name)


def step_run(name_prefix):
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in wf["jobs"].values():
        for step in job["steps"]:
            if step.get("name", "").startswith(name_prefix):
                return step["run"]
    raise SystemExit(f"no step named {name_prefix!r}")


def stub(path, body):
    path.write_text("#!/bin/bash\n" + body + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_detect(rscript_body):
    """Run the detect step; return (preinstalled, r_libs_set, combined output)."""
    script = step_run("Detect a preinstalled R")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        stub(bin_dir / "sudo", "exit 1")
        shutil.copy(shutil.which("mkdir"), bin_dir / "mkdir")
        if rscript_body is not None:
            stub(bin_dir / "Rscript", rscript_body)
        out, env = tmp / "output", tmp / "env"
        out.touch()
        env.touch()
        run = subprocess.run(
            [shutil.which("bash"), "-c", script],
            env={
                "PATH": str(bin_dir),
                "DECLARED": "false",
                "RUNNER_TEMP": str(tmp),
                "GITHUB_OUTPUT": str(out),
                "GITHUB_ENV": str(env),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        pre = [line for line in out.read_text().splitlines() if line.startswith("preinstalled=")]
        libs = "R_LIBS_USER=" in env.read_text() and (tmp / "r-library").is_dir()
        return (pre[0] if pre else ""), libs, run.stdout + run.stderr


pre, libs, log = run_detect("exit 0")
check("pak present: uses the runner R", pre == "preinstalled=true" and not libs, f"{pre} {libs} {log}")

pre, libs, log = run_detect("exit 1")
check(
    "no pak: still uses the runner R, with a per-job library",
    pre == "preinstalled=true" and libs and "remotes::install_deps" in log,
    f"{pre} {libs} {log}",
)

pre, libs, log = run_detect(None)
check(
    "no R at all: not preinstalled, and says so",
    pre == "preinstalled=false" and not libs and "no R on the runner" in log,
    f"{pre} {libs} {log}",
)

install = step_run("Install R dependencies (preinstalled R)")
check("install step keeps pak when present", "pak::local_install_dev_deps" in install, install)
check("install step falls back to remotes::install_deps", "remotes::install_deps" in install, install)

if FAILURES:
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1)
print("\nall passed")
