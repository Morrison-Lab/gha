#!/usr/bin/env python3
"""Offline unit tests for audit_example_stubs.py (gha#839).

Verifies that:
1. Clean stubs with populated with: blocks pass.
2. Clean stubs with commented # with: blocks pass when uncommented.
3. Stubs carrying an active with: and a commented # with: in the same job fail.
4. Direct duplicate keys in YAML mappings are detected and rejected.
5. Multi-job workflows with with: in one job and # with: in another pass cleanly.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_example_stubs as audit  # noqa: E402


def run_tests() -> None:
    cases = [
        (
            "clean_with_and_commented_inputs",
            """
name: Clean With
on: workflow_dispatch
jobs:
  review:
    uses: Morrison-Lab/gha/.github/workflows/cursor-code-review.yml@v2
    with:
      pr-number: 123
      # dry-run: true
""",
            True,
            [],
        ),
        (
            "clean_commented_with_only",
            """
name: Clean Commented
on: workflow_dispatch
jobs:
  check:
    uses: Morrison-Lab/gha/.github/workflows/check-extra.yml@v2
    # with:
    #   path: '.'
""",
            True,
            [],
        ),
        (
            "duplicate_with_in_same_job",
            """
name: Bad Duplicate With
on: workflow_dispatch
jobs:
  review:
    uses: Morrison-Lab/gha/.github/workflows/cursor-code-review.yml@v2
    with:
      pr-number: 123
    # with:
    #   dry-run: true
""",
            False,
            ["creates duplicate key", "duplicate key 'with'"],
        ),
        (
            "direct_duplicate_mapping_key",
            """
name: Direct Duplicate Key
name: Duplicate Name
on: workflow_dispatch
jobs:
  check:
    uses: Morrison-Lab/gha/.github/workflows/check-extra.yml@v2
""",
            False,
            ["strict YAML parse error", "duplicate key 'name'"],
        ),
        (
            "multi_job_isolated_with",
            """
name: Multi Job
on: workflow_dispatch
jobs:
  job1:
    uses: Morrison-Lab/gha/.github/workflows/r-cmd-check.yml@v2
    # with:
    #   path: '.'
  job2:
    uses: Morrison-Lab/gha/.github/workflows/r-cmd-check.yml@v2
    with:
      hard: true
""",
            True,
            [],
        ),
    ]

    failures = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        for name, text, should_pass, expected_substrs in cases:
            file_path = tmp_path / f"{name}.yml"
            file_path.write_text(text.strip() + "\n", encoding="utf-8")
            errors = audit.audit_file_content(file_path, text)

            if should_pass and errors:
                print(f"FAIL {name}: expected clean pass, got errors: {errors}", file=sys.stderr)
                failures += 1
            elif not should_pass and not errors:
                print(f"FAIL {name}: expected failure, passed cleanly", file=sys.stderr)
                failures += 1
            elif not should_pass:
                joined = " ".join(errors)
                missing = [s for s in expected_substrs if s not in joined]
                if missing:
                    print(
                        f"FAIL {name}: errors missing expected substrings {missing}. Got: {errors}",
                        file=sys.stderr,
                    )
                    failures += 1
                else:
                    print(f"OK   {name}")
            else:
                print(f"OK   {name}")

    if failures:
        print(f"::error::{failures} test cases failed.", file=sys.stderr)
        sys.exit(1)

    print("All run-audit-example-stubs tests passed cleanly.")


if __name__ == "__main__":
    run_tests()
