#!/usr/bin/env python3
"""Pin the reviewer's tool grant in `run-claude-review-attempt/action.yml`.

gha#566 and gha#572 widened `Bash` from a handful of named commands to the
whole tool, because naming commands one at a time kept starving real reviews
(five measured runs, no verdict, tens of dollars). That widening moved the deny
list from belt-and-braces to load-bearing: before it, `gh pr merge` was
unreachable because it was simply not on the allowlist; after it, only an
explicit denial keeps it unreachable.

Nothing else would notice that going away. A future edit trimming the deny list
"because the allowlist is narrow anyway" would silently hand a review job with
`pull-requests: write` the ability to merge the PR it is reviewing, and no
check would turn red. This suite is that check.

**What it does not do.** It asserts the declared lists, not the behaviour of
Claude Code's permission matcher. Simulating that matcher here would be
testing a model of the system rather than the system -- the fixture trap -- so
every assertion below is about a rule this repo controls and can be read
straight out of the file.

Usage::

    python3 run-reviewer-allowlist-tests.py [--action PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

DEFAULT_ACTION = ".github/actions/run-claude-review-attempt/action.yml"

# Capabilities that were unreachable before the gha#566/gha#572 widening
# (absent from a narrow allowlist) and that must stay unreachable after it
# (present in the deny list). Each entry is the deny rule that must exist,
# beside what it prevents -- the reviewer holds `pull-requests: write` and
# `issues: write`, so these are the forge mutations an accident could reach.
REQUIRED_DENIALS = {
    "Bash(git add:*)": "stage changes in the checkout under review",
    "Bash(git commit:*)": "commit to the branch under review",
    "Bash(git rm:*)": "delete tracked files",
    "Bash(git push:*)": "push to the branch under review",
    "Bash(gh pr comment:*)": "post a duplicate top-level review comment",
    "Bash(gh pr merge:*)": "merge the pull request it is reviewing",
    "Bash(gh pr close:*)": "close the pull request",
    "Bash(gh pr edit:*)": "rewrite the PR title, body, or labels",
    "Bash(gh pr review:*)": "submit a formal approving or blocking review",
    "Bash(gh pr create:*)": "open a pull request",
    "Bash(gh issue comment:*)": "comment on an issue",
    "Bash(gh issue close:*)": "close an issue",
    "Bash(gh issue edit:*)": "rewrite an issue",
    "Bash(gh api:*)": "reach any mutation the subcommand denials above cover",
    "Bash(gh workflow run:*)": "dispatch a workflow",
    "Bash(gh secret:*)": "read or write repository secrets",
    # Not forge mutations, but the same load-bearing-after-widening argument:
    # these have no synchronous form in a one-shot CI run (gha#392, gha#532).
    "ScheduleWakeup": "end the turn waiting for a wakeup that never fires",
    "SendMessage": "message an agent that does not exist in a headless run",
    "Monitor": "stream a background process past the end of the run",
    "Agent(run_in_background:true)": "spawn a background agent and stall",
    "Task(run_in_background:true)": "the same, under the Task alias",
}

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"OK   {message}")
    else:
        print(f"::error::{message}", file=sys.stderr)
        FAILURES.append(message)


def tool_list(claude_args: str, flag: str) -> list[str]:
    match = re.search(re.escape(flag) + r'\s+"([^"]*)"', claude_args)
    if not match:
        print(f"::error::{flag} not found in claude_args", file=sys.stderr)
        sys.exit(1)
    return [t.strip() for t in match.group(1).split(",") if t.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", default=DEFAULT_ACTION)
    args = parser.parse_args()

    import yaml

    path = pathlib.Path(args.action)
    if not path.is_file():
        print(f"::error::{path}: no such file", file=sys.stderr)
        return 2

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    steps = doc["runs"]["steps"]
    claude_args = next(s["with"]["claude_args"] for s in steps if "claude_args" in s.get("with", {}))

    allowed = tool_list(claude_args, "--allowedTools")
    denied = tool_list(claude_args, "--disallowedTools")

    print(f"Checking {path} ({len(allowed)} allowed, {len(denied)} denied)\n")

    # 1. Bash is granted whole. The bare form is the documented spelling for
    #    "all invocations"; `Bash(*)` is equivalent and also acceptable.
    check(
        "Bash" in allowed or "Bash(*)" in allowed,
        "Bash is granted whole (gha#566/gha#572)",
    )

    # 2. No leftover per-command Bash allow entries. Under a blanket grant they
    #    are dead weight that reads as though the grant were still narrow,
    #    which is the misreading gha#566 was filed about.
    leftovers = [t for t in allowed if t.startswith("Bash(")]
    check(
        not leftovers,
        "no redundant per-command Bash allow entries remain"
        + (f" (found: {', '.join(leftovers)})" if leftovers else ""),
    )

    # 3. Every capability the narrow allowlist used to make unreachable is now
    #    explicitly denied. This is the assertion the whole file exists for.
    for rule, consequence in sorted(REQUIRED_DENIALS.items()):
        check(rule in denied, f"denied: {rule}  (else the reviewer could {consequence})")

    # 4. Write is granted, and only under a scratch prefix -- the checkout
    #    under review must stay untouched, since this is a review-only run.
    writes = [t for t in allowed if t == "Write" or t.startswith("Write(")]
    check(bool(writes), "Write is granted for scratch files (gha#572)")
    check(
        "Write" not in allowed,
        "Write is not granted unscoped (it would reach the checkout)",
    )
    check(
        all(w.startswith("Write(//tmp/") for w in writes),
        f"every Write grant is scoped under /tmp (found: {', '.join(writes) or 'none'})",
    )

    # 5. Parameter-scoped rules are valid in deny/ask rules only, never in an
    #    allow rule -- an allow rule for one parameter would not establish the
    #    call is safe overall, so Claude Code does not accept the form there.
    param_allows = [t for t in allowed if re.search(r"\([a-z_]+:[^*]", t)]
    check(
        not param_allows,
        "no parameter-scoped rules in the allow list"
        + (f" (found: {', '.join(param_allows)})" if param_allows else ""),
    )

    print()
    if FAILURES:
        print(f"::error::{len(FAILURES)} reviewer-allowlist assertion(s) failed", file=sys.stderr)
        return 1
    print("All reviewer-allowlist assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
