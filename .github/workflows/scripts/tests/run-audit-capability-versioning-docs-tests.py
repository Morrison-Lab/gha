#!/usr/bin/env python3
"""Offline tests for audit_capability_versioning_docs.py (gha#730).

Builds a small fixture repo tree per case rather than reusing this repo's own
--- the real tree is what the live self-check in `_selftest.yml` exercises,
and a fixture lets each case isolate one behaviour (a missing region, an
ambiguous self-reference, a substring trap) without depending on this repo's
current documentation state staying exactly as it is today.

Region fixtures are built from the module's own ``REGIONS`` registry, not a
second hard-coded copy of it --- a second copy is exactly the kind of
duplicated-list drift this whole capability exists to catch, applied to its
own test.

Usage::

    python3 run-audit-capability-versioning-docs-tests.py
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import audit_capability_versioning_docs as audit  # noqa: E402

failures = 0
cases = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures, cases
    cases += 1
    if condition:
        print(f"OK   {label}")
    else:
        print(f"::error::{label}{': ' + detail if detail else ''}", file=sys.stderr)
        failures += 1


def write(root: pathlib.Path, rel_path: str, body: str) -> pathlib.Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def build_fixture(root: pathlib.Path, capabilities: dict[str, tuple[str, set[int]]]) -> None:
    """Write a minimal repo tree.

    ``capabilities`` maps a capability name to ``(tag, region_indices)``,
    where ``region_indices`` are positions into ``audit.REGIONS`` the
    capability's own ``.yml`` token should appear inside. Every named
    capability gets a matching ``.github/workflows/<name>.yml`` and
    ``examples/<name>.yml`` self-reference at the given tag.
    """
    for name, (tag, _regions) in capabilities.items():
        write(root, f".github/workflows/{name}.yml", "name: fixture\njobs: {}\n")
        write(
            root,
            f"examples/{name}.yml",
            f"uses: Morrison-Lab/gha/.github/workflows/{name}.yml@{tag}\n",
        )

    by_file: dict[str, list[tuple[int, str | None, str]]] = defaultdict(list)
    for idx, (rel_path, start, end) in enumerate(audit.REGIONS):
        by_file[rel_path].append((idx, start, end))

    for rel_path, regions_in_file in by_file.items():
        lines: list[str] = []
        for idx, start, end in regions_in_file:
            if start is not None:
                lines.append(start)
            for name, (_tag, region_indices) in capabilities.items():
                if idx in region_indices:
                    lines.append(f"`{name}.yml` is mentioned here.")
            lines.append(end)
        write(root, rel_path, "\n".join(lines) + "\n")


def run(root: pathlib.Path) -> tuple[list[str], int]:
    """Run the audit, muting its own printed output, return (findings, exit code)."""
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        try:
            findings, _population, _regions = audit.run_audit(root)
            return findings, (1 if findings else 0)
        except audit.AuditError as exc:
            return [str(exc)], 2


def run_case(capabilities: dict[str, tuple[str, set[int]]]) -> tuple[list[str], int]:
    """Build a fresh fixture tree for one case's capabilities and run the audit.

    A fresh `TemporaryDirectory` per case, not a shared one reused across
    several `build_fixture` calls -- a shared tree leaks the previous case's
    capability files forward (`discover_population` scans everything under
    it), so a later "nothing should be flagged" case would still see an
    earlier case's leftover, unrelated finding.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        build_fixture(root, capabilities)
        return run(root)


