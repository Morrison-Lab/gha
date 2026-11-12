"""Unit tests for check-common/mdmask.py (gha#1856)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mdmask  # noqa: E402


def test_code_span_is_blanked_and_length_kept():
    line = "Write `the code` here"
    masked, open_ = mdmask.mask_markdown_line(line, False)
    assert masked == "Write " + " " * 10 + " here"
    assert len(masked) == len(line) and not open_


def test_double_backtick_span_is_blanked():
    masked, _ = mdmask.mask_markdown_line("a ``x ` y`` b", False)
    assert masked == "a " + " " * 9 + " b"


def test_closed_comment_is_blanked():
    line = "keep <!-- drop --> keep"
    masked, open_ = mdmask.mask_markdown_line(line, False)
    assert masked == "keep " + " " * 13 + " keep"
    assert not open_
    assert mdmask.blank_closed_comments("<!--a--> x <!--b-->") == " " * 8 + " x " + " " * 8


def test_comment_open_across_lines():
    masked, open_ = mdmask.mask_markdown_line("text <!-- starts", False)
    assert masked == "text " and open_
    masked, open_ = mdmask.mask_markdown_line("still inside", True)
    assert masked == "" and open_
    masked, open_ = mdmask.mask_markdown_line("ends --> after", True)
    assert masked == " " * 8 + " after" and not open_


def test_span_inside_comment_does_not_survive():
    masked, _ = mdmask.mask_markdown_line("<!-- `x` --> y", False)
    assert masked.strip() == "y"


def test_fence_re_reads_marker_and_language():
    m = mdmask.FENCE_RE.match("  ```{r} ")
    assert m and m.group(1) == "```" and m.group(2) == "{r}"
    m = mdmask.FENCE_RE.match("~~~~ tex")
    assert m and m.group(1) == "~~~~" and m.group(2) == "tex"
    assert mdmask.FENCE_RE.match("`` not a fence") is None
