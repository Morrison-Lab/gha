#!/usr/bin/env python3
"""Offline unit tests for audit_callee_permissions.py (gha#836).

Verifies that audit_callee_permissions correctly detects and reports:
- Permission key additions on jobs in reusable workflows
- Permission value widening (read -> write, dict -> write-all)
- Jobs gaining a permissions block (where none was declared before)
- Jobs dropping a permissions block (falling back to caller/workflow inheritance)
- Workflow-level permission key additions and value widening
- Unchanged permissions with comments or reordering (no false positives)
- Permission narrowing (write -> read, read -> none, dropping keys) (permitted)
- Exemption of brand-new reusable workflows (no existing callers to break)
- Notice emitted when reusable workflow is removed or renamed
- id-token: write addition detected when base was write-all / read-all (id-token not in shorthand)
- Negative controls: malformed YAML, invalid permission values
- Extension support: both .yml and .yaml workflows evaluated
- Non-reusable workflows (no on: workflow_call) ignored
- Skip when workflows restored marker is present

Usage::

    python3 run-audit-callee-permissions-tests.py
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import audit_callee_permissions as audit  # noqa: E402

failures = 0
cases = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures, cases
    cases += 1
    if condition:
        print(f"OK   {label}")
    else:
        print(f"::error::{label}{': ' + detail if detail else ''}", file=sys.stderr)
        failures += 1


def run_git(args: list[str], cwd: pathlib.Path) -> str:
    res = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout


def init_repo(path: pathlib.Path) -> None:
    run_git(["init", "-q"], cwd=path)
    run_git(["config", "user.name", "Test Runner"], cwd=path)
    run_git(["config", "user.email", "t@example.invalid"], cwd=path)  # phi-allow
    run_git(["config", "commit.gpgsign", "false"], cwd=path)


def commit_all(path: pathlib.Path, message: str) -> str:
    run_git(["add", "."], cwd=path)
    run_git(["commit", "-q", "-m", message, "--allow-empty"], cwd=path)
    return run_git(["rev-parse", "HEAD"], cwd=path).strip()


def run_audit(
    base_ref: str,
    head_ref: str | None,
    cwd: pathlib.Path,
    workflows_dir: str = ".github/workflows",
) -> tuple[int, str]:
    args = ["--base-ref", base_ref, "--workflows-dir", workflows_dir]
    if head_ref is not None:
        args.extend(["--head-ref", head_ref])

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        orig_cwd = pathlib.Path.cwd()
        try:
            os.chdir(cwd)
            code = audit.main(args)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        finally:
            os.chdir(orig_cwd)

    return code, out.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        repo = root / "repo"
        repo.mkdir()
        init_repo(repo)

        wf_dir = repo / ".github" / "workflows"
        wf_dir.mkdir(parents=True)

        # 1. Base commit: clean reusable workflows (both .yml and .yaml) and non-reusable
        (wf_dir / "reusable1.yml").write_text(
            """name: Reusable 1
on:
  workflow_call:

jobs:
  job-a:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: read
    steps:
      - run: echo a
  job-b:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - run: echo b
  job-unconstrained:
    runs-on: ubuntu-latest
    steps:
      - run: echo unconstrained
""",
            encoding="utf-8",
        )

        (wf_dir / "reusable2.yaml").write_text(
            """name: Reusable 2
on:
  workflow_call:

permissions:
  contents: read

jobs:
  worker:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: echo worker
  shorthand-job:
    runs-on: ubuntu-latest
    permissions: write-all
    steps:
      - run: echo write-all
""",
            encoding="utf-8",
        )

        # Non-reusable workflow: permission additions here must be ignored by audit
        (wf_dir / "caller.yml").write_text(
            """name: Caller
on:
  push:

jobs:
  call:
    uses: ./.github/workflows/reusable1.yml
""",
            encoding="utf-8",
        )

        base_sha = commit_all(repo, "Initial base commit")
        run_git(["tag", "v1"], cwd=repo)

        # -------------------------------------------------------------
        # Test 1: Unchanged state vs base_ref
        code, out = run_audit("v1", None, cwd=repo)
        check("identical working tree reports clean (exit 0)", code == 0, f"output: {out}")
        check("identical working tree output summary", "examined 5 jobs across 2 reusable workflows" in out, out)

        # -------------------------------------------------------------
        # Test 2: Added comments and key reordering (no structural permission change)
        (wf_dir / "reusable1.yml").write_text(
            """name: Reusable 1