def main() -> int:
    all_region_indices = set(range(len(audit.REGIONS)))

    # -------------------------------------------------- clean, v2 listed everywhere
    findings, code = run_case({"foo": ("v2", all_region_indices)})
    check("v2 capability listed in every region -> no findings", code == 0 and not findings, str(findings))

    # -------------------------------------------------- v2 missing from one region
    missing_one = all_region_indices - {2}
    findings, code = run_case({"foo": ("v2", missing_one)})
    check("v2 capability missing from one region -> exactly one finding", code == 1 and len(findings) == 1, str(findings))
    check(
        "the finding names the region it's missing from",
        findings and audit.REGIONS[2][0] in findings[0],
        str(findings),
    )

    # -------------------------------------------------- v2 missing from every region
    findings, code = run_case({"foo": ("v2", set())})
    check(
        "v2 capability listed nowhere -> one finding per region",
        code == 1 and len(findings) == len(audit.REGIONS),
        str(findings),
    )

    # -------------------------------------------------- v1 never needs listing
    findings, code = run_case({"bar": ("v1", set())})
    check("v1 capability listed nowhere -> no findings (v1 is the baseline)", code == 0 and not findings, str(findings))

    # v1 being listed anyway (a stale-but-harmless mention) is not flagged
    # either -- this script only ever checks the missing direction (see
    # its own module docstring for why the reverse produced false
    # positives against real prose).
    findings, code = run_case({"bar": ("v1", all_region_indices)})
    check("v1 capability listed everywhere anyway -> still no findings", code == 0 and not findings, str(findings))

    # -------------------------------------------------- two capabilities, independent
    findings, code = run_case(
        {
            "foo": ("v2", all_region_indices),
            "baz": ("v2", all_region_indices - {0}),
        }
    )
    check(
        "one clean + one with a gap -> exactly one finding, for the right capability",
        code == 1 and len(findings) == 1 and "'baz'" in findings[0] and "'foo'" not in findings[0],
        str(findings),
    )

    # ------------------------------------------------------------ is_listed: substring trap
    # `\bgemini\b` would match inside "gemini-code-review" too, since a word
    # boundary sits on both sides of the substring there -- exactly the trap
    # an exact backtick-token match exists to avoid (gha#730's own module
    # docstring).
    region_with_only_the_longer_name = "See `gemini-code-review.yml` for details."
    check(
        "is_listed does not mistake a longer name for the shorter one it contains",
        audit.is_listed(region_with_only_the_longer_name, "gemini") is False,
    )
    check(
        "is_listed still finds the longer name itself",
        audit.is_listed(region_with_only_the_longer_name, "gemini-code-review") is True,
    )
    check(
        "is_listed accepts the bare backtick form too (CLAUDE.md's own spelling)",
        audit.is_listed("Pin `gemini` to `@v2`.", "gemini") is True,
    )

    # ------------------------------------------------------------ extract_pin
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        # A stub with more than one self-reference must pick the line naming
        # THIS capability, not the first Morrison-Lab/gha/... line in the
        # file (claude-code-review.yml and report-failure.yml both do this
        # for real, referencing an internal composite / a different
        # capability's workflow ahead of their own).
        multi = write(
            root,
            "multi.yml",
            "uses: Morrison-Lab/gha/.github/actions/parse-workflow-ref@v2\n"
            "uses: Morrison-Lab/gha/.github/workflows/quarto-publish.yml@v2\n"
            "uses: Morrison-Lab/gha/.github/workflows/multi.yml@v2\n",
        )
        check("extract_pin picks the line naming this capability, not the first self-reference", audit.extract_pin(multi, "multi") == "v2")

        # A composite-path self-reference (no .github/workflows/ prefix, no
        # .yml suffix) must resolve too -- check-code-similarity's example
        # references its composite directly rather than its reusable-workflow
        # wrapper.
        composite = write(root, "composite.yml", "uses: Morrison-Lab/gha/composite@v2\n")
        check("extract_pin resolves a bare root-composite self-reference", audit.extract_pin(composite, "composite") == "v2")

        none_found = write(root, "none.yml", "uses: Morrison-Lab/gha/.github/workflows/other.yml@v1\n")
        try:
            audit.extract_pin(none_found, "none")
            check("extract_pin raises when no self-reference names this capability", False)
        except audit.AuditError:
            check("extract_pin raises when no self-reference names this capability", True)

        ambiguous = write(
            root,
            "ambiguous.yml",
            "uses: Morrison-Lab/gha/.github/workflows/ambiguous.yml@v1\n"
            "uses: Morrison-Lab/gha/.github/workflows/ambiguous.yml@v2\n",
        )
        try:
            audit.extract_pin(ambiguous, "ambiguous")
            check("extract_pin raises on two conflicting pins for the same capability", False)
        except audit.AuditError:
            check("extract_pin raises on two conflicting pins for the same capability", True)

    # ------------------------------------------------------------ discover_population
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        write(root, ".github/workflows/has-both.yml", "x\n")
        write(root, "examples/has-both.yml", "x\n")
        write(root, ".github/workflows/workflow-only.yml", "x\n")  # no matching example
        write(root, "examples/example-only.yml", "x\n")  # no matching workflow (assemble-news's own shape)
        population = audit.discover_population(root)
        check("a capability with both a workflow file and an example is in the population", "has-both" in population)
        check(
            "a workflow file with no matching example is excluded",
            "workflow-only" not in population,
        )
        check(
            "an example with no matching .github/workflows/*.yml is excluded (the assemble-news shape)",
            "example-only" not in population,
        )

        empty = pathlib.Path(tmp) / "empty-tree"
        (empty / ".github" / "workflows").mkdir(parents=True)
        (empty / "examples").mkdir(parents=True)
        try:
            audit.discover_population(empty)
            check("an empty overlap raises rather than returning an empty population", False)
        except audit.AuditError:
            check("an empty overlap raises rather than returning an empty population", True)

    # ------------------------------------------------------------ extract_region
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        write(root, "doc.md", "## Start\ncontent\n## End\ntrailer\n")
        text = audit.extract_region(root, "doc.md", "## Start", "## End")
        check("extract_region returns exactly the text between the two markers", text.strip() == "content")

        try:
            audit.extract_region(root, "doc.md", "## Nope", "## End")
            check("extract_region raises when the start heading is not found", False)
        except audit.AuditError:
            check("extract_region raises when the start heading is not found", True)

        try:
            audit.extract_region(root, "doc.md", "## Start", "## Nope")
            check("extract_region raises when the end heading is not found", False)
        except audit.AuditError:
            check("extract_region raises when the end heading is not found", True)

        write(root, "no-start-marker.md", "front matter\n## End\n")
        text = audit.extract_region(root, "no-start-marker.md", None, "## End")
        check("extract_region with start=None runs from the top of the file", "front matter" in text)

    print(f"\n{cases - failures}/{cases} checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
