"""The student-copy step that renders each question alone: the first by itself, the rest in parallel."""

import re

from fail import fail
from list_path import list_path

GLOB_RE = re.compile(r"^[A-Za-z0-9_./*?\[\]!-]+$")


def fragment_line(fragments: str, glob: str, parallel: int) -> str:
    if fragments == "all":
        if not GLOB_RE.match(glob) or glob.startswith("/") or ".." in glob.split("/"):
            fail(f"fragment-glob must be a relative path inside the checkout of path characters and * ? [ ], not {glob!r}")
        listing = f"ls -1 {glob}"
    else:
        listing = f"cat {list_path('fragments', fragments)}"
    return (
        f"set -eu; files=$({listing}); "
        'if [ -z "$files" ]; then echo "No questions to render on their own."; exit 0; fi; '
        'first=$(echo "$files" | head -n 1); quarto render "$first" --to html; '
        f'echo "$files" | tail -n +2 | xargs -r -P {parallel} -I{{}} quarto render {{}} --to html'
    )
