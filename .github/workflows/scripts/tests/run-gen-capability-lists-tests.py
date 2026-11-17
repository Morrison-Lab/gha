#!/usr/bin/env python3
"""Offline tests for gen_capability_lists.py (gha#1862).

Each case builds a small fixture tree, so it isolates one behaviour; the last
case runs the generator over this repo itself, which is what the website's
`pre-render` step does on every render.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "gen_capability_lists.py"
spec = importlib.util.spec_from_file_location("gen_capability_lists", SCRIPT)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

WORKFLOW = """name: {title}
on:
  workflow_call:
    inputs:
      runs-on:
        type: string
      globs:
        type: string
      fail:
        type: boolean
jobs:
  check:
    runs-on: ubuntu-latest
    permissions:
      contents: {perm}
    steps:
      - run: true
"""

STUB = """jobs:
  check:
    uses: Morrison-Lab/gha/.github/workflows/{name}.yml@{tag}
"""


def build(root: pathlib.Path) -> None:
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "examples").mkdir()
    (root / "website" / "reference").mkdir(parents=True)
    caps = {
        "check-alpha": ("v3", "read", "Alpha (reusable)"),
        "check-beta": ("v2", "write", "Beta (reusable)"),
        "check-gamma": ("v3", "read", "Gamma (reusable)"),
        "check-delta": ("v3", "read", "Delta (reusable)"),
    }
    for name, (tag, perm, title) in caps.items():
        (root / ".github" / "workflows" / f"{name}.yml").write_text(
            WORKFLOW.format(title=title, perm=perm))
        (root / "examples" / f"{name}.yml").write_text(STUB.format(name=name, tag=tag))
    # A workflow with no stub is not a capability.
    (root / ".github" / "workflows" / "internal.yml").write_text(
        WORKFLOW.format(title="Internal", perm="read"))
    (root / "website" / "reference" / "check-alpha.qmd").write_text(
        '---\ntitle: "check-alpha.yml"\ndescription: >-\n  Flag an alpha | with a pipe.\n---\n\n'
        "The body says something else. More.\n")
    (root / "website" / "reference" / "check-beta.qmd").write_text(
        '---\ntitle: "check-beta.yml"\n---\n\n## Heading\n\n'
        "Flag a beta, e.g. this one. Second sentence.\n")
    (root / "website" / "reference" / "check-delta.qmd").write_text(
        '---\ntitle: "check-delta.yml"\n---\n\n'
        "Flag what [beta](check-beta.qmd), [this](#use), [up](../index.qmd), "
        "[web](https://example.org) and [root](/x.qmd) miss.\n")


def test_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        build(root)
        out = gen.generate(root)
        assert out["tag-v3.md"] == ("`check-alpha.yml`, `check-delta.yml`, "
                                    "`check-gamma.yml`\n"), out["tag-v3.md"]
        assert out["tag-v2.md"] == "`check-beta.yml`\n", out["tag-v2.md"]
        assert out["readonly.md"] == ("`check-alpha`, `check-delta`, "
                                      "`check-gamma`\n"), out["readonly.md"]
        rows = out["workflows-table.md"].splitlines()
        assert rows[0] == "| Workflow | Purpose | Key inputs |"
        assert len(rows) == 6, rows
        # The description wins over the body, and a pipe is escaped.
        assert rows[2] == ("| [`check-alpha.yml`](reference/check-alpha.qmd) | "
                           "Flag an alpha \\| with a pipe. | `globs`, `fail` |"), rows[2]
        # No description: the first sentence, past a heading and an abbreviation.
        assert rows[3] == ("| [`check-beta.yml`](reference/check-beta.qmd) | "
                           "Flag a beta, e.g. this one. | `globs`, `fail` |"), rows[3]
        # Relative links resolve from website/, not from reference/.
        assert rows[4] == ("| [`check-delta.yml`](reference/check-delta.qmd) | "
                           "Flag what [beta](reference/check-beta.qmd), "
                           "[this](reference/check-delta.qmd#use), [up](reference/../index.qmd), "
                           "[web](https://example.org) and [root](/x.qmd) miss. | "
                           "`globs`, `fail` |"), rows[4]
        # No reference page: no link, and the workflow's name.
        assert rows[5] == "| `check-gamma.yml` | Gamma (reusable) | `globs`, `fail` |", rows[4]
        assert "internal" not in out["workflows-table.md"]


def test_main_writes_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        build(root)
        out_dir = root / "out"
        assert gen.main(["--repo-root", str(root), "--out", str(out_dir)]) == 0
        names = sorted(p.name for p in out_dir.iterdir())
        assert names == ["readonly.md", "tag-v2.md", "tag-v3.md", "workflows-table.md"], names


def test_empty_tree_fails_rather_than_writing_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "examples").mkdir()
        assert gen.main(["--repo-root", str(root), "--out", str(root / "out")]) == 1


def test_this_repo() -> None:
    root = HERE.parents[3]
    out = gen.generate(root)
    table = out["workflows-table.md"]
    population = gen.versions.discover_population(root)
    assert len(table.splitlines()) == len(population) + 2
    for name in population:
        assert f"`{name}.yml`" in table, name
    for line in table.splitlines()[2:]:
        assert line.count(" | ") >= 2 and line.split(" | ")[1].strip(), line


def main() -> int:
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    print(f"{len(tests)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
