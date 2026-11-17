"""Stop student_copy_steps.py on a bad input, with an annotation and the usage exit code."""

import sys


def fail(message: str) -> None:
    print(f"::error::student-copy-render: {message.replace('%', '%25').replace(chr(13), '%0D').replace(chr(10), '%0A')}", file=sys.stderr)
    raise SystemExit(64)
