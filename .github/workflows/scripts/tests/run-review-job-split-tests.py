#!/usr/bin/env python3
"""Pin the gha#580 credential split in claude-code-review.yml.

The model and a writable forge token must not share a job. A prefix deny
list cannot be a security boundary once Bash is granted whole (gha#580,
raised from a review of #578): wrapping a denied command, or writing
through a redirect, both go around it. The close is architectural.

This suite reads the workflow YAML and the attempt composite, and asserts
the facts a future edit could reverse silently:

1. The model job (`claude-review`) grants no forge-write permission
   and no `id-token: write`. Forwarding `github_token` skips the
   App-token exchange; that exchange's DEFAULT_PERMISSIONS are write
   (anthropics/claude-code-action v1.0.196 `src/github/token.ts`,
   measured 2026-08-26), so granting `id-token: write` would let a
   dropped override mint a write token.
2. The posting job (`post-review`) holds `pull-requests: write` and
   `issues: write`, and does not invoke the model.
3. The attempt composite forwards `github_token` to claude-code-action.
4. The inline-comment MCP tool is not in the model job's allowlist,
   because it posts during the model turn.
5. Pack still runs after a failed `resolve-final` (`!cancelled()` plus
   success/failure outcomes) so a no-verdict run still reaches the
   posting job (gha#543).
6. The gha#543 failure notice still posts when the packed artifact is
   missing (`download.outcome != 'success'` on a finished review).
7. Caller grant lists include `actions: read` (a `permissions:` block
   sets unspecified scopes to none; without it `download-artifact` 403s).

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
# `id-token: write` is included: in the pinned action it is exchanged for a
# GitHub App token whose DEFAULT_PERMISSIONS are contents/PRs/issues write.
FORGE_WRITE = {
    "contents": "write",
    "pull-requests": "write",
    "issues": "write",
    "actions": "write",
    "workflows": "write",
    "id-token": "write",
}

INLINE_TOOL = "mcp__github_inline_comment__create_inline_comment"
MODEL_USES = ("run-claude-review-attempt", "anthropics/claude-code-action")


def job_uses_model(job: dict) -> bool:
    return any(any(m in u for m in MODEL_USES) for u in uses_of(job))


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
        # write-all is a writable forge token for every scope, not just
        # contents. Mapping only contents: write would let a model job
        # with permissions: write-all pass the per-key FORGE_WRITE checks.
        return {key: "write" for key in FORGE_WRITE}
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
        review_perms.get("id-token") != "write",
        "claude-review does not grant id-token: write "
        "(App-token exchange is skipped; its defaults are write)",
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
    check(
        post_perms.get("actions") == "read",
        "post-review holds actions: read (download-artifact)",
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
    pack_step = next(
        (
            s
            for s in review.get("steps") or []
            if isinstance(s, dict)
            and "pack-review-payload" in str(s.get("uses", ""))
        ),
        None,
    )
    if pack_step is None:
        die(f"{workflow_path}: claude-review has no pack-review-payload step")
    pack_if = pack_step.get("if") or ""
    if not isinstance(pack_if, str):
        die(
            f"{workflow_path}: pack-review-payload if: is "
            f"{type(pack_if).__name__}, expected a string "
            "(a default success() gate would skip packing after "
            "resolve-final fails)"
        )
    check(
        "!cancelled()" in pack_if,
        "pack runs under !cancelled() so a failed resolve-final still packs",
    )
    check(
        "self_mod" in pack_if,
        "pack still runs on a self-mod skip so the skip notice can post",
    )
    pack_if_norm = " ".join(str(pack_if).split())
    check(
        "steps.resolve-final.outcome == 'failure'" in pack_if_norm
        or 'steps.resolve-final.outcome == "failure"' in pack_if_norm,
        "pack if: includes resolve-final.outcome == 'failure' (equality, not a negated comparison)",
    )
    check(
        "steps.resolve-final.outcome == 'success'" in pack_if_norm
        or 'steps.resolve-final.outcome == "success"' in pack_if_norm,
        "pack if: includes resolve-final.outcome == 'success'",
    )
    check(
        "!= 'failure'" not in pack_if_norm and '!= "failure"' not in pack_if_norm,
        "pack if: does not negate the failure outcome",
    )
    notice_step = next(
        (
            s
            for s in post.get("steps") or []
            if isinstance(s, dict)
            and "report-review-failure" in str(s.get("uses", ""))
        ),
        None,
    )
    if notice_step is None:
        die(f"{workflow_path}: post-review has no report-review-failure step")
    notice_if = notice_step.get("if") or ""
    if not isinstance(notice_if, str):
        die(
            f"{workflow_path}: report-review-failure if: is "
            f"{type(notice_if).__name__}, expected a string"
        )
    notice_if_norm = " ".join(str(notice_if).split())
    check(
        "!cancelled()" in notice_if_norm,
        "failure-notice runs under !cancelled() so Require failing the "
        "job does not skip the notice (implicit success() conjunct)",
    )
    check(
        "resolve_outcome == 'failure' ||" in notice_if_norm
        or 'resolve_outcome == "failure" ||' in notice_if_norm,
        "failure-notice if: ORs the loaded no-verdict path with the "
        "missing-artifact path (AND would skip both)",
    )
    check(
        "steps.download.outcome != 'success'" in notice_if_norm
        or 'steps.download.outcome != "success"' in notice_if_norm,
        "failure-notice if: still posts when the packed artifact is missing "
        "(download.outcome != 'success'; gha#543)",
    )
    check(
        "needs.claude-review.result == 'success'" in notice_if_norm
        or 'needs.claude-review.result == "success"' in notice_if_norm,
        "failure-notice missing-artifact path includes a successful review "
        "(Require would otherwise skip the notice)",
    )
    check(
        "needs.claude-review.result == 'failure'" in notice_if_norm
        or 'needs.claude-review.result == "failure"' in notice_if_norm,
        "failure-notice missing-artifact path requires a finished review "
        "(does not fire on cancelled/skipped)",
    )
    conc_review = (
        "claude-review-${{ github.event.pull_request.number || inputs.pr-number }}"
    )
    conc_stash = (
        "claude-review-stash-${{ github.event.pull_request.number || inputs.pr-number }}"
    )

    def concurrency_of(name: str) -> dict | None:
        conc = (jobs.get(name) or {}).get("concurrency")
        return conc if isinstance(conc, dict) else None

    if "preempt-previous" not in jobs:
        check(False, "preempt-previous cancels a superseded model job before stash")
    else:
        check(
            not job_uses_model(jobs["preempt-previous"]),
            "preempt-previous does not invoke the model",
        )
        preempt_conc = concurrency_of("preempt-previous")
        check(
            preempt_conc is not None and str(preempt_conc.get("group") or "") == conc_review,
            "preempt-previous shares the canceling review group",
        )
        check(
            preempt_conc is not None and preempt_conc.get("cancel-in-progress") is True,
            "preempt-previous cancels in-progress model jobs of that group",
        )
    review_conc = concurrency_of("claude-review")
    check(
        review_conc is not None and str(review_conc.get("group") or "") == conc_review,
        "claude-review uses the canceling review group",
    )
    check(
        review_conc is not None and review_conc.get("cancel-in-progress") is True,
        "claude-review cancels in-progress model jobs of that group",
    )
    for name in ("gather-context", "post-review"):
        conc = concurrency_of(name)
        if conc is None:
            check(False, f"{name} uses the non-canceling stash group")
            continue
        check(
            str(conc.get("group") or "") == conc_stash,
            f"{name} uses the non-canceling stash group",
        )
        check(
            conc.get("cancel-in-progress") is False,
            f"{name} queues behind another run's stash/restore "
            "(does not cancel in-progress writes)",
        )
        check(
            str(conc.get("group") or "") != conc_review,
            f"{name} does not share the canceling review group "
            "(a cancelled run's post-review would cancel the new model job)",
        )
    gather_needs = (jobs.get("gather-context") or {}).get("needs")
    if isinstance(gather_needs, str):
        gather_needs = [gather_needs]
    check(
        isinstance(gather_needs, list) and "preempt-previous" in gather_needs,
        "gather-context waits for preempt-previous so a cancelled run can restore first",
    )
    require_art = next(
        (
            s
            for s in post.get("steps") or []
            if isinstance(s, dict)
            and "Require the payload artifact" in str(s.get("name") or "")
        ),
        None,
    )
    if require_art is None:
        die(f"{workflow_path}: post-review has no Require the payload artifact step")
    req_if_raw = require_art.get("if") or ""
    if not isinstance(req_if_raw, str):
        die(
            f"{workflow_path}: Require the payload artifact if: is "
            f"{type(req_if_raw).__name__}, expected a string"
        )
    req_if = " ".join(req_if_raw.split())
    check(
        "steps.download.outcome == 'failure'" in req_if
        or 'steps.download.outcome == "failure"' in req_if,
        "Require the payload artifact keys on download.outcome == 'failure' "
        "(a skipped download is not a miss)",
    )
    check(
        "!= 'success'" not in req_if and '!= "success"' not in req_if,
        "Require the payload artifact does not treat a skipped download as a miss",
    )
    check(
        "steps.target.outputs.stale" in str((post.get("outputs") or {}).get("stale") or ""),
        "post-review surfaces stale so require-review can skip a withheld review",
    )
    if "require-review" in jobs:
        rif = " ".join(str(jobs["require-review"].get("if") or "").split())
        check(
            "post-review.outputs.stale" in rif,
            "require-review skips when post-review reports stale",
        )
    reviewed_head = str((review.get("outputs") or {}).get("reviewed-head") or "")
    check(
        " ".join(reviewed_head.split()) == "${{ github.event.pull_request.head.sha }}",
        "reviewed-head is exactly github.event.pull_request.head.sha",
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

    for name, job in jobs.items():
        if not job_uses_model(job):
            continue
        perms = job_permissions(job)
        for key, val in FORGE_WRITE.items():
            check(
                perms.get(key) != val,
                f"job {name} invokes the model and does not grant {key}: {val}",
            )

    if "gather-context" in jobs:
        check(
            not job_uses_model(jobs["gather-context"]),
            "gather-context does not invoke the model",
        )

    post_blob = str(post)
    check(
        "payload.outputs.pr_number" not in post_blob
        and not re.search(r"payload\.outputs\.repo(?:\s|}|$)", post_blob),
        "post-review does not take repo/PR identity from the model-job artifact",
    )
    check(
        any("parse-workflow-ref" in u for u in post_uses),
        "post-review re-parses the caller workflow ref (trusted targeting)",
    )
    compare_values = []
    for step in post.get("steps") or []:
        if not isinstance(step, dict):
            continue
        run = step.get("run")
        if not isinstance(run, str):
            continue
        compare_values.extend(re.findall(r'COMPARE="([^"]*)"', run))
    check(
        compare_values == ["${REVIEWED_HEAD:-$STASH_HEAD}"],
        "COMPARE is assigned exactly once to ${REVIEWED_HEAD:-$STASH_HEAD}",
    )
    target = next(
        (
            s
            for s in post.get("steps") or []
            if isinstance(s, dict) and s.get("id") == "target"
        ),
        None,
    )
    if target is not None:
        target_run = str(target.get("run") or "")
        check(
            "not posting an unverifiable review" in target_run,
            "live-head lookup fails closed when gh api cannot read the PR head",
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
        "github_token" in with_block and str(with_block.get("github_token") or "").strip() != "",
        "run-claude-review-attempt forwards github_token (skips the App-token write exchange)",
    )
    token_val = str(with_block.get("github_token") or "")
    check(
        "github.token" in token_val or "inputs.github-token" in token_val,
        "forwarded github_token is the job token (github.token / inputs.github-token), not empty",
    )
    check(
        with_block.get("classify_inline_comments") == "false",
        "classify_inline_comments is false so the post-session posting "
        "step is skipped (false means post immediately during the "
        "session; that path is closed because neither "
        "mcp__github_inline_comment__ nor mcp__github__ is allowlisted, "
        "so prepareMcpConfig does not start the server; "
        "anthropics/claude-code-action #1048)",
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
    check(
        not any(
            t.startswith("mcp__github_inline_comment__") or t.startswith("mcp__github__")
            for t in allowed
        ),
        "neither mcp__github_inline_comment__ nor mcp__github__ is allowlisted "
        "(either prefix starts the inline-comment MCP server)",
    )

    if workflow_path.name == "claude-code-review.yml":
        root = workflow_path.resolve().parent.parent.parent
        example = root / "examples" / "claude-code-review.yml"
        if example.is_file():
            ex = load_yaml(example)
            review_job = ((ex or {}).get("jobs") or {}).get("review") or {}
            check(
                job_permissions(review_job).get("actions") == "read",
                "examples/claude-code-review.yml grants actions: read "
                "(caller token; unspecified scopes are none)",
            )
        grant_list_re = (
            r"`claude-code-review`[\s\S]{0,80}?grant[s]? "
            r"(`contents: read`[\s\S]{0,250}?)(?:and either|and add)"
        )
        for rel, pattern, message in (
            (
                "README.md",
                grant_list_re,
                "README.md claude-code-review grant lists actions: read",
            ),
            (
                "website/permissions.qmd",
                grant_list_re,
                "website/permissions.qmd claude-code-review grant lists actions: read",
            ),
            (
                "website/reference/claude-code-review.qmd",
                r"## Permissions\n+Grant (`contents: read`[\s\S]{0,250}?)(?:and either|and add)",
                "website/reference/claude-code-review.qmd Permissions lists actions: read",
            ),
        ):
            path = root / rel
            if not path.is_file():
                continue
            blob = path.read_text(encoding="utf-8")
            m = re.search(pattern, blob)
            listed = m.group(1) if m else ""
            check("actions: read" in listed, message)
        ref = root / "website" / "reference" / "claude-code-review.qmd"
        if ref.is_file():
            check(
                re.search(
                    r"permissions:\n(?:[^\n]*\n)*?      actions: read",
                    ref.read_text(encoding="utf-8"),
                )
                is not None,
                "website/reference/claude-code-review.qmd Example grants actions: read",
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
        pack_if = (
            "!cancelled() && "
            "(steps.selfmod.outputs.self_mod == 'true' || "
            "steps.resolve-final.outcome == 'success' || "
            "steps.resolve-final.outcome == 'failure')"
        )
        notice_if = (
            "!cancelled() && "
            "(steps.payload.outputs.resolve_outcome == 'failure' || "
            "(steps.download.outcome != 'success' && "
            "(needs.claude-review.result == 'success' || "
            "needs.claude-review.result == 'failure')))"
        )
        review_conc = (
            "    concurrency:\n"
            "      group: claude-review-${{ github.event.pull_request.number || inputs.pr-number }}\n"
            "      cancel-in-progress: true\n"
        )
        stash_conc = (
            "    concurrency:\n"
            "      group: claude-review-stash-${{ github.event.pull_request.number || inputs.pr-number }}\n"
            "      cancel-in-progress: false\n"
        )
        good_wf.write_text(
            f"""
