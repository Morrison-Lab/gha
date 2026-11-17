"""The student-copy step that renders each question alone: the first by itself, the rest in parallel."""

import re

from fail import fail
from list_path import list_path

GLOB_RE = re.compile(r"^[A-Za-z0-9_./*?\[\]!-]+$")

# A name starting with - would reach quarto as an option, so the line refuses it.
DASH_GUARD = (
    'if printf "%s\\n" "$files" | grep -q "^-"; then '
    'echo "A question to render starts with -: rename it." >&2; exit 1; fi; '
)


def fragment_line(fragments: str, glob: str, parallel: int) -> str:
    if fragments == "all":
        if not GLOB_RE.match(glob) or glob.startswith(("/", "-")) or ".." in glob.split("/"):
            fail(f"fragment-glob must be a relative path inside the checkout of path characters and * ? [ ], not {glob!r}")
        listing = f"ls -1d -- {glob}"
    else:
        listing = f"tr -d '\\r' < {list_path('fragments', fragments)}"
    return (
        f"set -euo pipefail; files=$({listing}); "
        'if [ -z "$files" ]; then echo "No questions to render on their own."; exit 0; fi; '
        f"{DASH_GUARD}"
        'first=$(printf "%s\\n" "$files" | head -n 1); quarto render "$first" --to html; '
        f'printf "%s\\n" "$files" | tail -n +2 | xargs -r -d "\\n" -P {parallel} -I{{}} quarto render {{}} --to html'
    )
