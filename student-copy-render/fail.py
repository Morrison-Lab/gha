"""Stop student_copy_steps.py on a bad input, with an annotation and the usage exit code."""

import sys


def fail(message: str) -> None:
    print(f"::error::student-copy-render: {message}", file=sys.stderr)
    raise SystemExit(64)
