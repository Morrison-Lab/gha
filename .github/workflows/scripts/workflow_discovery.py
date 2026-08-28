#!/usr/bin/env python3
"""Shared workflow discovery for this repo's own workflow audits.

One module rather than a glob repeated per audit, because the glob is exactly
what drifted: a ``*.yml``-only pattern lets a ``.yaml`` workflow bypass any
audit built on it, silently and with nothing red (gha#705, gha#716).

Both extensions, because GitHub loads ``.yml`` and ``.yaml`` alike and this
repo's own ``detect-pr-workflow-edits.sh`` recognizes both.  Top-level only,
for the same reason that script rejects nested paths: ``.github/workflows/
scripts/...`` is not a workflow, so an audit sweeping it in would report
findings GitHub never loads.

PyYAML is required by the callers that parse.  It ships preinstalled on the
GitHub-hosted Ubuntu runner image, which is where ``_selftest.yml`` runs these;
the import is guarded so a runner that ever drops it fails with an actionable
message rather than a traceback.
"""

from __future__ import annotations

import pathlib
import sys

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised only on a bare runner
    print(
        "::error::PyYAML is required by the workflow audits but is not installed. "
        "Install it (`pip install pyyaml`) or restore the runner image that ships it.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def discover_workflows(workflows_dir: pathlib.Path) -> list[pathlib.Path]:
    """Return the workflow files GitHub itself would discover, sorted."""
    return sorted(
        p
        for p in workflows_dir.iterdir()
        if p.is_file() and p.suffix in (".yml", ".yaml")
    )


def require_workflows(workflows_dir: pathlib.Path) -> list[pathlib.Path]:
    """`discover_workflows`, but refuse to return an empty list.

    An audit handed no paths examines nothing and reports clean, which is
    indistinguishable from a tree with no violations.  Failing here is what
    keeps that state from ever reaching a green check.
    """
    if not workflows_dir.is_dir():
        raise Discovery(f"workflows directory not found: {workflows_dir}")
    found = discover_workflows(workflows_dir)
    if not found:
        raise Discovery(
            f"no .yml or .yaml workflow files under {workflows_dir} --- "
            "an audit built on this list would pass having examined nothing"
        )
    return found


class Discovery(Exception):
    """Discovery could not produce a usable file list."""


class Unparsable(Exception):
    """A workflow file could not be parsed, so it was never examined."""


def load_workflow(path: pathlib.Path):
    """Parse one workflow, refusing rather than skipping on bad input.

    A file the audit could not read is not a file with no violations.  Treating
    the two alike is how a check passes over content it never saw --- the same
    conflation the shell version made by reading ``grep``'s exit 2 as exit 1.
    """
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise Unparsable(f"{path}: {exc}") from exc
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        raise Unparsable(f"{path}: top level is {type(doc).__name__}, not a mapping")
    return doc


def iter_steps(doc):
    """Yield ``(job_id, step_index, step)`` for every parsed step in a workflow.

    Steps written as ``- uses: x`` and as ``- name: y`` / ``uses: x`` are the
    same parsed mapping, which is the whole reason to walk structure instead of
    text: the two spellings are indistinguishable here, where a line-anchored
    regex sees only the second (gha#720).
    """
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for index, step in enumerate(steps):
            if isinstance(step, dict):
                yield str(job_id), index, step


def iter_job_uses(doc):
    """Yield ``(job_id, uses)`` for every reusable-workflow call in a workflow."""
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return
    for job_id, job in jobs.items():
        if isinstance(job, dict) and isinstance(job.get("uses"), str):
            yield str(job_id), job["uses"]
