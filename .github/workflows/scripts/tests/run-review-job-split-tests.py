#!/usr/bin/env python3
"""Pin the gha#580 credential split in claude-code-review.yml.

The model and a writable forge token must not share a job. A prefix deny
list cannot be a security boundary once Bash is granted whole (gha#580,
raised from a review of #578): wrapping a denied command, or writing
through a redirect, both go around it. The close is architectural.

This suite reads the workflow YAML and the attempt composite, and asserts
the facts a future edit could reverse silently:

1. The model job (`claude-review`) grants no forge-write permission.
   `id-token: write` is the documented exception (OIDC for Anthropic /
   the App-token exchange we now skip).
2. The posting job (`post-review`) holds `pull-requests: write` and
   `issues: write`, and does not invoke the model.
3. The attempt composite forwards `github_token` to claude-code-action,
   which is how the App-token exchange (default contents/PRs/issues
   write, measured in anthropics/claude-code-action v1.0.196
   `src/github/token.ts` DEFAULT_PERMISSIONS, 2026-08-26) is skipped.
4. The inline-comment MCP tool is not in the model job's allowlist,
   because it posts during the model turn.

PyYAML is required, same as run-reviewer-allowlist-tests.py.

Usage::

    python3 run-review-job-split-tests.py
    python3 run-review-job-split-tests.py --self-test
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

DEFAULT_WORKFLOW = ".github/workflows/claude-code-review.yml"
DEFAULT_ACTION = ".github/actions/run-claude-review-attempt/action.yml"

# Permissions that would let the model mutate the forge or the checkout.
# `id-token: write` is not one of them: it mints an OIDC JWT for Anthropic,
# not a GitHub write token.
FORGE_WRITE = {
    "contents": "write",
    "pull-requests": "write",
    "issues": "write",
    "actions": "write",
    "workflows": "write",
}

INLINE_TOOL = "mcp__github_inline_comment__create_inline_comment"


def die(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


def load_yaml(path: pathlib.Path):
    try:
        import yaml
    except ImportError:  # pragma: no cover - depends on the runner image
        die(
            "PyYAML is required to parse the workflow "
            "(install it with `python3 -m pip install pyyaml`)."
        )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"OK   {message}")
    else:
        print(f"::error::{message}", file=sys.stderr)
        FAILURES.append(message)


def job_permissions(job: dict) -> dict:
    perms = job.get("permissions")
    if perms is None:
        return {}
    if perms == "read-all":
        return {"contents": "read"}
    if perms == "write-all":
        return {"contents": "write"}
    if isinstance(perms, dict):
        return perms
    die(f"unrecognised permissions value: {perms!r}")
    return {}


def uses_of(job: dict) -> list[str]:
    uses = []
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        u = step.get("uses")
        if isinstance(u, str):
            uses.append(u)
    return uses


def check_workflow(workflow_path: pathlib.Path, action_path: pathlib.Path) -> int:
    doc = load_yaml(workflow_path)
    jobs = doc.get("jobs") or {}
    if "claude-review" not in jobs:
        die(f"{workflow_path}: no claude-review job")
    if "post-review" not in jobs:
        die(f"{workflow_path}: no post-review job")

    review = jobs["claude-review"]
    post = jobs["post-review"]
    review_perms = job_permissions(review)
    post_perms = job_permissions(post)

    print(f"Checking {workflow_path} and {action_path}\n")

    for key, val in FORGE_WRITE.items():
        check(
            review_perms.get(key) != val,
            f"claude-review does not grant {key}: {val}",
        )

    check(
        review_perms.get("contents") == "read",
        "claude-review grants contents: read",
    )
    check(
        review_perms.get("id-token") == "write",
        "claude-review keeps id-token: write (gha#580)",
    )
    check(
        post_perms.get("pull-requests") == "write",
        "post-review holds pull-requests: write",
    )
    check(
        post_perms.get("issues") == "write",
        "post-review holds issues: write",
    )
    check(
        post_perms.get("id-token") != "write",
        "post-review does not need id-token: write",
    )

    review_uses = uses_of(review)
    post_uses = uses_of(post)
    check(
        any("run-claude-review-attempt" in u for u in review_uses),
        "claude-review invokes run-claude-review-attempt (the model)",
    )
    check(
        not any("run-claude-review-attempt" in u for u in post_uses),
        "post-review does not invoke run-claude-review-attempt",
    )
    check(
        not any("anthropics/claude-code-action" in u for u in post_uses),
        "post-review does not invoke claude-code-action",
    )
    check(
        any("pack-review-payload" in u for u in review_uses),
        "claude-review packs a payload artifact for the posting job",
    )
    check(
        any("download-artifact" in u for u in post_uses),
        "post-review downloads the payload artifact",
    )

    needs = post.get("needs")
    if isinstance(needs, str):
        needs = [needs]
    check(
        isinstance(needs, list) and "claude-review" in needs,
        "post-review needs claude-review",
    )

    on = doc.get(True, doc.get("on")) or {}
    check(
        "pull_request_target" not in on,
        "the reusable workflow is pull_request_target-free (gha#235 already refuses forks)",
    )

    action = load_yaml(action_path)
    steps = action.get("runs", {}).get("steps") or []
    claude_step = next(
        (s for s in steps if isinstance(s, dict) and "claude_args" in s.get("with", {})),
        None,
    )
    if claude_step is None:
        die(f"{action_path}: no step with claude_args")
    with_block = claude_step["with"]
    check(
        "github_token" in with_block,
        "run-claude-review-attempt forwards github_token (skips the App-token write exchange)",
    )
    check(
        with_block.get("classify_inline_comments") == "false",
        "classify_inline_comments is false so the action does not post from the model job",
    )
    claude_args = with_block["claude_args"]
    match = re.search(r'--allowedTools\s+"([^"]*)"', claude_args)
    if not match:
        die(" --allowedTools not found in claude_args")
    allowed = [t.strip() for t in match.group(1).split(",") if t.strip()]
    check(
        INLINE_TOOL not in allowed,
        "the inline-comment MCP tool is not allowlisted on the model job",
    )

    if FAILURES:
        print(
            f"::error::{len(FAILURES)} review-job-split assertion(s) failed",
            file=sys.stderr,
        )
        return 1
    print("\nAll review-job-split assertions passed.")
    return 0


def run_self_test() -> int:
    script = pathlib.Path(__file__).resolve()

    def run(workflow: pathlib.Path, action: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(script),
                "--workflow",
                str(workflow),
                "--action",
                str(action),
            ],
            capture_output=True,
            text=True,
        )

    def expect(label: str, result: subprocess.CompletedProcess[str], should_pass: bool, needle: str | None = None) -> int:
        passed = result.returncode == 0
        if passed != should_pass:
            print(
                f"::error::{label}: expected {'pass' if should_pass else 'failure'}, "
                f"got exit {result.returncode}\n{result.stdout}{result.stderr}",
                file=sys.stderr,
            )
            return 1
        blob = result.stdout + result.stderr
        if needle and needle not in blob:
            print(
                f"::error::{label}: expected output to mention {needle!r}\n{blob}",
                file=sys.stderr,
            )
            return 1
        print(f"OK   {label}")
        return 0

    print("Running run-review-job-split-tests offline unit tests...")
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        good_wf = root / "good.yml"
        good_wf.write_text(
            """
