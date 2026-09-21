#!/usr/bin/env python3
"""Audit example caller stubs, workflows, and documentation for duplicate mapping keys (gha#839).

A consumer copying a stub from `examples/` or `website/reference/` follows
documented comments to enable optional inputs. If a stub carries an active `with:`
mapping and also a second, commented `# with:` key directly beneath it,
uncommenting per instructions silently duplicates the `with:` key on the job.

GitHub Actions and PyYAML's standard SafeLoader silently discard all but the
last occurrence of a duplicate key in a mapping. When that happens, real job
inputs (such as `pr-number`, `endpoint-url`, or `model`) are dropped without
error, running the workflow with missing configuration rather than failing.

This audit:
1. Validates every workflow file under `examples/` and `.github/workflows/`, as well
   as YAML code blocks in `website/reference/*.qmd`, using a strict,
   duplicate-key-rejecting YAML loader (`StrictSafeLoader`).
2. Simulates uncommenting `# with:` lines in caller jobs to assert that no
   job ends up with duplicate `with:` keys.

Usage::

    python3 audit_example_stubs.py [--examples-dir DIR] [--workflows-dir DIR] [--docs-dir DIR]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from workflow_discovery import (  # noqa: E402
    discover_workflows,
    skip_if_restored,
)

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    print(
        "::error::PyYAML is required to parse workflows but is not "
        "installed (install it with `python3 -m pip install pyyaml`).",
        file=sys.stderr,
    )
    raise SystemExit(2) from None


class StrictSafeLoader(yaml.SafeLoader):
    """YAML SafeLoader that raises an error when duplicate keys are encountered."""


def _reject_duplicates(loader: yaml.Loader, node: yaml.MappingNode, deep: bool = False):
    seen: set[object] = set()
    for k, _ in node.value:
        key = loader.construct_object(k, deep=deep)
        if key in seen:
            raise yaml.YAMLError(f"duplicate key {key!r}")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _reject_duplicates,
)


def audit_file_content(path: pathlib.Path, text: str) -> list[str]:
    """Audit a workflow or example stub text for duplicate keys and uncommentable with blocks.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    # 1. As-is validation with StrictSafeLoader (catches any existing duplicate keys)
    try:
        yaml.load(text, Loader=StrictSafeLoader)
    except yaml.YAMLError as exc:
        errors.append(f"{path}: strict YAML parse error: {exc}")
        return errors
    except Exception as exc:
        errors.append(f"{path}: failed to read or parse YAML: {exc}")
        return errors

    # 2. Simulate uncommenting '# with:' lines and re-parse with StrictSafeLoader
    if re.search(r"^(\s*)#\s*with:\s*$", text, re.MULTILINE):
        uncommented = re.sub(r"^(\s*)#\s*with:\s*$", r"\g<1>with:", text, flags=re.MULTILINE)
        try:
            yaml.load(uncommented, Loader=StrictSafeLoader)
        except yaml.YAMLError as exc:
            errors.append(f"{path}: uncommenting '# with:' creates duplicate key: {exc}")

    return errors


def resolve_includes(path: pathlib.Path, text: str) -> str:
    """Resolve Quarto `{{< include rel_path >}}` directives relative to path.parent."""
    def repl(m: re.Match[str]) -> str:
        rel = m.group(1).strip()
        inc = (path.parent / rel).resolve()
        if inc.is_file():
            return inc.read_text(encoding="utf-8")
        return m.group(0)

    return re.sub(r"\{\{<\s*include\s+([^\s>]+)\s*>\}\}", repl, text)


def extract_qmd_yaml_blocks(path: pathlib.Path, text: str) -> list[tuple[int, str]]:
    """Extract (start_line, yaml_text) for each YAML code block in a Quarto/Markdown document."""
    blocks: list[tuple[int, str]] = []
    pattern = re.compile(r"^```(?:ya?ml)\s*\r?\n(.*?)\r?\n```\s*$", re.MULTILINE | re.DOTALL)
    for m in pattern.finditer(text):
        start_line = text[:m.start()].count("\n") + 1
        block_text = resolve_includes(path, m.group(1))
        blocks.append((start_line, block_text))
    return blocks


def audit_files(files: list[pathlib.Path]) -> list[str]:
    all_errors: list[str] = []
    for file_path in files:
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            all_errors.append(f"{file_path}: could not read file: {exc}")
            continue

        if file_path.suffix.lower() in {".qmd", ".md"}:
            blocks = extract_qmd_yaml_blocks(file_path, text)
            for line_no, block_content in blocks:
                errors = audit_file_content(pathlib.Path(f"{file_path}:{line_no}"), block_content)
                all_errors.extend(errors)
        else:
            errors = audit_file_content(file_path, text)
            all_errors.extend(errors)

    return all_errors


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--examples-dir",
        type=pathlib.Path,
        default=pathlib.Path("examples"),
        help="Directory containing example stub files (default: examples).",
    )
    parser.add_argument(
        "--workflows-dir",
        type=pathlib.Path,
        default=pathlib.Path(".github/workflows"),
        help="Directory containing workflow files (default: .github/workflows).",
    )
    parser.add_argument(
        "--docs-dir",
        type=pathlib.Path,
        default=pathlib.Path("website/reference"),
        help="Directory containing documentation reference pages (default: website/reference).",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=pathlib.Path,
        help="Specific files to audit (defaults to all files in --examples-dir, --workflows-dir, and --docs-dir).",
    )

    args = parser.parse_args(argv)

    if skip_if_restored(args.workflows_dir, "example stubs duplicate keys audit"):
        return

    files_to_check: list[pathlib.Path] = []
    if args.files:
        files_to_check = args.files
    else:
        if args.examples_dir.is_dir():
            files_to_check.extend(discover_workflows(args.examples_dir))
        if args.workflows_dir.is_dir():
            files_to_check.extend(discover_workflows(args.workflows_dir))
        if args.docs_dir and args.docs_dir.is_dir():
            files_to_check.extend(sorted(args.docs_dir.glob("*.qmd")))

    if not files_to_check:
        print("::error::No files found to audit.", file=sys.stderr)
        sys.exit(2)

    errors = audit_files(files_to_check)
    if errors:
        print(f"Found {len(errors)} duplicate key or uncommentable 'with:' errors:", file=sys.stderr)
        for err in errors:
            print(f"::error::{err}", file=sys.stderr)
        sys.exit(1)

    print(
        f"All {len(files_to_check)} files passed strict YAML and uncommentable 'with:' checks cleanly."
    )


if __name__ == "__main__":
    main()
