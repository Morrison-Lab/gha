"""The student-copy step that renders each question alone: the first by itself, the rest in parallel."""

import re

from fail import fail
from list_path import list_path
from read_names import read_names

GLOB_RE = re.compile(r"^[A-Za-z0-9_./*?\[\]!-]+$")


def fragment_line(fragments: str, glob: str, parallel: int) -> str:
    if fragments == "all":
        if not GLOB_RE.fullmatch(glob) or glob.startswith(("/", "-")) or ".." in glob.split("/"):
            fail(f"fragment-glob must be a relative path inside the checkout of letters, digits and _ . / * ? [ ] ! -, not {glob!r}")
        listing = f"ls -1d -- {glob}"
    else:
        listing = f"cat -- {list_path('fragments', fragments)}"
    return (
        read_names(listing, "question")
        + 'if [ -z "$files" ]; then echo "No questions to render on their own."; else '
        + "first=${files%%$'\\n'*}; quarto render \"$first\" --to html; "
        + f'printf "%s" "$files" | tail -n +2 | xargs -r -d "\\n" -P {parallel} -I{{}} quarto render {{}} --to html; fi'
    )