on:
  workflow_call:

jobs:
  job-a:
    runs-on: ubuntu-latest
    # Reordered keys and added trailing comments
    permissions:
      issues: read # comments here
      contents: read
    steps:
      - run: echo a
  job-b:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - run: echo b
  job-unconstrained:
    runs-on: ubuntu-latest
    steps:
      - run: echo unconstrained
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("comments and key reordering do not trigger violations", code == 0, out)

        # -------------------------------------------------------------
        # Test 3: Permission narrowing (permitted)
        # job-b: write -> read; job-a: issues: read -> issues: none; contents: read -> dropped
        (wf_dir / "reusable1.yml").write_text(
            """name: Reusable 1
on:
  workflow_call:

jobs:
  job-a:
    runs-on: ubuntu-latest
    permissions:
      issues: none
    steps:
      - run: echo a
  job-b:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: echo b
  job-unconstrained:
    runs-on: ubuntu-latest
    steps:
      - run: echo unconstrained
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("permission narrowing (write->read, read->none, dropped keys) is allowed", code == 0, out)

        # -------------------------------------------------------------
        # Test 4: Added permission key to existing job (VIOLATION)
        # Reset to base first
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable1.yml").write_text(
            """name: Reusable 1
on:
  workflow_call:

jobs:
  job-a:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: read
      checks: read  # NEW KEY
    steps:
      - run: echo a
  job-b:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - run: echo b
  job-unconstrained:
    runs-on: ubuntu-latest
    steps:
      - run: echo unconstrained
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("adding a permission key to a job is rejected", code == 1, out)
        check(
            "violation message specifies file, job, and added key",
            "job 'job-a' added permission 'checks: read'" in out,
            out,
        )

        # -------------------------------------------------------------
        # Test 5: Widened permission value (read -> write) (VIOLATION)
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable1.yml").write_text(
            """name: Reusable 1
on:
  workflow_call:

jobs:
  job-a:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write  # WIDENED FROM READ
    steps:
      - run: echo a
  job-b:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - run: echo b
  job-unconstrained:
    runs-on: ubuntu-latest
    steps:
      - run: echo unconstrained
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("widening permission from read to write is rejected", code == 1, out)
        check("violation message reports widening", "widened permission 'issues': 'read' -> 'write'" in out, out)

        # -------------------------------------------------------------
        # Test 6: Job gaining permissions block (VIOLATION)
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable1.yml").write_text(
            """name: Reusable 1
on:
  workflow_call:

jobs:
  job-a:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: read
    steps:
      - run: echo a
  job-b:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - run: echo b
  job-unconstrained:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: read # GAINED BLOCK
    steps:
      - run: echo unconstrained
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("job gaining permissions block is rejected", code == 1, out)
        check(
            "violation message reports gained permissions block",
            "job 'job-unconstrained' gained permissions block requesting: pull-requests: read" in out,
            out,
        )

        # -------------------------------------------------------------
        # Test 7: Job dropping permissions block (VIOLATION)
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable1.yml").write_text(
            """name: Reusable 1
on:
  workflow_call:

jobs:
  job-a:
    runs-on: ubuntu-latest
    # DROPPED PERMISSIONS BLOCK
    steps:
      - run: echo a
  job-b:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - run: echo b
  job-unconstrained:
    runs-on: ubuntu-latest
    steps:
      - run: echo unconstrained
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("job dropping permissions block is rejected", code == 1, out)
        check(
            "violation message reports dropped block",
            "job 'job-a' dropped its permissions block (reverts to unconstrained inheritance)" in out,
            out,
        )

        # -------------------------------------------------------------
        # Test 8: Workflow-level widening and write-all shorthand
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable2.yaml").write_text(
            """name: Reusable 2
on:
  workflow_call:

permissions: write-all # WIDENED TO WRITE-ALL

jobs:
  worker:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: echo worker
  shorthand-job:
    runs-on: ubuntu-latest
    permissions: write-all
    steps:
      - run: echo write-all
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("workflow-level write-all expansion flags widenings", code == 1, out)
        check("workflow level violation reported", "workflow level widened permission" in out, out)

        # -------------------------------------------------------------
        # Test 9: id-token explicitly added to job whose base had write-all (VIOLATION)
        # write-all does NOT include id-token, so adding id-token: write is a widening!
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable2.yaml").write_text(
            """name: Reusable 2
on:
  workflow_call:

permissions:
  contents: read

jobs:
  worker:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: echo worker
  shorthand-job:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write # ADDED EXPLICIT ID-TOKEN (not granted by write-all)
    steps:
      - run: echo write-all
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("adding id-token: write after write-all is flagged as widening", code == 1, out)
        check("id-token added key violation reported", "added permission 'id-token: write'" in out, out)

        # -------------------------------------------------------------
        # Test 10: Brand-new reusable workflow added (exempt: no callers pinned to base)
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable3.yml").write_text(
            """name: Brand New Reusable
on:
  workflow_call:

jobs:
  new-job:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - run: echo brand new
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("brand-new reusable workflow added since base is exempt", code == 0, out)
        check("notice emitted for added workflow", "reusable workflow '.github/workflows/reusable3.yml' was added or renamed" in out, out)

        # -------------------------------------------------------------
        # Test 11: Reusable workflow removed/renamed since base (notice emitted)
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable1.yml").unlink()
        code, out = run_audit("v1", None, cwd=repo)
        check("removed/renamed workflow reports notice for hand-check", "reusable workflow '.github/workflows/reusable1.yml' was removed or renamed" in out, out)

        # -------------------------------------------------------------
        # Test 12: Non-reusable workflow permission changes (ignored)
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "caller.yml").write_text(
            """name: Caller
on:
  push:

permissions: write-all

jobs:
  call:
    runs-on: ubuntu-latest
    permissions: write-all
    steps:
      - run: echo caller changed
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("non-reusable workflows are ignored by callee audit", code == 0, out)

        # -------------------------------------------------------------
        # Test 13: Comparing two committed git refs directly (--head-ref)
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable1.yml").write_text(
            """name: Reusable 1
on:
  workflow_call:

jobs:
  job-a:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: read
      actions: read # ADDED IN COMMIT
    steps:
      - run: echo a
  job-b:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - run: echo b
  job-unconstrained:
    runs-on: ubuntu-latest
    steps:
      - run: echo unconstrained
""",
            encoding="utf-8",
        )
        head_sha = commit_all(repo, "Add actions: read")
        code, out = run_audit("v1", head_sha, cwd=repo)
        check("comparing two git refs detects violation", code == 1, out)
        check("violation identifies added action permission", "added permission 'actions: read'" in out, out)

        # -------------------------------------------------------------
        # Test 14: Negative control: malformed YAML in head
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable1.yml").write_text("name: broken:\n  - [", encoding="utf-8")
        code, out = run_audit("v1", None, cwd=repo)
        check("malformed YAML in head exits with code 2", code == 2, out)
        check("error message names YAML parse error", "mapping values are not allowed here" in out or "YAML parse error" in out, out)

        # -------------------------------------------------------------
        # Test 15: Negative control: invalid permission value (e.g. 'admin')
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / "reusable1.yml").write_text(
            """name: Reusable 1
on:
  workflow_call:

jobs:
  job-a:
    runs-on: ubuntu-latest
    permissions:
      contents: admin
    steps:
      - run: echo a
""",
            encoding="utf-8",
        )
        code, out = run_audit("v1", None, cwd=repo)
        check("invalid permission value exits with code 2", code == 2, out)
        check("error message names unexpected permission value", "unknown permission value 'admin'" in out, out)

        # -------------------------------------------------------------
        # Test 16: Restored workflows directory marker skips audit cleanly
        run_git(["checkout", "."], cwd=repo)
        (wf_dir / ".restored-from-default-branch").write_text("", encoding="utf-8")
        code, out = run_audit("v1", None, cwd=repo)
        check("restored marker causes audit to skip cleanly (exit 0)", code == 0, out)
        check("restored notice emitted", "Skipping callee permissions audit" in out, out)

    if failures == 0:
        print(f"\nAll {cases} test cases passed.")
        return 0
    print(f"\n{failures} of {cases} test cases failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
