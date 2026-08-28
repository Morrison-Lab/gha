#!/usr/bin/env python3
"""Pin claude.yml's cheap mention-filter job (gha#554).

gha#342 already stripped markup *inside* the agent job, so a quoted mention
no longer billed the expensive agent job (model invocation, R/Quarto setup).
What it left was the job-level `if:` testing the raw body -- a GitHub
expression cannot strip Markdown -- so a filter runner still spun up and
stood down (hosted-runner minute, dedup API call, agent concurrency slot).
Direction 2 of #554 moves that decision to a cheap first job that reuses
detect-bot-mention and gates the agent job on `proceed`. The filter runner
minute is still billed; the avoided cost is the `claude` job.

A wiring typo here is silent in the other direction from most bugs in this
file: dropping the gate, or combining `always()` with `!= 'false'`,
starts the expensive job for an untrusted commenter. Widening
`proceed == 'true'` to `!= 'false'` alone still withholds a quoted
mention (`proceed=false`) and still skips when the filter job is skipped;
it fail-opens when the filter job succeeds but proceed writes nothing.
The agent job is not something `_selftest.yml` can invoke, so this suite
reads the workflow YAML and executes the proceed script against a table.

Usage::

    python3 run-mention-filter-tests.py [--workflow PATH]
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile

FAILURES: list[str] = []

DEFAULT_WORKFLOW = ".github/workflows/claude.yml"

# Pin the exact expressions, not substrings. Appending `|| true` to either
# `if:` still contains every required fragment, so a substring pin stays
# green while dispatch/schedule runs detection on four empty bodies
# (prints `false`; unattended runs die) or the trusted-author gate is
# bypassed. Measured 2026-08-26 against this file's own mutations.
EXPECTED_FILTER_JOB_IF = (
    "(github.event_name == 'issue_comment' && "
    "contains(github.event.comment.body, '@claude') && "
    "(contains(fromJSON('[\"OWNER\",\"MEMBER\",\"COLLABORATOR\"]'), "
    "github.event.comment.author_association) || "
    "contains(fromJSON(inputs.trusted-bot-logins), "
    "github.event.comment.user.login))) ||\n"
    "(github.event_name == 'pull_request_review_comment' && "
    "contains(github.event.comment.body, '@claude') && "
    "(contains(fromJSON('[\"OWNER\",\"MEMBER\",\"COLLABORATOR\"]'), "
    "github.event.comment.author_association) || "
    "contains(fromJSON(inputs.trusted-bot-logins), "
    "github.event.comment.user.login))) ||\n"
    "(github.event_name == 'pull_request_review' && "
    "contains(github.event.review.body, '@claude') && "
    "(contains(fromJSON('[\"OWNER\",\"MEMBER\",\"COLLABORATOR\"]'), "
    "github.event.review.author_association) || "
    "contains(fromJSON(inputs.trusted-bot-logins), "
    "github.event.review.user.login))) ||\n"
    "(github.event_name == 'issues' && "
    "(contains(github.event.issue.body, '@claude') || "
    "contains(github.event.issue.title, '@claude')) && "
    "(contains(fromJSON('[\"OWNER\",\"MEMBER\",\"COLLABORATOR\"]'), "
    "github.event.issue.author_association) || "
    "contains(fromJSON(inputs.trusted-bot-logins), "
    "github.event.issue.user.login))) ||\n"
    "(github.event_name == 'issues' && github.event.action == 'assigned' && "
    "contains(fromJSON(inputs.dispatch-on-assignee), "
    "github.event.assignee.login)) ||\n"
    "github.event_name == 'workflow_dispatch' ||\n"
    "github.event_name == 'schedule'\n"
)

EXPECTED_DETECT_USES = (
    "Morrison-Lab/gha/.github/actions/detect-bot-mention@v2"
)

EXPECTED_FILTER_PERMISSIONS = {"contents": "read"}

EXPECTED_DETECT_STEP_IF = (
    "github.event_name == 'issue_comment' || "
    "github.event_name == 'pull_request_review_comment' || "
    "github.event_name == 'pull_request_review' || "
    "github.event_name == 'issues'"
)

EXPECTED_DETECT_WITH = {
    "comment-body": "${{ github.event.comment.body }}",
    "review-body": "${{ github.event.review.body }}",
    "issue-body": (
        "${{ github.event_name == 'issues' && "
        "github.event.issue.body || '' }}"
    ),
    "issue-title": (
        "${{ github.event_name == 'issues' && "
        "github.event.issue.title || '' }}"
    ),
}

EXPECTED_PROCEED_ENV = {
    "MENTION_MATCH": "${{ steps.mention.outputs.match }}",
    "ASSIGNMENT_TRIGGER": (
        "${{ github.event_name == 'issues' && "
        "github.event.action == 'assigned' && "
        "contains(fromJSON(inputs.dispatch-on-assignee), "
        "github.event.assignee.login) }}"
    ),
}

# (assignment_trigger, mention_match, expected_proceed, why)
# mention_match "" is the empty-output case: the detect step did not run
# (workflow_dispatch/schedule) or failed open (gha#343).
PROCEED_CASES = [
    ("false", "true", "true", "a real mention dispatches the agent job"),
    ("false", "false", "false", "a quoted / code-span / fence mention does not"),
    ("true", "false", "true", "assignment still dispatches with no mention"),
    ("true", "true", "true", "assignment plus a real mention still dispatches"),
    ("true", "", "true", "assignment with an empty mention result still dispatches"),
    ("false", "", "true", "empty mention result fail-opens (dispatch/schedule / stripper failure)"),
]


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"OK   {message}")
    else:
        print(f"::error::{message}", file=sys.stderr)
        FAILURES.append(message)


def needs_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def step_uses(step: dict) -> str:
    return str(step.get("uses") or "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    args = parser.parse_args()

    try:
        import yaml
    except ImportError:  # pragma: no cover - depends on the runner image
        print(
            "::error::PyYAML is required to parse the workflow "
            "(install it with `python3 -m pip install pyyaml`).",
            file=sys.stderr,
        )
        return 2

    path = pathlib.Path(args.workflow)
    if not path.is_file():
        print(f"::error::{path}: no such file", file=sys.stderr)
        return 2

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = doc["jobs"]

    check("mention-filter" in jobs, "claude.yml declares a mention-filter job")
    check("claude" in jobs, "claude.yml still declares the agent job")
    if "mention-filter" not in jobs or "claude" not in jobs:
        print(f"::error::{len(FAILURES)} mention-filter assertion(s) failed", file=sys.stderr)
        return 1

    filt = jobs["mention-filter"]
    agent = jobs["claude"]

    check(
        "mention-filter" in needs_list(agent.get("needs")),
        "the agent job needs mention-filter",
    )

    agent_if = str(agent.get("if") or "").strip()
    check(
        agent_if == "needs.mention-filter.outputs.proceed == 'true'",
        "the agent job starts only when mention-filter.proceed is exactly true "
        f"(found: {agent_if!r})",
    )
    check(
        "!= 'false'" not in agent_if,
        "the agent job does not treat an empty proceed output as go "
        "(`!= 'false'` fail-opens a successful filter that wrote nothing)",
    )

    check(
        filt.get("permissions") == EXPECTED_FILTER_PERMISSIONS,
        "mention-filter permissions are contents: read "
        "(an omitted block inherits the caller's write-scoped GITHUB_TOKEN)",
    )
    check(
        filt.get("runs-on") == "ubuntu-latest",
        "mention-filter uses ubuntu-latest, not inputs.runs-on "
        f"(found: {filt.get('runs-on')!r})",
    )
    timeout = filt.get("timeout-minutes")
    check(
        isinstance(timeout, int) and timeout <= 10,
        f"mention-filter timeout is small (found: {timeout!r})",
    )
    check(
        "concurrency" not in filt,
        "mention-filter has no concurrency group "
        "(a quoted mention must not queue behind an active agent run)",
    )
    check(
        "concurrency" in agent,
        "the agent job still serializes per issue/PR",
    )

    filt_steps = filt.get("steps") or []
    agent_steps = agent.get("steps") or []

    checkout = [
        s.get("name") or step_uses(s)
        for s in filt_steps
        if "actions/checkout" in step_uses(s)
    ]
    check(not checkout, "mention-filter does not check out the caller " + (f"(found: {checkout})" if checkout else ""))

    filt_mention = [s for s in filt_steps if "detect-bot-mention" in step_uses(s)]
    check(
        len(filt_mention) == 1,
        "mention-filter calls detect-bot-mention exactly once "
        f"(found: {len(filt_mention)})",
    )
    if filt_mention:
        check(
            filt_mention[0].get("id") == "mention",
            "detect step id is `mention` "
            "(proceed env reads steps.mention.outputs.match; a rename "
            "fail-opens quoted mentions)",
        )
        check(
            step_uses(filt_mention[0]) == EXPECTED_DETECT_USES,
            "detect-bot-mention uses the exact @v2 ref "
            "(a relative ./ path inside a reusable workflow resolves "
            "against the caller checkout, gha#284)",
        )
        check(
            filt_mention[0].get("continue-on-error") is True,
            "detect-bot-mention fail-opens (continue-on-error: true, gha#343)",
        )
        # Empty bodies still print `false` (detect-bot-mention.sh counts them),
        # so this `if:` is what leaves match empty on dispatch/schedule --
        # not the proceed `else`. Deleting it silently kills unattended runs.
        # Compare the normalized exact expression, not a substring: appending
        # `|| true` still contains every event clause and stays green under a
        # fragment pin, then runs detection on dispatch/schedule.
        check(
            filt_mention[0].get("if") == EXPECTED_DETECT_STEP_IF,
            "detect-bot-mention `if:` is the exact four-event expression "
            "(substring pins miss `|| true`)",
        )
        check(
            (filt_mention[0].get("with") or {}) == EXPECTED_DETECT_WITH,
            "detect-bot-mention `with:` maps each body input to its event field",
        )

    agent_mention = [s for s in agent_steps if "detect-bot-mention" in step_uses(s)]
    check(
        not agent_mention,
        "the agent job does not re-run detect-bot-mention "
        "(quoted mentions must never start this job, so the decision cannot live here)",
    )

    check(
        filt.get("if") == EXPECTED_FILTER_JOB_IF,
        "mention-filter's if: is the exact trusted-author expression "
        "(substring pins miss `|| true` bypasses of the association gate)",
    )

    proceed_out = str((filt.get("outputs") or {}).get("proceed") or "")
    check(
        "steps.proceed.outputs.proceed" in proceed_out,
        "mention-filter.outputs.proceed reads the proceed step, not detect-bot-mention's match "
        f"(found: {proceed_out!r})",
    )
    check(
        "steps.mention.outputs.match" not in proceed_out,
        "mention-filter.outputs.proceed is not wired to match "
        "(that would kill assignment-without-mention, gha#552)",
    )

    proceed_steps = [s for s in filt_steps if s.get("id") == "proceed"]
    check(len(proceed_steps) == 1, "mention-filter has a proceed step")
    if not proceed_steps:
        print(f"::error::{len(FAILURES)} mention-filter assertion(s) failed", file=sys.stderr)
        return 1

    script = proceed_steps[0].get("run") or ""
    check(bool(script.strip()), "the proceed step has a run: script")
    check(
        "if" not in proceed_steps[0],
        "the proceed step has no `if:` "
        "(a match-nonempty or outcome==success gate skips the script on "
        "dispatch/schedule and fail-closes unattended runs)",
    )
    check(
        (proceed_steps[0].get("env") or {}) == EXPECTED_PROCEED_ENV,
        "proceed step env maps MENTION_MATCH and ASSIGNMENT_TRIGGER "
        "to the detect output and the assignment expression",
    )
    check(
        "ASSIGNMENT_TRIGGER" in script,
        "the proceed script keeps the #552 assignment exemption",
    )
    check(
        '[ "$MENTION_MATCH" = "false" ]' in script,
        "the proceed script withholds on an explicit match=false",
    )

    # Execute the script from the YAML, not a copy. A rewritten proceed step
    # that drops the assignment exemption or fail-opens the wrong way must
    # turn this table red.
    print("\nProceed-script table (extracted from mention-filter):\n")
    for assignment, match, want, why in PROCEED_CASES:
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "github_output"
            out.write_text("", encoding="utf-8")
            env = os.environ.copy()
            env["ASSIGNMENT_TRIGGER"] = assignment
            env["MENTION_MATCH"] = match
            env["GITHUB_OUTPUT"] = str(out)
            result = subprocess.run(
                ["bash", "-s"],
                input=script,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            got = ""
            for line in out.read_text(encoding="utf-8").splitlines():
                if line.startswith("proceed="):
                    got = line.split("=", 1)[1]
            ok = result.returncode == 0 and got == want
            check(
                ok,
                f"assignment={assignment!r} match={match!r} -> proceed={want!r} "
                f"({why})"
                + (
                    f" [exit {result.returncode}, got {got!r}, stderr={result.stderr!r}]"
                    if not ok
                    else ""
                ),
            )

    print()
    if FAILURES:
        print(f"::error::{len(FAILURES)} mention-filter assertion(s) failed", file=sys.stderr)
        return 1
    print("All mention-filter assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
