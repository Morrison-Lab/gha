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


def test_code_span_closes_only_on_an_equal_run():
    # `a``b` is one span: the inner double run does not close a single one.
    assert mdmask.mask_code_spans("x `a``b` y") == "x " + " " * 6 + " y"
    # ``a`b`` is one span; the plain (`+).+?\1 pattern closed it on `b`.
    assert mdmask.mask_code_spans("x ``a`b`` y") == "x " + " " * 7 + " y"
    # A lone unclosed run masks nothing.
    assert mdmask.mask_code_spans("x `a y") == "x `a y"


def test_paragraph_code_span_crosses_a_line_break():
    text = "x `a\nb` y"
    assert mdmask.PARAGRAPH_CODE_SPAN_RE.sub("C", text) == "x C y"
    assert mdmask.CODE_SPAN_RE.sub("C", text) == text


def test_replace_comments_string_and_function():
    text = "a <!-- x --> b <!-- y\nz --> c <!-- open"
    assert mdmask.replace_comments(text) == "a  b  c <!-- open"
    assert mdmask.replace_comments(text, " ") == "a   b   c <!-- open"
    blanked = mdmask.replace_comments(text, lambda c: "#" * len(c))
    assert len(blanked) == len(text) and blanked.endswith(" c <!-- open")


def test_replace_comments_bang_closer_only_with_bang():
    text = "a <!-- x --!> b --> c"
    assert mdmask.replace_comments(text) == "a  c"
    assert mdmask.replace_comments(text, bang=True) == "a  b --> c"


def test_replace_comments_matches_the_regexes_it_replaces():
    import re

    plain = re.compile("<!--.*?-->", re.S)
    banged = re.compile("<!--.*?--!?>", re.S)
    cases = [
        "", "<!---->", "<!--->", "<!-->", "<!-- a -->x<!-- b",
        "<!-- a --!> b -->", "x <!-- <!-- y --> z -->", "<!--\n-->\n<!--!-->",
    ]
    for text in cases:
        assert mdmask.replace_comments(text, " ") == plain.sub(" ", text), text
        assert mdmask.replace_comments(text, bang=True) == banged.sub("", text), text
