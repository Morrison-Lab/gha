"""Tests for `preview/_workflow_annotations.py`.

Workflow commands are line-oriented, so an unescaped multi-line message is
truncated at its first line in the rendered annotation -- and git's rejection
text, which is the message most worth reading, is always several lines.
"""

import pytest


@pytest.fixture(scope="session")
def annotations(detector):  # detector's import puts `preview/` on sys.path
    import _workflow_annotations

    return _workflow_annotations


def test_a_newline_is_escaped(annotations):
    assert annotations.annotate("error", "first\nsecond") == "::error::first%0Asecond"


def test_a_carriage_return_is_escaped(annotations):
    assert annotations.escape_annotation("a\r\nb") == "a%0D%0Ab"


def test_percent_is_escaped_first(annotations):
    """Escaping `%` after the newlines would re-escape the escapes, turning a
    literal `%0A` in the message into a line break."""
    assert annotations.escape_annotation("100% of\nruns") == "100%25 of%0Aruns"
    assert annotations.escape_annotation("%0A") == "%250A"


def test_a_plain_message_is_unchanged(annotations):
    assert annotations.annotate("notice", "nothing special") == "::notice::nothing special"