on:
  workflow_call: {}
jobs:
  claude-review:
    permissions:
      contents: read
      pull-requests: read
      issues: read
      id-token: write
      actions: read
    steps:
      - uses: Morrison-Lab/gha/.github/actions/run-claude-review-attempt@v2
      - uses: Morrison-Lab/gha/.github/actions/pack-review-payload@v2
  post-review:
    needs: claude-review
    permissions:
      pull-requests: write
      issues: write
    steps:
      - uses: actions/download-artifact@v4
"""
        )
        good_action = root / "action.yml"
        good_action.write_text(
            """
runs:
  using: composite
  steps:
    - uses: anthropics/claude-code-action@main
      with:
        github_token: ${{ inputs.github-token }}
        classify_inline_comments: 'false'
        claude_args: >-
          --allowedTools
          "Bash,Edit(//tmp/**),WebFetch,WebSearch"
"""
        )
        failures += expect("good split passes", run(good_wf, good_action), True)

        bad_write = root / "bad-write.yml"
        bad_write.write_text(
            good_wf.read_text().replace(
                "      pull-requests: read\n",
                "      pull-requests: write\n",
                1,
            )
        )
        failures += expect(
            "write on the model job fails",
            run(bad_write, good_action),
            False,
            "claude-review does not grant pull-requests: write",
        )

        no_token = root / "no-token.yml"
        no_token.write_text(
            good_action.read_text().replace(
                "        github_token: ${{ inputs.github-token }}\n",
                "",
            )
        )
        failures += expect(
            "missing github_token forwarding fails",
            run(good_wf, no_token),
            False,
            "forwards github_token",
        )

        with_inline = root / "inline.yml"
        with_inline.write_text(
            good_action.read_text().replace(
                '"Bash,Edit(//tmp/**),WebFetch,WebSearch"',
                '"mcp__github_inline_comment__create_inline_comment,Bash"',
            )
        )
        failures += expect(
            "inline-comment MCP on the allowlist fails",
            run(good_wf, with_inline),
            False,
            "inline-comment MCP tool is not allowlisted",
        )

        with_prt = root / "prt.yml"
        with_prt.write_text(
            good_wf.read_text().replace(
                "  workflow_call: {}",
                "  workflow_call: {}\n  pull_request_target:",
            )
        )
        failures += expect(
            "pull_request_target fails",
            run(with_prt, good_action),
            False,
            "pull_request_target-free",
        )

    if failures:
        print(f"::error::{failures} self-test case(s) failed", file=sys.stderr)
        return 1
    print("All run-review-job-split-tests self-tests passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--action", default=DEFAULT_ACTION)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    workflow = pathlib.Path(args.workflow)
    action = pathlib.Path(args.action)
    if not workflow.is_file():
        die(f"{workflow}: no such file")
    if not action.is_file():
        die(f"{action}: no such file")
    return check_workflow(workflow, action)


if __name__ == "__main__":
    sys.exit(main())
