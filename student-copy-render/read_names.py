"""Read names into $files, CR and blank lines dropped first, refusing one quarto would read as an option."""


def read_names(listing: str, what: str) -> str:
    # A here-string, not a pipe, so grep -q's early exit cannot fail the line under pipefail.
    return (
        f"set -euo pipefail; files=$({listing} | tr -d '\\r' | sed '/^$/d'); "
        f'if grep -q "^-" <<< "$files"; then echo "A {what} starts with -: rename it." >&2; exit 1; fi; '
    )
