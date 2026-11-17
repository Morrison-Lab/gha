"""Check a list-file input of student_copy_steps.py: a relative path inside the checkout."""

import shlex

from fail import fail


def list_path(name: str, value: str) -> str:
    """Return the path quoted for the shell. A leading - would read as an option."""
    if not value or value.startswith(("/", "-")) or ".." in value.split("/") or "\n" in value:
        fail(f"{name} must be 'all' or a relative path inside the checkout, not {value!r}")
    return shlex.quote(value)
