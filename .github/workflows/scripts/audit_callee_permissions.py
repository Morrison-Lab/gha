#!/usr/bin/env python3
"""Fail when reusable workflows add permission keys or widen permission levels.

A reusable workflow's job-level (and workflow-level) ``permissions:`` block is
part of its caller contract: a nested job cannot request more than its caller
grants, so adding a permission -- even a ``read`` -- fails every caller written
against the old contract at **parse time** (``startup_failure``) with no
API-visible diagnostic (gha#685, gha#830, gha#831, gha#836).

This audit parses reusable workflows (``on: workflow_call``) across two git refs
(or a base ref and the working tree), compares the effective permissions of
each callee job and workflow level, and reports violations when:
1. A callee job or workflow level gains a new permission key that did not exist
   at the base ref.
2. An existing permission value is widened (e.g. ``read`` -> ``write``, or
   dict -> ``write-all``).
3. A job gains a ``permissions:`` block where it previously had none (explicitly
   declaring keys that were previously unconstrained or inherited).
4. A job loses its ``permissions:`` block when the base ref had one (reverting
   to caller/workflow inheritance, which widens permission scope).

Narrowings (``write`` -> ``read``, ``read`` -> ``none``) and removed keys
are permitted, as they do not require callers to grant anything new.
Brand-new reusable workflows added since the base ref have no existing callers
pinned to that base ref, and are exempt.

Usage::

    python3 audit_callee_permissions.py --base-ref <ref> [--head-ref <ref>] [--workflows-dir DIR]
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

# Level scale for comparing permission values: higher number means broader access.
# none < read < write.
LEVELS = {
    "none": 1,
    "read": 2,
    "write": 3,
}

# Standard GitHub Actions permission scopes covered by shorthand `read-all` / `write-all`.
SHORTHAND_KEYS = frozenset(
    [
        "actions",
        "attestations",
        "checks",
        "contents",
        "deployments",
        "discussions",
        "id-token",
        "issues",
        "models",
        "packages",
        "pages",
        "pull-requests",
        "repository-projects",
        "security-events",
        "statuses",
    ]
)


def load_yaml(content: str, filename: str) -> dict:
    """Safely parse YAML content with PyYAML, failing closed."""
    try:
        import yaml
    except ImportError:
        print(
            "::error::PyYAML is required to parse workflows but is not "
            "installed (install it with `python3 -m pip install pyyaml`).",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        doc = yaml.safe_load(content)
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ValueError(f"{filename}: YAML parse error: {exc}") from exc

    if doc is None:
        return {}
    if not isinstance(doc, dict):
        raise ValueError(f"{filename}: top level is {type(doc).__name__}, not a mapping")
    return doc


def is_reusable_workflow(doc: dict) -> bool:
    """Return True if the workflow declares on: workflow_call."""
    # PyYAML parses a bare `on:` key as the boolean True, so check both spellings.
    triggers = doc.get(True, doc.get("on"))
    return isinstance(triggers, dict) and "workflow_call" in triggers


def normalize_permissions_block(p: object, context: str) -> dict[str, str] | None:
    """Convert raw permissions block to a mapping of scope -> level string ('none', 'read', 'write').

    Returns None if no permissions block was declared (inherits caller/top-level).
    Empty dict {} means all permissions are set to none.
    """
    if p is None:
        return None
    if p == "read-all":
        return {k: "read" for k in sorted(SHORTHAND_KEYS)}
    if p == "write-all":
        return {k: "write" for k in sorted(SHORTHAND_KEYS)}
    if isinstance(p, dict):
        res = {}
        for k, v in p.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ValueError(
                    f"{context}: permission entry {k!r}: {v!r} is not string:string"
                )
            v_norm = v.lower().strip()
            if v_norm not in LEVELS:
                raise ValueError(
                    f"{context}: unknown permission value {v!r} for key {k!r} "
                    f"(expected one of: {', '.join(sorted(LEVELS))})"
                )
            res[k] = v_norm
        return res

    raise ValueError(f"{context}: unexpected permissions type: {type(p).__name__}")


def extract_callee_permissions(doc: dict, filename: str) -> dict[str, dict[str, str] | None]:
    """Extract declared permissions for workflow level and each job in a reusable workflow.

    Returns mapping:
      "(workflow)" -> normalized permissions dict or None
      "<job_id>" -> normalized permissions dict or None
    """
    res: dict[str, dict[str, str] | None] = {}
    top_p = normalize_permissions_block(doc.get("permissions"), f"{filename}: top-level permissions")
    res["(workflow)"] = top_p

    jobs = doc.get("jobs")
    if jobs is None or not isinstance(jobs, dict):
        raise ValueError(f"{filename}: missing or invalid 'jobs' mapping")

    for job_id, job in sorted(jobs.items()):
        if not isinstance(job, dict):
            raise ValueError(f"{filename}: job '{job_id}' is not a mapping")
        job_p = normalize_permissions_block(job.get("permissions"), f"{filename}: job '{job_id}' permissions")
        res[str(job_id)] = job_p

    return res


def compare_target_permissions(
    base_p: dict[str, str] | None,
    head_p: dict[str, str] | None,
    target_name: str,
    path: str,
) -> list[str]:
    """Compare base vs head permissions for a single target (job or workflow).

    Returns a list of violation messages.
    """
    violations: list[str] = []

    # Case 1: Job had no permissions block, but head added one.
    # Adding an explicit permissions block introduces new required grants on callers.
    if base_p is None and head_p is not None:
        added_keys = [k for k, v in head_p.items() if v != "none"]
        if added_keys:
            violations.append(
                f"{path}: {target_name} gained permissions block requesting: "
                f"{', '.join(f'{k}: {head_p[k]}' for k in sorted(added_keys))}"
            )
        return violations

    # Case 2: Job had permissions block, but head dropped it entirely.
    # Dropping permissions block means it falls back to workflow/caller permissions,
    # which widens access compared to the previous explicit restrictions.
    if base_p is not None and head_p is None:
        violations.append(
            f"{path}: {target_name} dropped its permissions block (reverts to unconstrained inheritance)"
        )
        return violations

    # Case 3: Both are None -> unchanged inheritance.
    if base_p is None and head_p is None:
        return violations

    # Case 4: Both are dicts. Check for added keys and escalated values.
    # base_p and head_p are guaranteed dict[str, str] here.
    assert base_p is not None and head_p is not None

    for key, head_val in sorted(head_p.items()):
        if head_val == "none":
            # Explicitly declaring 'none' narrows access and never demands caller grants.
            continue
        if key not in base_p:
            violations.append(
                f"{path}: {target_name} added permission '{key}: {head_val}' (not in base)"
            )
        else:
            base_val = base_p[key]
            head_level = LEVELS[head_val]
            base_level = LEVELS[base_val]
            if head_level > base_level:
                violations.append(
                    f"{path}: {target_name} widened permission '{key}': "
                    f"'{base_val}' -> '{head_val}'"
                )

    return violations


def git_show(ref: str, path: str, cwd: pathlib.Path | None = None) -> str:
    """Read file content at a git ref using git show."""
    try:
        proc = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
        return proc.stdout
    except subprocess.CalledProcessError as exc:
        raise FileNotFoundError(f"Failed to read {path} at {ref}: {exc.stderr.strip()}") from exc


def get_git_workflows(ref: str, workflows_dir: str = ".github/workflows", cwd: pathlib.Path | None = None) -> list[str]:
    """List workflow files present at a given git ref."""
    try:
        proc = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref, workflows_dir],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
        files = []
        for line in proc.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            p = pathlib.Path(line)
            if p.suffix in (".yml", ".yaml") and not p.name.startswith("."):
                # Must be directly in workflows_dir, not in a nested subdirectory
                if p.parent == pathlib.Path(workflows_dir):
                    files.append(line)
        return sorted(files)
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Failed to list workflows at ref {ref}: {exc.stderr.strip()}") from exc


def audit_permissions(
    base_ref: str,
    head_ref: str | None = None,
    workflows_dir: str = ".github/workflows",
    cwd: pathlib.Path | None = None,
) -> tuple[list[str], int, int]:
    """Audit callee permissions between base_ref and head_ref (or working tree).

    Returns:
      (violations, examined_workflows_count, examined_jobs_count)
    """
    base_files = set(get_git_workflows(base_ref, workflows_dir, cwd=cwd))

    if head_ref is not None:
        head_files = set(get_git_workflows(head_ref, workflows_dir, cwd=cwd))
    else:
        # Working tree
        target_dir = (cwd / workflows_dir) if cwd else pathlib.Path(workflows_dir)
        if not target_dir.is_dir():
            raise ValueError(f"Workflows directory not found: {target_dir}")
        head_files = set(
            str(p.relative_to(cwd) if cwd else p)
            for p in target_dir.iterdir()
            if p.is_file() and p.suffix in (".yml", ".yaml") and not p.name.startswith(".")
        )

    # Check common workflows that exist in both refs
    common_workflows = sorted(base_files & head_files)

    all_violations: list[str] = []
    examined_workflows = 0
    examined_jobs = 0

    for wf_path in common_workflows:
        # Load base workflow
        base_content = git_show(base_ref, wf_path, cwd=cwd)
        base_doc = load_yaml(base_content, f"{wf_path}@{base_ref}")
        if not is_reusable_workflow(base_doc):
            continue

        # Load head workflow
        if head_ref is not None:
            head_content = git_show(head_ref, wf_path, cwd=cwd)
        else:
            file_disk = (cwd / wf_path) if cwd else pathlib.Path(wf_path)
            head_content = file_disk.read_text(encoding="utf-8")

        head_doc = load_yaml(head_content, f"{wf_path}@(head)")
        if not is_reusable_workflow(head_doc):
            # Workflow was reusable at base but no longer reusable at head.
            # Callers calling it will fail if it's no longer reusable, but this audit
            # focuses on permission contract widening.
            continue

        examined_workflows += 1
        base_perms = extract_callee_permissions(base_doc, f"{wf_path}@{base_ref}")
        head_perms = extract_callee_permissions(head_doc, f"{wf_path}@(head)")

        # Compare workflow-level permissions
        v = compare_target_permissions(
            base_perms.get("(workflow)"),
            head_perms.get("(workflow)"),
            "workflow level",
            wf_path,
        )
        all_violations.extend(v)

        # Compare all jobs in head that existed in base
        base_jobs = {k: v for k, v in base_perms.items() if k != "(workflow)"}
        head_jobs = {k: v for k, v in head_perms.items() if k != "(workflow)"}

        for job_id, head_p in sorted(head_jobs.items()):
            examined_jobs += 1
            if job_id not in base_jobs:
                # Job added in an existing reusable workflow.
                # If it declares permissions, callers will need to satisfy them.
                if head_p is not None:
                    added_keys = [k for k, val in head_p.items() if val != "none"]
                    if added_keys:
                        all_violations.append(
                            f"{wf_path}: new job '{job_id}' added with permissions: "
                            f"{', '.join(f'{k}: {head_p[k]}' for k in sorted(added_keys))}"
                        )
            else:
                base_p = base_jobs[job_id]
                v = compare_target_permissions(
                    base_p,
                    head_p,
                    f"job '{job_id}'",
                    wf_path,
                )
                all_violations.extend(v)

    return all_violations, examined_workflows, examined_jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit callee reusable workflow permissions for added keys or widened levels."
    )
    parser.add_argument(
        "--base-ref",
        required=True,
        help="Base git reference or tag to compare against (e.g. v2 or origin/main).",
    )
    parser.add_argument(
        "--head-ref",
        default=None,
        help="Head git reference (e.g. HEAD or commit SHA). Defaults to inspecting working tree.",
    )
    parser.add_argument(
        "--workflows-dir",
        default=".github/workflows",
        help="Directory containing GitHub Actions workflows (default: .github/workflows).",
    )

    args = parser.parse_args(argv)

    try:
        violations, w_count, j_count = audit_permissions(
            base_ref=args.base_ref,
            head_ref=args.head_ref,
            workflows_dir=args.workflows_dir,
        )
    except Exception as exc:
        print(f"::error::Audit failed with error: {exc}", file=sys.stderr)
        return 2

    if violations:
        print(
            f"::error::Found {len(violations)} permission widening violation(s) "
            f"across callee workflows compared to {args.base_ref}:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"::error::{v}", file=sys.stderr)
        return 1

    target_desc = args.head_ref if args.head_ref else "working tree"
    print(
        f"OK: No permission widenings detected between {args.base_ref} and {target_desc} "
        f"(examined {j_count} jobs across {w_count} reusable workflows)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
