#!/usr/bin/env python3
"""Run preview-deploy.yml's "Read PR metadata" step against a stub `gh`.

The preview artifact is written by the build half, which a fork PR controls,
so the deploy half must refuse a PR number or action it cannot vouch for.
Each case runs the step's own `run:` block, read from the workflow file, with
a fake `gh` on PATH that answers the PR lookup.

Usage:
    python3 run-preview-deploy-metadata-tests.py
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

try:
    import yaml
except ImportError:
    print("::error::PyYAML is required to run these tests.", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "preview-deploy.yml"
STEP_NAME = "Read PR metadata"

# What the stub `gh` prints for each PR number: "<head repo>#<head branch>".
PULLS = {
    "7": "octo/site#feature",
    "8": "fork/site#evil",
}

STUB_GH = """#!/usr/bin/env bash
# Answers `gh api repos/<repo>/pulls/<n> --jq ...` from STUB_PULLS.
url="$2"
n="${url##*/}"
while IFS='=' read -r key value; do
  if [ "$key" = "$n" ]; then
    printf '%s\\n' "$value"
    exit 0
  fi
done <<< "$STUB_PULLS"
echo "gh: Not Found (HTTP 404)" >&2
exit 1
"""


def step_script() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in doc["jobs"]["deploy"]["steps"]:
        if step.get("name") == STEP_NAME:
            return step["run"]
    raise SystemExit(f"::error::No step named {STEP_NAME!r} in {WORKFLOW}")


def run_case(script: str, pr_number: str, action: str, head_repo: str, head_branch: str):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        meta = tmp_path / "_preview_download" / "meta"
        meta.mkdir(parents=True)
        (meta / "pr-number.txt").write_text(pr_number, encoding="utf-8")
        (meta / "action.txt").write_text(action, encoding="utf-8")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(STUB_GH, encoding="utf-8")
        gh.chmod(0o755)
        output = tmp_path / "github_output"
        output.write_text("", encoding="utf-8")
        env = {
            "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "octo/site",
            "GH_TOKEN": "unused",
            "HEAD_REPO": head_repo,
            "HEAD_BRANCH": head_branch,
            "STUB_PULLS": "\n".join(f"{k}={v}" for k, v in PULLS.items()),
        }
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, output.read_text(encoding="utf-8")


# (description, pr-number.txt, action.txt, head repo, head branch, accepted?)
CASES = [
    ("matching same-repo PR deploys", "7\n", "deploy\n", "octo/site", "feature", True),
    ("matching fork PR deploys", "8", "deploy", "fork/site", "evil", True),
    ("matching PR may remove its own preview", "7", "remove", "octo/site", "feature", True),
    ("a build naming another PR is refused", "7", "deploy", "fork/site", "evil", False),
    ("a build removing another PR's preview is refused", "7", "remove", "fork/site", "evil", False),
    ("a path in place of a number is refused", "../..", "deploy", "octo/site", "feature", False),
    ("an empty number is refused", "", "deploy", "octo/site", "feature", False),
    ("an unknown action is refused", "7", "publish", "octo/site", "feature", False),
    ("a PR the API cannot find is refused", "99", "deploy", "octo/site", "feature", False),
]


def main() -> int:
    script = step_script()
    failures = 0
    for desc, pr_number, action, head_repo, head_branch, accepted in CASES:
        result, outputs = run_case(script, pr_number, action, head_repo, head_branch)
        if accepted:
            expected = f"pr-number={pr_number.strip()}\naction={action.strip()}\n"
            ok = result.returncode == 0 and outputs == expected
        else:
            # A refusal must stop the job and leave no outputs for later steps.
            ok = result.returncode != 0 and outputs == "" and "::error::" in result.stdout
        if not ok:
            failures += 1
            print(f"::error::FAIL: {desc}")
            print(f"  exit={result.returncode} outputs={outputs!r}")
            print(f"  stdout={result.stdout!r} stderr={result.stderr!r}")
        else:
            print(f"ok: {desc}")
    if failures:
        print(f"::error::{failures} of {len(CASES)} cases failed")
        return 1
    print(f"All {len(CASES)} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
