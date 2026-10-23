#!/usr/bin/env python3
"""Tests for quarto-publish/render-per-file.py, using a fake `quarto` on PATH.

Usage:
    python3 run-render-per-file-tests.py
"""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "quarto-publish" / "render-per-file.py"

FAKE_QUARTO = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_QUARTO_LOG"]
if args[0] == "inspect":
    if args[1] == ".":
        files = [os.path.join(os.getcwd(), n) for n in ("a.qmd", "b.qmd", "c.qmd")]
        print(json.dumps({"files": {"input": files}}))
    else:
        formats = {"c.qmd": {"html": {}}}.get(args[1], {"html": {}, "pdf": {}})
        print(json.dumps({"formats": formats}))
else:
    with open(log, "a") as f:
        f.write(" ".join(args) + "\\n")
    sys.exit(1 if os.environ.get("FAKE_QUARTO_FAIL") in args else 0)
"""


def run(formats, fail_on=""):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        fake = tmp / "bin" / "quarto"
        fake.parent.mkdir()
        fake.write_text(FAKE_QUARTO, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        project = tmp / "proj"
        project.mkdir()
        log = tmp / "log.txt"
        env = dict(
            os.environ,
            PATH=f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
            FAKE_QUARTO_LOG=str(log),
            FAKE_QUARTO_FAIL=fail_on,
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(project), "_site", *formats],
            env=env, capture_output=True, text=True, check=False,
        )
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return result.returncode, calls, result.stdout


def main():
    errors = []

    code, calls, _ = run(["pdf"])
    expected = ["render a.qmd --to pdf --output-dir _site",
                "render b.qmd --to pdf --output-dir _site"]
    if code != 0 or calls != expected:
        errors.append(f"pdf: renders only files that declare it, got {code} {calls}")

    code, calls, _ = run(["nonesuch"])
    if code == 0 or calls:
        errors.append("an unmatched format must fail, not pass vacuously")

    code, calls, _ = run(["pdf"], fail_on="a.qmd")
    if code == 0 or len(calls) != 2:
        errors.append(f"a failed file fails the run but the rest still render: {code} {calls}")

    if errors:
        print("\n".join(errors))
        return 1
    print("render-per-file tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
