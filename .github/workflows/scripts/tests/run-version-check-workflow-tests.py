#!/usr/bin/env python3
"""Pin `version-check.yml`'s live-label exemption contract (gha#722).

The defect this guards against is silent in both directions, which is why it
wants a test rather than care.  Reading the label from
``github.event.pull_request.labels`` returns the labels frozen into the
TRIGGERING EVENT's payload, so a label applied afterwards is invisible and an
approved or re-run job reuses the same stale payload --- the exemption simply
never fires, and a check that never exempts looks exactly like a check whose
exemption nobody asked for.

Nothing about the workflow's own output distinguishes the two, and this repo's
`_selftest.yml` cannot exercise the reusable workflow end to end: it needs a
live `pull_request` event and a labelled PR.  So the contract is asserted
against the YAML instead, the same way `run-r-cmd-check-workflow-tests.py`
pins facts a live `R CMD check` in this repo cannot.

Usage::

    python3 run-version-check-workflow-tests.py [--workflow PATH] [--self-test]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

# tests/ -> scripts/ -> workflows/ -> .github/ -> repo root
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
DEFAULT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "version-check.yml"

STALE_PAYLOAD = "github.event.pull_request.labels"


def die(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    raise SystemExit(1)


def exempt_step(text: str) -> str:
    """Return the body of the `Check if this PR is exempt` step.

    Sliced from its own `- name:` to the next one so an assertion about this
    step cannot be satisfied by text belonging to a later step.
    """
    start = text.find("- name: Check if this PR is exempt")
    if start == -1:
        die("version-check.yml no longer has a 'Check if this PR is exempt' step")
    nxt = text.find("      - name:", start + 1)
    return text[start:] if nxt == -1 else text[start:nxt]


def strip_comment_lines(text: str) -> str:
    """Drop whole-line YAML comments before scanning for a banned construct.

    The passage explaining WHY the stale payload path is wrong has to name
    that path, so a scan over the raw file flags the very comment documenting
    the rule --- the self-implicating-example problem ai-config's
    `examples-are-scanned.md` describes. Teaching the checker about comment
    regions is the fix there; rewording the prose so it cannot say what it
    means is not.

    Whole lines only. A trailing comment after real YAML is left alone, so a
    live read cannot be hidden from this scan by appending a `#` to its line.
    """
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def check(workflow: pathlib.Path) -> int:
    text = workflow.read_text(encoding="utf-8")
    code = strip_comment_lines(text)
    step = exempt_step(text)
    failures = 0

    def want(condition: bool, message: str) -> None:
        nonlocal failures
        if condition:
            print(f"OK   {message}")
        else:
            print(f"::error::{message}", file=sys.stderr)
            failures += 1

    # The defect itself. Anywhere in the file, not just this step: a job-level
    # `if:` reading the payload would reintroduce it one level up.
    want(
        STALE_PAYLOAD not in code,
        f"the stale event payload ({STALE_PAYLOAD}) is not read anywhere",
    )

    # `pull-requests: read`, not `issues: read`: GitHub authorizes a label read
    # on an issue object that is a pull request against the pull-requests
    # permission, and `issues: read` alone returned 403 on check-news's first
    # consumer run (gha#724 / gha#725). Asserting the wrong one here would pin
    # a permission set that cannot make the call.
    want(
        re.search(r"pull-requests:\s*read", code) is not None,
        "the job grants pull-requests: read, which authorizes the label read",
    )

    want(
        "gh api" in step and "--paginate" in step,
        "the exempt step reads labels from the API with --paginate",
    )
    want(
        re.search(r"/issues/\$PR_NUMBER/labels", step) is not None,
        "the exempt step reads the PR's live labels endpoint",
    )

    # Fail-loud: the read is a plain assignment, so `set -e` aborts on an API
    # failure. Swallowing it yields an empty label stream, which reproduces
    # the never-exempt defect this whole step exists to fix.
    want(
        re.search(r"^\s*labels=\$\(gh api", step, re.M) is not None,
        "the API read is a plain assignment, so set -e sees a failure",
    )
    # ... and not inside an `if`/`while` condition, where `set -e` is inert by
    # design: a compound-command context is exactly where a failing read stops
    # aborting and starts reading as "no labels".
    want(
        re.search(r"^\s*(?:if|while|until)\s+.*\bgh api", step, re.M) is None,
        "the API read is not inside a condition, where set -e would not fire",
    )
    want(
        re.search(r"^\s*set -euo pipefail", step, re.M) is not None,
        "the exempt step runs under set -euo pipefail",
    )
    want(
        "|| true" not in step and "|| :" not in step,
        "the exempt step does not swallow a failed API read",
    )

    # Case-insensitive on both sides, mirroring the payload `contains()` this
    # replaced.
    want(
        len(re.findall(r"tr '\[:upper:\]' '\[:lower:\]'", step)) >= 2,
        "both the input label and each live label are lowercased before comparison",
    )

    # Only the configured input is honoured. gha#721's sibling matched a second
    # hardcoded spelling because the action it wraps recognizes that spelling
    # itself; nothing downstream here reads labels, so a literal would defeat a
    # caller's override.
    want(
        re.search(r'=\s*["\']no version increment["\']', step) is None,
        "no hardcoded label spelling competes with the configurable input",
    )

    # The second bypass must survive the rewrite.
    want(
        "$BUMP_BRANCH" in step,
        "the bump-branch bypass still short-circuits the check",
    )

    if failures:
        print(f"::error::{failures} version-check contract assertion(s) failed", file=sys.stderr)
        return 1
    print("All version-check workflow contract assertions passed.")
    return 0


def run_self_test() -> int:
    """Confirm each assertion can actually fail, not merely pass today."""
    import tempfile

    base = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    mutations = {
        "stale payload restored": (
            "HEAD_REF: ${{ github.head_ref }}",
            "HEAD_REF: ${{ github.head_ref }}\n"
            "          HAS_LABEL: ${{ contains(github.event.pull_request.labels.*.name, inputs.x) }}",
        ),
        "pull-requests: read dropped": ("      pull-requests: read\n", ""),
        "--paginate dropped": ("gh api --paginate", "gh api"),
        "read swallowed": ("--jq '.[].name')", "--jq '.[].name' || true)"),
        "case folding dropped": (
            "input_lc=$(printf '%s' \"$INPUT_LABEL\" | tr '[:upper:]' '[:lower:]')",
            'input_lc="$INPUT_LABEL"',
        ),
        "bump-branch bypass dropped": ('[ "$HEAD_REF" = "$BUMP_BRANCH" ]', "false"),
        # The hardcoded-spelling assertion is a NEGATIVE one, so it needs a
        # mutation that introduces the thing it forbids -- otherwise it passes
        # today and would pass just as well if it checked nothing.
        "competing hardcoded label added": (
            'if [ "$label_lc" = "$input_lc" ]; then',
            'if [ "$label_lc" = "$input_lc" ] || [ "$label_lc" = "no version increment" ]; then',
        ),
        "set -e dropped": ("          set -euo pipefail\n", ""),
        "read moved into a condition": (
            'labels=$(gh api --paginate \\',
            'if labels=$(gh api --paginate \\',
        ),
    }

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for label, (old, new) in mutations.items():
            if old not in base:
                print(f"::error::self-test '{label}': anchor not found, so the "
                      "mutation would pass vacuously", file=sys.stderr)
                failures += 1
                continue
            path = pathlib.Path(tmp) / "mutated.yml"
            path.write_text(base.replace(old, new, 1), encoding="utf-8")
            if check(path) == 0:
                print(f"::error::self-test '{label}': mutation was NOT caught",
                      file=sys.stderr)
                failures += 1
            else:
                print(f"OK   self-test '{label}' is caught")

    if failures:
        print(f"::error::{failures} self-test case(s) failed", file=sys.stderr)
        return 1
    print("All version-check workflow self-tests passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=pathlib.Path, default=DEFAULT_WORKFLOW)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    return check(args.workflow)


if __name__ == "__main__":
    raise SystemExit(main())
