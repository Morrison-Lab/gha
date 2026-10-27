#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Fail when a workflow calls a gha reusable workflow without the permissions it needs.

A nested job cannot request more than its caller grants, so a caller that
omits a permission the reusable workflow asks for fails at startup
(``startup_failure``) with no step run and no log. A scheduled caller then
stops silently: lds's weekly preview cleanup did this for a week because its
job lacked ``actions: read`` (Morrison-Lab/lds#1468).

The callee cannot warn from inside, so this check runs in the consumer
repository, reads each ``uses: Morrison-Lab/gha/.github/workflows/<name>@<ref>``
job, fetches that callee at that ref, and compares what the callee's jobs
request (the union, as ``audit_callee_permissions.py`` defines it) with what
the calling job grants. A caller job with no block takes the workflow-level
block; with neither, its grant is the repository default, which this check
cannot see, so that call is reported as unchecked and not as clean.

Environment: CCP_WORKFLOWS_DIR (default .github/workflows), CCP_FAIL (default
true), CCP_GHA_DIR (a local gha checkout to read callees from instead of
fetching them, for tests and offline runs).
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

_SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from audit_callee_permissions import (  # noqa: E402
    LEVELS,
    extract_callee_permissions,
    is_reusable_workflow,
    load_yaml_str,
    normalize_permissions_block,
    union_of_job_grants,
)
from workflow_discovery import Discovery, Unparsable, require_workflows  # noqa: E402

USES_RE = re.compile(
    r"^Morrison-Lab/gha/\.github/workflows/(?P<name>[^/@]+\.ya?ml)@(?P<ref>.+)$",
    re.IGNORECASE,
)
RAW_URL = "https://raw.githubusercontent.com/Morrison-Lab/gha/{ref}/.github/workflows/{name}"


def fetch_callee(name: str, ref: str, gha_dir: str | None) -> str:
    """Return the callee's text at ``ref``, from a local checkout or the web."""
    if gha_dir:
        return (pathlib.Path(gha_dir) / ".github" / "workflows" / name).read_text()
    url = RAW_URL.format(ref=ref, name=name)
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def required_grants(callee_text: str, name: str) -> dict[str, str] | None:
    """The union of what the callee's jobs request, or None when unknown."""
    doc = load_yaml_str(callee_text, name)
    if not is_reusable_workflow(doc):
        raise Unparsable(f"{name}: not a reusable workflow (no on: workflow_call)")
    declared = extract_callee_permissions(doc, name)
    workflow_p = declared.pop("(workflow)")
    return union_of_job_grants(declared, workflow_p)


def missing_grants(required: dict[str, str], granted: dict[str, str]) -> list[str]:
    """Permissions the callee requests above what the caller grants."""
    return [
        f"{key}: {level}"
        for key, level in sorted(required.items())
        if LEVELS[level] > LEVELS[granted.get(key, "none")]
    ]


def check_workflow(path: pathlib.Path, gha_dir: str | None):
    """Yield (kind, line) for each gha call in one caller workflow."""
    doc = load_yaml_str(path.read_text(), str(path))
    workflow_p = normalize_permissions_block(doc.get("permissions"), f"{path}: permissions")
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        raise Unparsable(f"{path}: missing or invalid 'jobs' mapping")
    for job_id, job in sorted(jobs.items()):
        uses = job.get("uses") if isinstance(job, dict) else None
        match = USES_RE.match(uses) if isinstance(uses, str) else None
        if not match:
            continue
        name, ref = match["name"], match["ref"]
        job_p = normalize_permissions_block(job.get("permissions"), f"{path}: job '{job_id}'")
        granted = job_p if job_p is not None else workflow_p
        required = required_grants(fetch_callee(name, ref, gha_dir), name)
        where = f"{path}: job '{job_id}' calls {name}@{ref}"
        if granted is None:
            yield "unchecked", f"{where}: no permissions block at job or workflow level, so the grant is the repository default"
        elif required is None:
            yield "unchecked", f"{where}: the callee has a job with no permissions block, so what it needs is unknown"
        else:
            gaps = missing_grants(required, granted)
            if gaps:
                yield "missing", f"{where}: caller does not grant {', '.join(gaps)}"
            else:
                yield "ok", where


def main() -> int:
    workflows_dir = pathlib.Path(os.environ.get("CCP_WORKFLOWS_DIR", ".github/workflows"))
    fail = os.environ.get("CCP_FAIL", "true").lower() in ("true", "1", "yes")
    gha_dir = os.environ.get("CCP_GHA_DIR") or None
    counts = {"ok": 0, "unchecked": 0, "missing": 0}
    try:
        for path in require_workflows(workflows_dir):
            for kind, line in check_workflow(path, gha_dir):
                counts[kind] += 1
                if kind == "missing":
                    print(f"::error::{line}", file=sys.stderr)
                elif kind == "unchecked":
                    print(f"::warning::{line}")
    except (Discovery, Unparsable, OSError, urllib.error.URLError) as exc:
        print(f"::error::check-caller-permissions could not finish: {exc}", file=sys.stderr)
        return 2
    print(
        f"Examined {sum(counts.values())} call(s) of gha reusable workflows: "
        f"{counts['ok']} ok, {counts['missing']} missing a grant, {counts['unchecked']} unchecked."
    )
    return 1 if counts["missing"] and fail else 0


if __name__ == "__main__":
    sys.exit(main())
