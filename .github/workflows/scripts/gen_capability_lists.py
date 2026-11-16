#!/usr/bin/env python3
"""Write the website's capability lists from the files each capability owns.

Adding a check used to mean editing about ten hand-kept lists (gha#1862):
the `@v2`/`@v3` lists, the read-only list, and the workflow table rows.
Each new check touched every one of those files, so it could not fit under
`check-pr-size`'s 10-file cap. The facts are already on disk, and the audits
already derive them from there, so this script writes the lists at render
time into git-ignored include files instead:

- a capability is a reusable workflow `.github/workflows/<name>.yml` with an
  `examples/<name>.yml` stub (`discover_population` in
  `audit_capability_versioning_docs.py`);
- its major tag is the one that stub pins (`extract_pin` there);
- it is read-only when every job's effective permissions are `read` or
  `none` (`read_only_workflows` in `tests/run-permissions-docs-tests.py`);
- its purpose is the `description:` in the front matter of
  `website/reference/<name>.qmd`, or else that page's first sentence;
- its inputs are the workflow's `workflow_call` inputs, less the runner
  plumbing every workflow takes (`COMMON_INPUTS`).

Nothing here is a second copy of a rule: the two helpers are imported, so a
fix to either reaches the lists too.

Outputs, under `website/_generated/` by default:

- `tag-<major>.md`: the backticked workflow file names pinned at that tag,
  one file per tag the stubs use;
- `readonly.md`: the backticked names of the read-only capabilities;
- `workflows-table.md`: the catalog table, header included.

Usage::

    python3 gen_capability_lists.py [--repo-root DIR] [--out DIR]

Quarto runs it as a `pre-render` step from `website/`.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent

# Inputs every reusable workflow takes for its runner, which say nothing about
# what the capability does.
COMMON_INPUTS = {"runs-on", "python-version"}


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


versions = _load("audit_capability_versioning_docs",
                 HERE / "audit_capability_versioning_docs.py")
permissions = _load("run_permissions_docs_tests",
                    HERE / "tests" / "run-permissions-docs-tests.py")


def purpose(page: pathlib.Path) -> str:
    """A reference page's `description:`, else its first sentence.

    The front-matter field lets a page state its one-line purpose for the
    catalog without the catalog keeping a copy of it.
    """
    text = page.read_text(encoding="utf-8")
    front = ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        front, text = (text[3:end], text[end + 4:]) if end != -1 else ("", "")
    if front:
        import yaml  # load_yaml has already required PyYAML by this point
        meta = yaml.safe_load(front)
        if isinstance(meta, dict) and str(meta.get("description") or "").strip():
            return " ".join(str(meta["description"]).split())
    return first_sentence(text)


# Abbreviations whose dot does not end a sentence.
ABBREVIATIONS = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf)\.$")


def first_sentence(text: str) -> str:
    """The first sentence of the first prose paragraph of a page body."""
    paragraph = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if not paragraph and stripped.startswith(("#", ":::", "<!--", "{{<", "|", "```")):
            continue
        paragraph.append(stripped)
    prose = " ".join(paragraph)
    for match in re.finditer(r"(?<=[.!?])\s+", prose):
        if not ABBREVIATIONS.search(prose[:match.start()]):
            return prose[:match.start()]
    return prose


def workflow_inputs(workflow: pathlib.Path) -> list[str]:
    doc = permissions.load_yaml(workflow)
    triggers = doc.get(True, doc.get("on")) if isinstance(doc, dict) else None
    call = triggers.get("workflow_call") if isinstance(triggers, dict) else None
    inputs = (call or {}).get("inputs") or {}
    return [name for name in inputs if name not in COMMON_INPUTS]


def table_row(name: str, repo_root: pathlib.Path) -> str:
    workflow = repo_root / ".github" / "workflows" / f"{name}.yml"
    page = repo_root / "website" / "reference" / f"{name}.qmd"
    if page.is_file():
        link = f"[`{name}.yml`](reference/{name}.qmd)"
        text = purpose(page)
    else:
        link = f"`{name}.yml`"
        doc = permissions.load_yaml(workflow)
        text = str(doc.get("name", "")) if isinstance(doc, dict) else ""
    inputs = ", ".join(f"`{i}`" for i in workflow_inputs(workflow))
    cells = [link, text.replace("|", "\\|"), inputs]
    return "| " + " | ".join(cells) + " |"


def backticked(names) -> str:
    return ", ".join(f"`{n}`" for n in sorted(names))


def generate(repo_root: pathlib.Path) -> dict[str, str]:
    """Map output file name -> contents."""
    population = versions.discover_population(repo_root)
    by_tag: dict[str, list[str]] = {}
    for name, example in population.items():
        by_tag.setdefault(versions.extract_pin(example, name), []).append(f"{name}.yml")
    read_only = permissions.read_only_workflows(repo_root / ".github" / "workflows")
    rows = [table_row(name, repo_root) for name in sorted(population)]
    out = {f"tag-{tag}.md": backticked(names) + "\n" for tag, names in by_tag.items()}
    out["readonly.md"] = backticked(n for n in read_only if n in population) + "\n"
    out["workflows-table.md"] = "\n".join(
        ["| Workflow | Purpose | Key inputs |", "| --- | --- | --- |", *rows]) + "\n"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=pathlib.Path, default=HERE.parents[2])
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    out_dir = args.out or repo_root / "website" / "_generated"
    try:
        files = generate(repo_root)
    except versions.AuditError as exc:
        print(f"::error::gen_capability_lists: {exc}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")
    print(f"gen_capability_lists: wrote {len(files)} file(s) to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