on:
  workflow_call: {{}}
jobs:
  preempt-previous:
{review_conc}    permissions: {{}}
    steps:
      - run: echo cancel predecessor
  gather-context:
    needs: preempt-previous
{stash_conc}    permissions:
      pull-requests: write
      issues: write
    steps:
      - run: echo stash
  claude-review:
{review_conc}    outputs:
      reviewed-head: ${{{{ github.event.pull_request.head.sha }}}}
    permissions:
      contents: read
      pull-requests: read
      issues: read
      actions: read
    steps:
      - uses: Morrison-Lab/gha/.github/actions/run-claude-review-attempt@v2
      - uses: Morrison-Lab/gha/.github/actions/pack-review-payload@v2
        if: "{pack_if}"
  post-review:
    needs: claude-review
{stash_conc}    outputs:
      stale: ${{{{ steps.target.outputs.stale }}}}
    permissions:
      pull-requests: write
      issues: write
      actions: read
    steps:
      - uses: Morrison-Lab/gha/.github/actions/parse-workflow-ref@v2
      - uses: actions/download-artifact@v4
      - name: Require the payload artifact on a finished review
        if: needs.claude-review.result == 'success' && steps.download.outcome == 'failure'
        run: exit 1
      - uses: Morrison-Lab/gha/.github/actions/report-review-failure@v2
        if: "{notice_if}"
      - id: target
        run: |
          echo "not posting an unverifiable review"
          COMPARE="${{REVIEWED_HEAD:-$STASH_HEAD}}"
  require-review:
    needs: [claude-review, post-review]
    if: always() && !(needs.post-review.result == 'success' && fromJSON(needs.post-review.outputs.stale || 'false'))
    steps:
      - run: echo ok
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

        with_github_mcp = root / "github-mcp.yml"
        with_github_mcp.write_text(
            good_action.read_text().replace(
                '"Bash,Edit(//tmp/**),WebFetch,WebSearch"',
                '"mcp__github__create_pull_request,Bash"',
            )
        )
        failures += expect(
            "mcp__github__ prefix on the allowlist fails",
            run(good_wf, with_github_mcp),
            False,
            "mcp__github__",
        )

        classify_true = root / "classify-true.yml"
        classify_true.write_text(
            good_action.read_text().replace(
                "        classify_inline_comments: 'false'\n",
                "        classify_inline_comments: 'true'\n",
            )
        )
        failures += expect(
            "classify_inline_comments true fails (would run the post-session poster)",
            run(good_wf, classify_true),
            False,
            "classify_inline_comments is false",
        )

        classify_omitted = root / "classify-omitted.yml"
        classify_omitted.write_text(
            good_action.read_text().replace(
                "        classify_inline_comments: 'false'\n",
                "",
            )
        )
        failures += expect(
            "omitting classify_inline_comments fails",
            run(good_wf, classify_omitted),
            False,
            "classify_inline_comments is false",
        )

        write_all = root / "write-all.yml"
        write_all.write_text(
            good_wf.read_text().replace(
                "    permissions:\n"
                "      contents: read\n"
                "      pull-requests: read\n"
                "      issues: read\n"
                "      actions: read\n",
                "    permissions: write-all\n",
                1,
            )
        )
        failures += expect(
            "permissions: write-all on the model job fails",
            run(write_all, good_action),
            False,
            "claude-review does not grant pull-requests: write",
        )

        empty_token = root / "empty-token.yml"
        empty_token.write_text(
            good_action.read_text().replace(
                "        github_token: ${{ inputs.github-token }}\n",
                "        github_token: ''\n",
            )
        )
        failures += expect(
            "empty github_token forwarding fails",
            run(good_wf, empty_token),
            False,
            "job token",
        )

        model_in_gather = root / "model-in-gather.yml"
        model_in_gather.write_text(
            good_wf.read_text().replace(
                "      - run: echo stash\n",
                "      - uses: Morrison-Lab/gha/.github/actions/run-claude-review-attempt@v2\n",
            )
        )
        failures += expect(
            "model in a writable gather-context job fails",
            run(model_in_gather, good_action),
            False,
            "gather-context does not invoke the model",
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

        with_id_token = root / "id-token.yml"
        with_id_token.write_text(
            good_wf.read_text().replace(
                "      actions: read\n",
                "      actions: read\n      id-token: write\n",
                1,
            )
        )
        failures += expect(
            "id-token: write on the model job fails",
            run(with_id_token, good_action),
            False,
            "claude-review does not grant id-token: write",
        )

        no_pack_if = root / "no-pack-if.yml"
        no_pack_if.write_text(
            good_wf.read_text().replace(
                f'        if: "{pack_if}"\n',
                "",
            )
        )
        failures += expect(
            "omitting pack if: (default success() gate) fails",
            run(no_pack_if, good_action),
            False,
            "pack runs under !cancelled()",
        )

        success_gate = root / "success-gate.yml"
        success_gate.write_text(
            good_wf.read_text().replace(
                f'        if: "{pack_if}"\n',
                "        if: success()\n",
            )
        )
        failures += expect(
            "pack if: success() still fails",
            run(success_gate, good_action),
            False,
            "pack runs under !cancelled()",
        )

        bool_if = root / "bool-if.yml"
        bool_if.write_text(
            good_wf.read_text().replace(
                f'        if: "{pack_if}"\n',
                "        if: true\n",
            )
        )
        failures += expect(
            "boolean pack if: fails",
            run(bool_if, good_action),
            False,
            "expected a string",
        )

        flipped_failure = root / "flipped-failure.yml"
        flipped_failure.write_text(
            good_wf.read_text().replace(
                "steps.resolve-final.outcome == 'failure'",
                "steps.resolve-final.outcome != 'failure'",
                1,
            )
        )
        failures += expect(
            "negated resolve-final failure comparison fails",
            run(flipped_failure, good_action),
            False,
            "resolve-final.outcome == 'failure'",
        )

        late_sha = root / "late-sha.yml"
        late_sha.write_text(
            good_wf.read_text().replace(
                "github.event.pull_request.head.sha",
                "steps.stash.outputs.head_before",
                1,
            )
        )
        failures += expect(
            "reviewed-head from a later API fetch fails",
            run(late_sha, good_action),
            False,
            "exactly github.event.pull_request.head.sha",
        )

        stash_only = root / "stash-only.yml"
        stash_only.write_text(
            good_wf.read_text().replace(
                'COMPARE="${REVIEWED_HEAD:-$STASH_HEAD}"',
                'COMPARE="$STASH_HEAD"',
                1,
            )
        )
        failures += expect(
            "stale check using only gather stash-head fails",
            run(stash_only, good_action),
            False,
            "COMPARE is assigned exactly once",
        )

        extra_fallback = root / "extra-fallback.yml"
        extra_fallback.write_text(
            good_wf.read_text().replace(
                "github.event.pull_request.head.sha",
                "github.event.pull_request.head.sha || steps.stash.outputs.head_before",
                1,
            )
        )
        failures += expect(
            "reviewed-head with a later-SHA fallback fails",
            run(extra_fallback, good_action),
            False,
            "exactly github.event.pull_request.head.sha",
        )

        second_compare = root / "second-compare.yml"
        second_compare.write_text(
            good_wf.read_text().replace(
                'COMPARE="${REVIEWED_HEAD:-$STASH_HEAD}"',
                'COMPARE="${REVIEWED_HEAD:-$STASH_HEAD}"\n          COMPARE="$STASH_HEAD"',
                1,
            )
        )
        failures += expect(
            "a later COMPARE=$STASH_HEAD assignment fails",
            run(second_compare, good_action),
            False,
            "COMPARE is assigned exactly once",
        )

        payload_only_notice = root / "payload-only-notice.yml"
        payload_only_notice.write_text(
            good_wf.read_text().replace(
                f'        if: "{notice_if}"\n',
                "        if: steps.payload.outputs.resolve_outcome == 'failure'\n",
            )
        )
        failures += expect(
            "failure-notice gated only on payload resolve_outcome fails",
            run(payload_only_notice, good_action),
            False,
            "download.outcome != 'success'",
        )

        anded_notice = root / "anded-notice.yml"
        anded_notice.write_text(
            good_wf.read_text().replace(
                "resolve_outcome == 'failure' || ",
                "resolve_outcome == 'failure' && ",
                1,
            )
        )
        failures += expect(
            "AND between resolve_outcome and download.outcome fails",
            run(anded_notice, good_action),
            False,
            "ORs the loaded no-verdict path",
        )

        no_success_arm = root / "no-success-arm.yml"
        no_success_arm.write_text(
            good_wf.read_text().replace(
                "(needs.claude-review.result == 'success' || "
                "needs.claude-review.result == 'failure')",
                "(needs.claude-review.result == 'failure')",
                1,
            )
        )
        failures += expect(
            "dropping the success arm of the missing-artifact path fails",
            run(no_success_arm, good_action),
            False,
            "includes a successful review",
        )

        no_cancelled_guard = root / "no-cancelled-guard.yml"
        no_cancelled_guard.write_text(
            good_wf.read_text().replace(
                f'        if: "{notice_if}"\n',
                '        if: "' + notice_if.replace("!cancelled() && ", "", 1) + '"\n',
            )
        )
        failures += expect(
            "omitting !cancelled() on the failure notice fails",
            run(no_cancelled_guard, good_action),
            False,
            "failure-notice runs under !cancelled()",
        )

        skipped_is_miss = root / "skipped-is-miss.yml"
        skipped_is_miss.write_text(
            good_wf.read_text().replace(
                "steps.download.outcome == 'failure'",
                "steps.download.outcome != 'success'",
                1,
            )
        )
        failures += expect(
            "treating a skipped download as a missing artifact fails",
            run(skipped_is_miss, good_action),
            False,
            "does not treat a skipped download as a miss",
        )

        gather_on_review_group = root / "gather-on-review-group.yml"
        gather_on_review_group.write_text(
            good_wf.read_text().replace(stash_conc, review_conc, 1)
        )
        failures += expect(
            "gather-context on the canceling review group fails",
            run(gather_on_review_group, good_action),
            False,
            "does not share the canceling review group",
        )

        stash_cancels = root / "stash-cancels.yml"
        stash_cancels.write_text(
            good_wf.read_text().replace(
                "      cancel-in-progress: false\n",
                "      cancel-in-progress: true\n",
                1,
            )
        )
        failures += expect(
            "cancel-in-progress on the stash group fails",
            run(stash_cancels, good_action),
            False,
            "does not cancel in-progress writes",
        )

        no_preempt = root / "no-preempt.yml"
        no_preempt.write_text(
            good_wf.read_text().replace(
                "  preempt-previous:\n"
                + review_conc
                + "    permissions: {}\n"
                + "    steps:\n"
                + "      - run: echo cancel predecessor\n",
                "",
                1,
            ).replace(
                "    needs: preempt-previous\n",
                "",
                1,
            )
        )
        failures += expect(
            "omitting preempt-previous fails",
            run(no_preempt, good_action),
            False,
            "preempt-previous cancels a superseded model job before stash",
        )

        live_head_open = root / "live-head-open.yml"
        live_head_open.write_text(
            good_wf.read_text().replace(
                '          echo "not posting an unverifiable review"\n',
                "",
                1,
            )
        )
        failures += expect(
            "live-head lookup that can fail open fails",
            run(live_head_open, good_action),
            False,
            "fails closed when gh api cannot read the PR head",
        )

        no_stale_skip = root / "no-stale-skip.yml"
        no_stale_skip.write_text(
            good_wf.read_text().replace(
                "always() && !(needs.post-review.result == 'success' && "
                "fromJSON(needs.post-review.outputs.stale || 'false'))",
                "always()",
                1,
            )
        )
        failures += expect(
            "require-review ignoring a stale post fails",
            run(no_stale_skip, good_action),
            False,
            "require-review skips when post-review reports stale",
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
