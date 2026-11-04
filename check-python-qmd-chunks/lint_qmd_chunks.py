"""Lint the Python chunks of Quarto files with the lab's Ruff configuration.

The chunks of one `.qmd` file share a Python session, so they are joined
into one source file, in document order, and linted together.
A finding is reported at its line in the `.qmd` file.

Usage:
    python3 lint_qmd_chunks.py [--config ruff.toml] FILE.qmd ...

Exit status is 1 when any file has a finding.
Formatting is not checked: `ruff format` deletes the trailing semicolons
that lds puts after plotting calls to hide their return values.

Chunks are lecture snippets, not modules, so these rules are not applied:

- D1: missing docstrings.
- E402 and I001: imports sit in the chunk that needs them, not at the top.
- B018: a bare expression displays its value.
- E703: a trailing semicolon hides a call's return value, as lds requires.
- F821 and F401: a subfile shares names with the page that includes it,
  and R chunks supply `r`, so a name can be defined or used elsewhere.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHUNK_IGNORES = "D1,E402,I001,B018,E703,F821,F401"
OPEN_FENCE = re.compile(r"^(\s*)(`{3,})\{python[ ,}]")


def extract_chunks(text):
    """Return (source, line_map) for the Python chunks in a qmd text.

    line_map[i] is the 1-based qmd line of line i + 1 of the source.
    Chunks are separated by two blank lines.
    """
    source = []
    line_map = []
    fence = None
    indent = ""
    for number, line in enumerate(text.split("\n"), start=1):
        if fence is None:
            opened = OPEN_FENCE.match(line)
            if opened:
                indent = opened.group(1)
                fence = opened.group(2)
                if source:
                    source.extend(["", ""])
                    line_map.extend([number, number])
            continue
        if line.strip() == fence:
            fence = None
            continue
        # A chunk inside a callout or list item is indented as a whole.
        source.append(line.removeprefix(indent))
        line_map.append(number)
    return "\n".join(source) + "\n", line_map


def run_ruff(args):
    """Run ruff with the arguments and return the completed process."""
    return subprocess.run(
        ["ruff", *args], capture_output=True, text=True, check=False
    )


def lint_file(path, config):
    """Return the findings for one qmd file as printable lines."""
    source, line_map = extract_chunks(Path(path).read_text(encoding="utf-8"))
    if not any(line.strip() for line in source.split("\n")):
        return []
    problems = []
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "chunks.py"
        target.write_text(source, encoding="utf-8")
        check = run_ruff(
            [
                "check",
                "--config",
                str(config),
                "--ignore",
                CHUNK_IGNORES,
                "--output-format",
                "json",
                "--no-cache",
                str(target),
            ]
        )
        if check.returncode not in (0, 1):
            sys.exit(f"ruff check failed: {check.stderr}")
        for finding in json.loads(check.stdout or "[]"):
            row = finding["location"]["row"]
            problems.append(
                f"{path}:{line_map[row - 1]}: {finding['code']} "
                f"{finding['message']}"
            )
    return problems


def main():
    """Lint the files named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", default="ruff.toml")
    parser.add_argument("files", nargs="+")
    options = parser.parse_args()
    problems = []
    for path in options.files:
        problems.extend(lint_file(path, options.config))
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
