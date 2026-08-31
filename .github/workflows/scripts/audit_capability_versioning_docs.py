#!/usr/bin/env python3
"""Audit the repo's own @v1/@v2-per-capability documentation for drift.

Every consumer-facing capability pins the major tag its own reference page
recommends -- ``@v1`` for most, ``@v2`` for a capability that postdates the
frozen pre-``2.0.0`` snapshot (see ``CLAUDE.md``'s "About this repo"
section). That fact is restated, by hand, in several separate places: this
file's own opening paragraph, ``README.md``'s ``## Versioning`` section *and*
its nested ``### Pinning third-party actions`` subsection, and
``website/versioning.qmd`` / ``website/workflows.qmd``. Nothing keeps those
restatements in sync with each other or with reality, and it has drifted on
four separate occasions (gha#181, gha#374, gha#728 rounds 1 and 2) -- see
gha#730, which this script closes.

Two things sank an earlier prototype, and both are why this script is shaped
the way it is rather than the more obvious way.

**The population is derived from ``.github/workflows/*.yml`` file
existence, never from any of the prose lists themselves.** Deriving it from
a list only checks the lists against each other -- which is exactly how
gha#728 slipped through: every list agreed with every other list, and all of
them were wrong. And the population is *not* every capability with an
``examples/*.yml`` stub either: ``assemble-news`` has one, but ships only as
a composite action with no ``.github/workflows/assemble-news.yml`` at all,
so it is correctly absent from every one of these lists -- a whole-file (or
whole-population) presence check would have flagged it as a false gap.

**Ground truth for a capability's *actual* pinned tag comes from its own
``examples/<name>.yml`` stub**, not from any of the prose either: that stub
is what a consumer copy-pastes, so a wrong tag there is self-defeating
independent of anything this script checks. Locating the right line takes
care -- several stubs reference more than one ``Morrison-Lab/gha/...`` path
(an internal composite dispatched from within the same job, a different
capability's workflow entirely), so the match has to be on the *specific*
path segment naming this capability, not "the first self-reference in the
file".

**Each prose location is a hand-registered ``(file, start heading, end
heading)`` region**, not a free-text scan of the whole file. A README
capability *table* entry and a README *versioning-list* entry are two
different sections of the same file that must not be conflated -- the
listed pitfall in gha#730's own body -- so a hit has to be scoped to the
specific paragraph that is *this* list, not anywhere in the file. Both
markers must be found or the region extraction refuses outright: a renamed
heading must not silently narrow this script's blind spot to nothing.

**Only the missing direction is checked, never the reverse.** A region also
names some ``@v1`` capabilities on purpose, to say they were audited and
confirmed unchanged (README's own "were audited in the same pass and found
unchanged since the freeze, so ``@v1`` remains current for them" is such a
sentence) -- a bare presence check cannot tell that clause apart from a
genuine "pin this to ``@v2``" exception without the same brittle clause-level
prose parsing this script exists to avoid, and flagging those names as stale
produced exactly the false-positive noise gha#730's own abandoned prototype
was scrapped over. So this script only ever asks "is a non-``@v1`` capability
listed everywhere it must be", never "is a listed capability still accurate".

**Presence within a region is an exact backtick-delimited token match**,
never a word-boundary regex. Every one of these paragraphs writes capability
names inside single backticks, and relying on that convention sidesteps the
substring trap a regex ``\\bname\\b`` falls into: ``\\bgemini\\b`` matches
inside ``gemini-code-review`` too, since a word boundary sits on both sides
of the substring there. Matching the literal ```` `gemini.yml` ```` or
```` `gemini` ```` token avoids it without needing a lookaround at all.
Two spellings are checked at every site (bare ``name`` and ``name.yml``)
because that is exactly what gha#728's second round missed: the grep used to
find round 1's gaps was keyed to the ``.yml`` spelling, and one of this
repo's own list locations (this file's own "About this repo" paragraph)
names capabilities bare.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from workflow_discovery import skip_if_restored  # noqa: E402

SELF_USES_RE = re.compile(
    r"uses:\s*Morrison-Lab/gha/(?:\.github/(?:workflows|actions)/)?(\S+?)@(v\d+)\b"
)

# (file relative to repo root, start heading line or None for start-of-file,
# end heading line). Both markers are matched by an EXACT stripped-line
# comparison. A region that runs to end-of-file is deliberately not
# supported: an unbounded region is exactly the over-capture failure mode
# gha#730 warns against, so every region names a real closing heading.
REGIONS: list[tuple[str, str | None, str]] = [
    ("README.md", "## Versioning", "### Advancing a major tag"),
    ("README.md", "### Pinning third-party actions", "### Job timeouts"),
    ("website/versioning.qmd", None, "## Widening permissions is a breaking change"),
    ("website/workflows.qmd", "## Versioning {#versioning}", "## Quality checks {#quality-checks}"),
    ("CLAUDE.md", "## About this repo", "### Layout"),
]

BASELINE_TAG = "v1"


class AuditError(Exception):
    """The audit could not run to completion -- never a stand-in for 'clean'."""


def discover_population(repo_root: pathlib.Path) -> dict[str, pathlib.Path]:
    """Map capability name -> its examples/ stub, for every reusable workflow.

    A capability is in scope only when BOTH ``.github/workflows/<name>.yml``
    and ``examples/<name>.yml`` exist. The workflow file is what makes it a
    reusable-workflow capability at all (a composite-only capability like
    ``assemble-news`` has no such file); the example is what supplies ground
    truth for its pinned tag.
    """
    workflows_dir = repo_root / ".github" / "workflows"
    examples_dir = repo_root / "examples"
    if not workflows_dir.is_dir():
        raise AuditError(f"workflows directory not found: {workflows_dir}")
    if not examples_dir.is_dir():
        raise AuditError(f"examples directory not found: {examples_dir}")

    population: dict[str, pathlib.Path] = {}
    for wf in sorted(workflows_dir.glob("*.yml")):
        name = wf.stem
        example = examples_dir / f"{name}.yml"
        if example.is_file():
            population[name] = example

    if not population:
        raise AuditError(
            "no capability had both a .github/workflows/*.yml file and a "
            "matching examples/*.yml stub -- an audit built on this list "
            "would pass having examined nothing"
        )
    return population


def extract_pin(example_path: pathlib.Path, name: str) -> str:
    """Return the major tag `name`'s own example stub pins itself to."""
    text = example_path.read_text(encoding="utf-8")
    found: set[str] = set()
    for match in SELF_USES_RE.finditer(text):
        raw_path, tag = match.group(1), match.group(2)
        stem = raw_path[:-4] if raw_path.endswith(".yml") else raw_path
        if stem == name:
            found.add(tag)

    if not found:
        raise AuditError(
            f"{example_path}: no self-referencing "
            f"'uses: Morrison-Lab/gha/...{name}...@vN' line found"
        )
    if len(found) > 1:
        raise AuditError(
            f"{example_path}: found conflicting self-referencing pins for "
            f"'{name}': {sorted(found)}"
        )
    return found.pop()


