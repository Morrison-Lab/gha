#!/usr/bin/env python3
"""Pin claude.yml's cheap mention-filter job (gha#554).

gha#342 already stripped markup *inside* the agent job, so a quoted mention
no longer billed an agent run. What it left was the job-level `if:` testing
the raw body -- a GitHub expression cannot strip Markdown -- so a runner
still spun up, checked out, and stood down. Direction 2 of #554 moves that
decision to a cheap first job that reuses detect-bot-mention and gates the
agent job on `proceed`.

A wiring typo here is silent in the other direction from most bugs in this
file: dropping the gate, or widening `proceed == 'true'` to `!= 'false'`,
starts the expensive job for a quoted mention or an untrusted commenter.
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
        "(a skipped filter job would then start the agent for an untrusted commenter)",
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
        uses = step_uses(filt_mention[0])
        check(
            uses.endswith("@v2") or uses.startswith("./"),
            f"detect-bot-mention is referenced at @v2 or a local path (found: {uses})",
        )
        check(
            filt_mention[0].get("continue-on-error") is True,
            "detect-bot-mention fail-opens (continue-on-error: true, gha#343)",
        )
        # Empty bodies still print `false` (detect-bot-mention.sh counts them),
        # so this `if:` is what leaves match empty on dispatch/schedule --
        # not the proceed `else`. Deleting it silently kills unattended runs.
        # Split on || so pull_request_review is not a prefix of
        # pull_request_review_comment.
        detect_if = str(filt_mention[0].get("if") or "")
        detect_clauses = {c.strip() for c in detect_if.split("||")}
        for event in (
            "issue_comment",
            "pull_request_review_comment",
            "pull_request_review",
            "issues",
        ):
            check(
                f"github.event_name == '{event}'" in detect_clauses,
                f"detect-bot-mention runs on {event}",
            )
        check(
            not any("workflow_dispatch" in c or "schedule" in c for c in detect_clauses),
            "detect-bot-mention does not run on workflow_dispatch/schedule "
            "(four empty bodies would print false and withhold the agent)",
        )
        with_block = filt_mention[0].get("with") or {}
        for field in ("issue-body", "issue-title"):
            value = str(with_block.get(field) or "")
            check(
                "github.event_name == 'issues'" in value,
                f"{field} is scoped to the issues event (gha#343: an enclosing "
                "issue title must not keep a later quoted comment matching)",
            )

    agent_mention = [s for s in agent_steps if "detect-bot-mention" in step_uses(s)]
    check(
        not agent_mention,
        "the agent job does not re-run detect-bot-mention "
        "(quoted mentions must never start this job, so the decision cannot live here)",
    )

    filt_if = str(filt.get("if") or "")
    check(
        "github.event.action == 'assigned'" in filt_if
        and "inputs.dispatch-on-assignee" in filt_if,
        "mention-filter's if: still admits an allowlisted assignment with no mention",
    )
    check(
        "contains(github.event.issue.body, '@claude')" in filt_if,
        "mention-filter's if: still requires a raw mention on issues.opened "
        "(assignment is the other clause, not a replacement)",
    )
    check(
        "workflow_dispatch" in filt_if and "schedule" in filt_if,
        "mention-filter's if: still admits workflow_dispatch/schedule "
        "(gha#245; a skipped filter leaves proceed empty and the agent never starts)",
    )
    check(
        "author_association" in filt_if
        and "OWNER" in filt_if
        and "MEMBER" in filt_if
        and "COLLABORATOR" in filt_if,
        "mention-filter's if: still carries the trusted-author association gate "
        "(the agent job's only if: is proceed==true, so this is the real gate)",
    )
    check(
        "trusted-bot-logins" in filt_if,
        "mention-filter's if: still honours trusted-bot-logins",
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
