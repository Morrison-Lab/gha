#!/usr/bin/env python3
"""Assert all workflow jobs set timeout-minutes on runner jobs and only allowed keys on caller jobs.

Follow-up for gha#328, gha#504, gha#582, and gha#590.

A GitHub Actions workflow job must either run on a runner (declaring ``runs-on``)
or call a reusable workflow (declaring ``uses``).

1. **Runner jobs (`runs-on`)**: Every job running on a runner must declare
   ``timeout-minutes`` so the bound on a runaway job is deliberate and
   usually far tighter than GitHub's own 360-minute default job timeout
   (gha#328, gha#504).
2. **Caller jobs (`uses`)**: A job invoking a reusable workflow cannot legally
   set ``timeout-minutes`` -- GitHub Actions rejects it outright at workflow
   load time (startup failure with 0 jobs, gha#582). Only the following keys
   are allowed on caller jobs:
   ``name``, ``uses``, ``with``, ``secrets``, ``needs``, ``if``,
   ``permissions``, ``strategy``, ``concurrency``.

Previously, selftest checked ``timeout-minutes`` with a file-level grep
(``grep -rL 'timeout-minutes' .github/workflows/*.yml``). That had two defects
(gha#590):
- It was satisfied by comment text in caller workflows, making comments
  load-bearing for CI.
- It was vacuous for caller workflows because it could not check whether the
  actual caller jobs or runner jobs conformed to GitHub's schema rules.

This script replaces the file-level grep with an authoritative job-level YAML
assertion.

Usage::

    python3 run-workflow-job-guard-tests.py [--workflows-dir DIR] [FILES ...]
    python3 run-workflow-job-guard-tests.py --self-test
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Shared with the two workflow audits and the permissions-docs suite rather
# than re-globbed here: a fourth copy of the discovery rule is a fourth place
# for it to drift back to `*.yml` only (gha#705, gha#716).
from workflow_discovery import discover_workflows, skip_if_restored  # noqa: E402

DEFAULT_WORKFLOWS_DIR = ".github/workflows"

# Allowed top-level keys for a job that calls a reusable workflow via `uses:`.
# Per GitHub Actions workflow syntax:
# https://docs.github.com/en/actions/sharing-automations/reusing-workflows#calling-a-reusable-workflow
ALLOWED_CALLER_KEYS = {
    "name",
    "uses",
    "with",
    "secrets",
    "needs",
    "if",
    "permissions",
    "strategy",
    "concurrency",
}


def die(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


def load_yaml(path: pathlib.Path):
    try:
        import yaml
    except ImportError:  # pragma: no cover
        die(
            "PyYAML is required to validate workflow jobs "
            "(install it with `python3 -m pip install pyyaml`)."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_workflow_doc(doc, filename: str) -> list[str]:
    """Validate a parsed workflow document for job key and timeout rules.

    Returns a list of error strings (empty if valid).
    """
    errors: list[str] = []
    if not isinstance(doc, dict):
        # Empty or non-dict YAML files are not valid workflow definitions
        return [f"{filename}: document root is not a mapping"]

    jobs = doc.get("jobs")
    if jobs is None:
        return [f"{filename}: missing 'jobs' mapping"]
    if not isinstance(jobs, dict):
        return [f"{filename}: 'jobs' is not a mapping"]
    if not jobs:
        return [f"{filename}: 'jobs' mapping is empty"]

    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            errors.append(f"{filename}: job '{job_id}' is not a mapping")
            continue

        if "uses" in job:
            illegal = set(job) - ALLOWED_CALLER_KEYS
            if illegal:
                errors.append(
                    f"{filename}: caller job '{job_id}' sets illegal keys for a reusable workflow call: "
                    f"{sorted(illegal)} (only {sorted(ALLOWED_CALLER_KEYS)} allowed; "
                    f"in particular, timeout-minutes is not supported on uses: jobs, see gha#582)"
                )
        elif "runs-on" in job:
            if "timeout-minutes" not in job:
                errors.append(
                    f"{filename}: runner job '{job_id}' missing 'timeout-minutes' (see gha#328, gha#504)"
                )
            else:
                timeout = job["timeout-minutes"]
                # Reject only a missing or empty value here; whether the
                # value is a well-formed integer or expression is the
                # adjacent actionlint audit's job (schema validation), not
                # this guard's.
                if timeout is None or (isinstance(timeout, str) and not timeout.strip()):
                    errors.append(
                        f"{filename}: runner job '{job_id}' has empty 'timeout-minutes'"
                    )
        else:
            errors.append(
                f"{filename}: job '{job_id}' has neither 'runs-on' nor 'uses'"
            )

    return errors


def validate_workflow_files(files: list[pathlib.Path]) -> list[str]:
    all_errors: list[str] = []
    for file_path in files:
        if not file_path.is_file():
            continue
        try:
            doc = load_yaml(file_path)
        except Exception as exc:
            all_errors.append(f"{file_path}: YAML parse error: {exc}")
            continue
        errors = validate_workflow_doc(doc, str(file_path))
        all_errors.extend(errors)
    return all_errors


def run_self_test() -> None:
    """Exercise validation against positive and negative synthetic fixtures."""
    test_cases = [
        # 1. Valid runner job with timeout-minutes
        (
            "valid_runner",
            """
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: echo ok
""",
            True,
            [],
        ),
        # 2. Runner job missing timeout-minutes
        (
            "missing_timeout",
            """
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
            False,
            ["missing 'timeout-minutes'"],
        ),
        # 3. Runner job with timeout-minutes in comment only (vacuous comment regression)
        (
            "comment_only_timeout",
            """
name: Test
on: push
jobs:
  test:
    # timeout-minutes: 10
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
            False,
            ["missing 'timeout-minutes'"],
        ),
        # 4. Valid caller job with uses: and allowed keys
        (
            "valid_caller",
            """
name: Caller
on: push
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
    with:
      arg: value
    secrets: inherit
    permissions:
      contents: read
""",
            True,
            [],
        ),
        # 5. Caller job with timeout-minutes (gha#582 bug)
        (
            "caller_with_timeout",
            """
name: Caller
on: push
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
    timeout-minutes: 60
""",
            False,
            ["caller job 'call' sets illegal keys", "timeout-minutes"],
        ),
        # 6. Caller job with disallowed steps:
        (
            "caller_with_steps",
            """
name: Caller
on: push
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
    steps:
      - run: echo ok
""",
            False,
            ["caller job 'call' sets illegal keys", "steps"],
        ),
        # 7. Job missing both runs-on and uses
        (
            "job_missing_exec_target",
            """
name: Test
on: push
jobs:
  bad:
    name: Bad Job
""",
            False,
            ["has neither 'runs-on' nor 'uses'"],
        ),
        # 8. Non-dict jobs
        (
            "non_dict_jobs",
            """
name: Test
on: push
jobs:
  - test
""",
            False,
            ["'jobs' is not a mapping"],
        ),
        # 9. Runner job with dynamic timeout expression
        (
            "dynamic_timeout",
            """
name: Test
on:
  workflow_call:
    inputs:
      timeout-minutes:
        type: number
        default: 20
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: ${{ inputs.timeout-minutes }}
    steps:
      - run: echo ok
""",
            True,
            [],
        ),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        for name, yaml_text, should_pass, expected_substrs in test_cases:
            case_file = tmp_path / f"{name}.yml"
            case_file.write_text(yaml_text, encoding="utf-8")
            errors = validate_workflow_files([case_file])

            if should_pass and errors:
                die(f"Self-test '{name}' failed unexpectedly: {errors}")
            elif not should_pass and not errors:
                die(f"Self-test '{name}' was expected to fail but passed cleanly")
            elif not should_pass:
                joined = " ".join(errors)
                for substr in expected_substrs:
                    if substr not in joined:
                        die(
                            f"Self-test '{name}' error did not contain expected substring '{substr}'. "
                            f"Got errors: {errors}"
                        )

    # gha#705: the table above hands content straight to the validator, so it
    # cannot see the DISCOVERY glob -- which is where the .yaml gap lived. A
    # tmpdir carrying one file per extension (plus one non-workflow file that
    # must be ignored) pins discovery itself; reverting discover_workflows to
    # a *.yml-only glob turns this red (confirmed by mutation).
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        (tmp_path / "a.yml").write_text("name: a\n", encoding="utf-8")
        (tmp_path / "b.yaml").write_text("name: b\n", encoding="utf-8")
        (tmp_path / "c.txt").write_text("not a workflow\n", encoding="utf-8")
        found = [p.name for p in discover_workflows(tmp_path)]
        if found != ["a.yml", "b.yaml"]:
            die(
                "Self-test 'discovery_both_extensions' failed: expected "
                f"['a.yml', 'b.yaml'], got {found} (gha#705)"
            )

    print("All run-workflow-job-guard self-tests passed cleanly.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run unit tests on synthetic valid and invalid workflow fixtures.",
    )
    parser.add_argument(
        "--workflows-dir",
        type=pathlib.Path,
        default=pathlib.Path(DEFAULT_WORKFLOWS_DIR),
        help=f"Directory containing workflow YAML files (default: {DEFAULT_WORKFLOWS_DIR}).",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=pathlib.Path,
        help="Specific workflow files to validate (defaults to all *.yml and *.yaml in --workflows-dir).",
    )

    args = parser.parse_args(argv)

    if args.self_test:
        run_self_test()
        return

    if skip_if_restored(args.workflows_dir, "workflow job guard check"):
        return

    files_to_check = args.files
    if not files_to_check:
        if not args.workflows_dir.is_dir():
            die(f"Workflows directory not found: {args.workflows_dir}")
        files_to_check = discover_workflows(args.workflows_dir)

    if not files_to_check:
        die("No workflow files found to validate.")

    errors = validate_workflow_files(files_to_check)
    if errors:
        print(f"Found {len(errors)} workflow job validation errors:", file=sys.stderr)
        for err in errors:
            print(f"::error::{err}", file=sys.stderr)
        sys.exit(1)

    print(
        f"All {len(files_to_check)} workflow files passed job key and timeout checks."
    )


if __name__ == "__main__":
    main()
