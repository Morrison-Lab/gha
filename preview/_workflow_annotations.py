"""Emit GitHub Actions workflow commands correctly.

Shared by `detect-changed-chapters.py` and `add-home-banner.py` rather than
written twice, the way `generate-altdoc-landing-page`'s two generators share
`_site_output.py`.

Workflow commands are line-oriented, so a message carrying a newline -- git's
own multi-line rejection text, for instance -- renders as an annotation
truncated at its first line, losing exactly the part that says what went wrong.
The escaping below is what GitHub's own runner expects; `%` goes first, or it
would re-escape the escapes.
"""


def escape_annotation(message):
    return (
        str(message)
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def annotate(level, message):
    """Return a `::level::message` workflow command with the message escaped."""
    return f"::{level}::{escape_annotation(message)}"
