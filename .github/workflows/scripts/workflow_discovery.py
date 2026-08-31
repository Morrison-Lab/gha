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

PyYAML is required only by ``load_workflow``, and is imported there rather
than at module load so the discovery half stays importable without it.  It
ships preinstalled on the GitHub-hosted Ubuntu runner image, which is where
``_selftest.yml`` runs these; the import is guarded so a runner that ever drops
it fails with an actionable message rather than a traceback.
"""

from __future__ import annotations

import os
import pathlib
import sys


def is_workflows_restored(workflows_dir: pathlib.Path | None = None) -> bool:
    """Return True if .github/workflows was restored from default branch (gha#598)."""
    if os.environ.get("GHA_WORKFLOWS_RESTORED") == "1":
        return True
    if workflows_dir is None:
        workflows_dir = pathlib.Path(".github/workflows")
    return (workflows_dir / ".restored-from-default-branch").is_file()


def skip_if_restored(workflows_dir: pathlib.Path | None = None, label: str = "workflow check") -> bool:
    """Print a notice and return True if .github/workflows was restored from default branch (gha#598, gha#765)."""
    if is_workflows_restored(workflows_dir):
        print(
            f"::notice::Skipping {label}: .github/workflows/ "
            "was restored from default branch (gha#598, gha#765)."
        )
        return True
    return False


def discover_workflows(workflows_dir: pathlib.Path) -> list[pathlib.Path]:
    """Return the workflow files GitHub itself would discover, sorted."""
    return sorted(
        p
        for p in workflows_dir.iterdir()
        if p.is_file() and p.suffix in (".yml", ".yaml") and not p.name.startswith(".")
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
    # Imported here rather than at module load, so importing this module for
    # its discovery half -- which touches no YAML -- does not require PyYAML,
    # and `--help` still works on a machine without it.
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover - only on a bare runner
        print(
            "::error::PyYAML is required to parse workflows but is not "
            "installed (install it with `python3 -m pip install pyyaml`).",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise Unparsable(f"{path}: {exc}") from exc
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        raise Unparsable(f"{path}: top level is {type(doc).__name__}, not a mapping")
    return doc


def require_jobs(path: pathlib.Path, doc) -> dict:
    """Return a workflow's ``jobs`` mapping, refusing anything else.

    Skipping a malformed shape is the parsed-walk version of reading grep's
    exit 2 as exit 1: the audit walks nothing and reports clean, and the file
    that produced that verdict is the one nobody looked at. Every workflow
    GitHub will run has a ``jobs`` mapping, so its absence or wrong type is a
    defect in the file rather than a file with nothing to audit.
    """
    if not doc:
        raise Unparsable(f"{path}: empty workflow --- nothing to audit")
    jobs = doc.get("jobs")
    if jobs is None:
        raise Unparsable(f"{path}: no 'jobs' mapping --- nothing to audit")
    if not isinstance(jobs, dict) or not jobs:
        raise Unparsable(
            f"{path}: 'jobs' is {type(jobs).__name__}, not a non-empty mapping"
        )
    return jobs


def iter_steps(path: pathlib.Path, doc):
    """Yield ``(job_id, step_index, step)`` for every parsed step in a workflow.

    Steps written as ``- uses: x`` and as ``- name: y`` / ``uses: x`` are the
    same parsed mapping, which is the whole reason to walk structure instead of
    text: the two spellings are indistinguishable here, where a line-anchored
    regex sees only the second (gha#720).

    A job with no ``steps`` is legitimate --- that is what a reusable-workflow
    caller looks like --- but a ``steps`` that is present and not a list of
    mappings is malformed, and is refused rather than skipped.
    """
    for job_id, job in require_jobs(path, doc).items():
        if not isinstance(job, dict):
            raise Unparsable(
                f"{path}: job '{job_id}' is {type(job).__name__}, not a mapping"
            )
        steps = job.get("steps")
        if steps is None:
            continue
        if not isinstance(steps, list):
            raise Unparsable(
                f"{path}: job '{job_id}' has 'steps' as {type(steps).__name__}, "
                "not a list"
            )
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise Unparsable(
                    f"{path}: job '{job_id}' step {index} is "
                    f"{type(step).__name__}, not a mapping"
                )
            yield str(job_id), index, step


def iter_job_inputs(path: pathlib.Path, doc):
    """Yield ``(job_id, block_name, key, value)`` for a job's passed values.

    A reusable-workflow caller hands values down through job-level ``with:``
    and ``secrets:``, neither of which appears in ``steps``.  The regex this
    module replaced matched any line-leading ``token:`` and so covered them
    incidentally; a walk that visits only steps does not, which would be a
    coverage regression rather than a refactor.

    ``secrets: inherit`` is the one legitimate scalar here, so it alone is
    skipped.  Any other scalar --- a string ``with:``, or a ``secrets:`` naming
    anything else --- is malformed, and skipping it would leave a block the
    audit never examined reported as clean.
    """
    for job_id, job in require_jobs(path, doc).items():
        if not isinstance(job, dict):
            raise Unparsable(
                f"{path}: job '{job_id}' is {type(job).__name__}, not a mapping"
            )
        for block_name in ("with", "secrets"):
            block = job.get(block_name)
            if block is None:
                continue
            if block_name == "secrets" and block == "inherit":
                continue
            if not isinstance(block, dict):
                raise Unparsable(
                    f"{path}: job '{job_id}' has '{block_name}' as "
                    f"{type(block).__name__}, not a mapping"
                    + (" (only 'secrets: inherit' is a valid scalar here)"
                       if block_name == "secrets" else "")
                )
            for key, value in block.items():
                yield str(job_id), block_name, str(key), value


def iter_job_uses(path: pathlib.Path, doc):
    """Yield ``(job_id, uses)`` for every reusable-workflow call in a workflow."""
    for job_id, job in require_jobs(path, doc).items():
        if not isinstance(job, dict):
            raise Unparsable(
                f"{path}: job '{job_id}' is {type(job).__name__}, not a mapping"
            )
        uses = job.get("uses")
        if uses is None:
            continue
        if not isinstance(uses, str):
            raise Unparsable(
                f"{path}: job '{job_id}' has 'uses' as {type(uses).__name__}, "
                "not a string"
            )
        yield str(job_id), uses
