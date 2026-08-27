#!/usr/bin/env python3
"""Pin the reviewer's tool grant in `run-claude-review-attempt/action.yml`.

gha#566 and gha#572 widened `Bash` from a handful of named commands to the
whole tool, because naming commands one at a time kept starving real reviews
(five measured runs, no verdict, tens of dollars). After that widening, a
prefix deny list cannot be a security boundary: wrapping a denied command,
or writing through a redirect, both go around it (gha#580). The close is
architectural -- the model job holds `contents: read` and the posting job
holds forge-write, so they never coincide. This suite still pins the deny
list as a *guard rail* against accidents. Nothing else would notice a
future edit trimming it "because the allowlist is narrow anyway" or
"because the job is read-only"; both misreadings would silently drop
rules that still stop a confused model from *trying* a merge.

**What it does not do.** It asserts the declared lists, not the behaviour of
Claude Code's permission matcher, and it is not the credential split --
that is `run-review-job-split-tests.py`. Simulating the matcher here would
be testing a model of the system rather than the system -- the fixture
trap -- so every assertion below is about a rule this repo controls and
can be read straight out of the file.

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
# (absent from a narrow allowlist) and that must stay denied as a guard
# rail after it. Each entry is the deny rule that must exist, beside what
# an accident could still *attempt* -- gha#580 moved forge-write off the
# model job, so these no longer succeed, but a confused model retrying
# them still wastes the run.
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
    "Bash(gh pr ready:*)": "flip a draft to ready for review",
    "Bash(gh pr reopen:*)": "reopen a closed pull request",
    "Bash(gh pr lock:*)": "lock the PR conversation",
    "Bash(gh pr unlock:*)": "unlock a deliberately locked conversation",
    "Bash(gh pr update-branch:*)": "push a merge onto the branch under review",
    "Bash(gh pr revert:*)": "open a revert of the change under review",
    "Bash(gh issue create:*)": "file an issue",
    "Bash(gh issue reopen:*)": "reopen a closed issue",
    "Bash(gh issue delete:*)": "delete an issue outright",
    "Bash(gh issue develop:*)": "create a branch attached to an issue",
    "Bash(gh issue lock:*)": "lock an issue conversation",
    "Bash(gh issue unlock:*)": "unlock a deliberately locked issue",
    "Bash(gh issue pin:*)": "pin an issue to the repository",
    "Bash(gh issue unpin:*)": "unpin a pinned issue",
    "Bash(gh issue transfer:*)": "move an issue to another repository",
    "Bash(gh api:*)": "reach any mutation the subcommand denials above cover",
    "Bash(gh workflow run:*)": "dispatch a workflow",
    "Bash(gh run cancel:*)": "cancel a running workflow, including its own",
    "Bash(gh run rerun:*)": "re-run a workflow and spend the budget again",
    "Bash(gh release:*)": "create, edit, or delete a release",
    "Bash(gh label:*)": "create, rename, or delete repository labels",
    "Bash(gh cache delete:*)": "evict the Actions cache",
    "Bash(gh repo edit:*)": "change repository settings",
    "Bash(gh repo delete:*)": "delete the repository",
    "Bash(gh variable:*)": "read or write repository variables",
    "Bash(gh secret:*)": "list secret metadata, or set and delete secrets",
    "Bash(*git-push.sh*)": "push through the action's own push wrapper",
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

    # Guarded, matching run-permissions-docs-tests.py. PyYAML ships
    # preinstalled on the GitHub-hosted Ubuntu image and this step runs under
    # the runner's system python3 with no setup-python, so it is present in
    # practice -- unlike lint-yaml, which installs it because setup-python
    # gives that job a fresh interpreter. The guard is so that a runner image
    # which ever drops it names the fix instead of raising ImportError.
    try:
        import yaml
    except ImportError:  # pragma: no cover - depends on the runner image
        print(
            "::error::PyYAML is required to parse the action manifest "
            "(install it with `python3 -m pip install pyyaml`).",
            file=sys.stderr,
        )
        return 2

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
    leftovers = [t for t in allowed if t.startswith("Bash(") and t != "Bash(*)"]
    check(
        not leftovers,
        "no redundant per-command Bash allow entries remain"
        + (f" (found: {', '.join(leftovers)})" if leftovers else ""),
    )

    # 3. The deny set must match EXACTLY. Asserting only that each required
    #    rule is present leaves every other production rule unpinned -- the
    #    cross-vendor review of #578 found that dropping `gh pr ready`,
    #    `gh release`, `gh label` and a dozen others left this suite green,
    #    which is precisely the load-bearing coverage it claims to provide.
    #    Equality also forces a deliberate edit here when a rule is added, so
    #    the table below stays an inventory rather than drifting into a
    #    sample.
    missing = sorted(set(REQUIRED_DENIALS) - set(denied))
    unexpected = sorted(set(denied) - set(REQUIRED_DENIALS))
    for rule in missing:
        check(False, f"denied rule missing: {rule}  (else the reviewer could {REQUIRED_DENIALS[rule]})")
    for rule in unexpected:
        check(
            False,
            f"deny rule not accounted for here: {rule} -- add it to REQUIRED_DENIALS "
            "with the consequence it prevents, so the inventory stays complete",
        )
    if not missing and not unexpected:
        check(True, f"the deny list matches its inventory exactly ({len(denied)} rules)")

    # 4. The scratch-write grant must be spelled `Edit(//tmp/**)`.
    #    Two independent ways to get this wrong, and each produces a rule that
    #    is accepted and then never consulted -- which reads as a working grant
    #    in the config, so nothing surfaces the mistake. The docs say Claude
    #    Code "checks file permissions against Edit(path) and Read(path) rules
    #    only", so a `Write(...)` path rule is inert; and `//` is the absolute
    #    form, where a single leading `/` anchors at the project instead.
    #    This shipped as `Write(//tmp/**)` and a reviewer caught it.
    inert = [t for t in allowed if re.match(r"(Write|MultiEdit|NotebookEdit|Glob)\(", t)]
    check(
        not inert,
        "no path rule uses a tool name Claude Code never consults"
        + (f" (found: {', '.join(inert)}; use Edit(...) or Read(...))" if inert else ""),
    )

    edits = [t for t in allowed if t == "Edit" or t.startswith("Edit(")]
    check(bool(edits), "a scratch-write grant is present (gha#572)")
    check("Edit" not in allowed, "Edit is not granted unscoped (it would reach the checkout)")
    check(
        all(e.startswith("Edit(//tmp/") for e in edits),
        f"every scratch-write grant is scoped under /tmp (found: {', '.join(edits) or 'none'})",
    )

    # 5. Parameter-scoped rules are valid in deny/ask rules only, never in an
    #    allow rule -- an allow rule for one parameter would not establish the
    #    call is safe overall, so Claude Code does not accept the form there.
    # `WebFetch(domain:...)` is WebFetch's OWN specifier syntax, not a
    # parameter rule, and the docs say allow rules "continue to use each
    # tool's own specifier syntax" -- so it must not be flagged here.
    param_allows = [
        t
        for t in allowed
        if re.search(r"\([a-z_]+:[^*]", t) and not t.startswith("WebFetch(")
    ]
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