def extract_region(repo_root: pathlib.Path, rel_path: str, start: str | None, end: str) -> str:
    """Return the text strictly between two exact heading lines.

    Refuses -- rather than falling back to an empty or whole-file scan --
    when either marker cannot be found, so a renamed heading surfaces as a
    loud audit failure instead of a silently widened blind spot.
    """
    path = repo_root / rel_path
    if not path.is_file():
        raise AuditError(f"{rel_path}: file not found")
    lines = path.read_text(encoding="utf-8").split("\n")

    if start is None:
        start_idx = -1
    else:
        start_idx = next((i for i, line in enumerate(lines) if line.strip() == start), None)
        if start_idx is None:
            raise AuditError(f"{rel_path}: start heading not found: {start!r}")

    end_idx = next(
        (i for i, line in enumerate(lines) if i > start_idx and line.strip() == end),
        None,
    )
    if end_idx is None:
        raise AuditError(f"{rel_path}: end heading not found after start: {end!r}")

    return "\n".join(lines[start_idx + 1 : end_idx])


def is_listed(region_text: str, name: str) -> bool:
    """Whether `name` appears as an exact backtick-delimited token."""
    return f"`{name}`" in region_text or f"`{name}.yml`" in region_text


def run_audit(repo_root: pathlib.Path) -> tuple[list[str], int, int]:
    """Return (findings, capability count, region count)."""
    population = discover_population(repo_root)

    pins = {name: extract_pin(example, name) for name, example in population.items()}

    region_texts: dict[tuple[str, str | None, str], str] = {
        region: extract_region(repo_root, *region) for region in REGIONS
    }

    findings: list[str] = []
    for name, tag in sorted(pins.items()):
        if tag == BASELINE_TAG:
            continue
        for region in REGIONS:
            if is_listed(region_texts[region], name):
                continue
            rel_path, start, end = region
            location = f"{rel_path} ({start or 'start of file'} .. {end})"
            findings.append(
                f"MISSING: '{name}' pins {tag} in its own example stub "
                f"but is not listed in {location}"
            )

    return findings, len(population), len(REGIONS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[3],
        help="Repository root (default: derived from this script's own path).",
    )
    args = parser.parse_args(argv)

    workflows_dir = args.repo_root / ".github" / "workflows"
    if skip_if_restored(workflows_dir, "audit-capability-versioning-docs"):
        return 0

    try:
        findings, capability_count, region_count = run_audit(args.repo_root)
    except AuditError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2

    print(
        f"Checked {capability_count} capabilities against {region_count} "
        f"documented versioning-list regions."
    )
    if findings:
        for finding in findings:
            print(f"::error::{finding}")
        print(f"{len(findings)} finding(s).")
        return 1

    print("No findings -- every non-@v1 capability is listed everywhere it must be.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
