#!/usr/bin/env python3
"""Write a student-copy check's condor-batch steps: both profiles, each question, the check.

Inputs come from the student-copy-render composite's SC_* environment. The first question
renders alone so the pre-render scripts finish first; the rest share no output, so run in parallel.
"""

from __future__ import annotations

import os
import re
import shlex
import sys

GLOB_RE = re.compile(r"^[A-Za-z0-9_./*?\[\]!-]+$")


def fail(message: str) -> None:
    print(f"::error::student-copy-render: {message}", file=sys.stderr)
    raise SystemExit(64)


def list_path(name: str, value: str) -> str:
    """A relative path inside the checkout, quoted for the shell."""
    if not value or value.startswith("/") or ".." in value.split("/") or "\n" in value:
        fail(f"{name} must be 'all' or a relative path inside the checkout, not {value!r}")
    return shlex.quote(value)


def document_lines(documents: str) -> list[str]:
    if documents == "all":
        return ["quarto render", "quarto render --profile solution"]
    path = list_path("documents", documents)
    return [
        f"xargs -r -a {path} -I{{}} quarto render {{}}",
        f"xargs -r -a {path} -I{{}} quarto render {{}} --profile solution",
    ]


def fragment_line(fragments: str, glob: str, parallel: int) -> str:
    if fragments == "all":
        if not GLOB_RE.match(glob):
            fail(f"fragment-glob may hold only path characters and * ? [ ], not {glob!r}")
        listing = f"ls -1 {glob}"
    else:
        listing = f"cat {list_path('fragments', fragments)}"
    return (
        f"set -eu; files=$({listing}); "
        'if [ -z "$files" ]; then echo "No questions to render on their own."; exit 0; fi; '
        'first=$(echo "$files" | head -n 1); quarto render "$first" --to html; '
        f'echo "$files" | tail -n +2 | xargs -r -P {parallel} -I{{}} quarto render {{}} --to html'
    )


def build(env: dict[str, str]) -> list[str]:
    check = env.get("SC_CHECK", "").strip()
    if not check:
        fail("check is required")
    if "\n" in check:
        fail("check must be one line; condor-batch runs each line in its own shell")
    parallel_text = env.get("SC_PARALLEL", "4").strip() or "4"
    if not parallel_text.isdigit() or int(parallel_text) < 1:
        fail(f"parallel must be a whole number of at least 1, not {parallel_text!r}")
    documents = env.get("SC_DOCUMENTS", "all").strip() or "all"
    fragments = env.get("SC_FRAGMENTS", "all").strip() or "all"
    glob = env.get("SC_FRAGMENT_GLOB", "exercises/*/_exr-*.qmd").strip()
    return [
        *document_lines(documents),
        fragment_line(fragments, glob, int(parallel_text)),
        check,
    ]


def main() -> int:
    print("\n".join(build(dict(os.environ))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
