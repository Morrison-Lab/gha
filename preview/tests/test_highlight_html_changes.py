"""Unit tests for rendered-HTML change highlighting.

Tests verify that:
  - A page with no change receives no highlighting and remains byte-identical.
  - A page with modified or added text receives inline mark tags and a summary banner,
    with all surrounding HTML tags intact.
  - A page with newly added paragraphs receives element-level highlighting.
  - A page differing only in build metadata (htmlwidgets, timestamps, comments) is NOT
    highlighted and remains byte-identical.
  - A page absent from the deployed branch is treated as new, not as an error.
  - A skipped comparison skips cleanly without modifying files.
  - Re-running the script is idempotent and does not accumulate duplicate banners.
  - Invalid configurations fail fast.
"""

import json
import pytest
from conftest import write


def run_highlighter(highlighter, monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    highlighter.main()


def test_unchanged_page_remains_byte_identical(highlighter, monkeypatch, repo_factory):
    page = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head><title>Chapter 1</title></head>\n"
        "<body>\n"
        "<main class=\"content\">\n"
        "<h1>Introduction</h1>\n"
        "<p>This is unchanged text in paragraph one.</p>\n"
        "<p>This is unchanged text in paragraph two.</p>\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )
    work = repo_factory(published={"chapters/01.html": page})
    rendered = write(work, "_site/chapters/01.html", page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert result == page


def test_modified_text_gets_inline_highlighting_and_banner(highlighter, monkeypatch, repo_factory):
    old_page = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head><title>Chapter 1</title></head>\n"
        "<body>\n"
        "<main class=\"content\">\n"
        "<h1>Introduction</h1>\n"
        "<p>The quick brown fox jumps over the lazy dog.</p>\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )
    new_page = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head><title>Chapter 1</title></head>\n"
        "<body>\n"
        "<main class=\"content\">\n"
        "<h1>Introduction</h1>\n"
        "<p>The quick red fox leaps over the lazy sleepy dog.</p>\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )
    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert "gha-preview-page-banner:start" in result
    assert "preview-page-changes-banner" in result
    assert "preview-text-changed" in result
    assert "preview-text-added" in result
    assert "<h1>Introduction</h1>" in result
    assert "</main>" in result


def test_html_tags_inside_modified_paragraph_are_preserved(highlighter, monkeypatch, repo_factory):
    old_page = (
        "<main>\n"
        "<p>Use <b>important</b> method and <code>fn()</code> today.</p>\n"
        "</main>"
    )
    new_page = (
        "<main>\n"
        "<p>Use <b>critical</b> method and <code>new_fn()</code> today.</p>\n"
        "</main>"
    )
    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert "<b>" in result and "</b>" in result
    assert "<code>" in result and "</code>" in result
    assert "preview-text-changed" in result


def test_newly_added_paragraph_gets_element_highlighting(highlighter, monkeypatch, repo_factory):
    old_page = (
        "<main>\n"
        "<p>First paragraph.</p>\n"
        "</main>"
    )
    new_page = (
        "<main>\n"
        "<p>First paragraph.</p>\n"
        "<p>A brand new paragraph added to the section.</p>\n"
        "</main>"
    )
    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert '<mark class="preview-element-added"' in result
    assert "A brand new paragraph added to the section." in result


def test_page_differing_only_in_build_metadata_remains_unmodified(highlighter, monkeypatch, repo_factory):
    old_page = (
        "<main>\n"
        "<!-- rendered at 2026-08-01T12:00:00Z -->\n"
        '<div id="htmlwidget-abcdef123456" class="html-widget">Widget</div>\n'
        "<p>Same stable prose text here.</p>\n"
        "</main>"
    )
    new_page = (
        "<main>\n"
        "<!-- rendered at 2026-08-31T15:30:00Z -->\n"
        '<div id="htmlwidget-789012fedcba" class="html-widget">Widget</div>\n'
        "<p>Same stable prose text here.</p>\n"
        "</main>"
    )
    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert result == new_page
    assert "gha-preview-page-banner" not in result
    assert "preview-text-changed" not in result


def test_custom_normalize_patterns(highlighter, monkeypatch, repo_factory):
    old_page = "<main><p>Hash: build-abc123</p></main>"
    new_page = "<main><p>Hash: build-xyz789</p></main>"

    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
        NORMALIZE_PATTERNS="build-[a-z0-9]+",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert result == new_page


def test_page_absent_from_deployed_branch_treated_as_new_page(highlighter, monkeypatch, repo_factory):
    new_page = (
        "<main>\n"
        "<h1>Brand New Chapter</h1>\n"
        "<p>This entire chapter is new.</p>\n"
        "</main>"
    )
    work = repo_factory(published={"chapters/old.html": "<main><p>Old</p></main>"})
    rendered = write(work, "_site/chapters/new_chap.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/new_chap"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/new_chap.html").read_text(encoding="utf-8")
    assert "gha-preview-page-banner:start" in result
    assert "This is a new page added in this pull request." in result
    assert "preview-text-changed" not in result


def test_skipped_detection_does_not_modify_files(highlighter, monkeypatch, repo_factory):
    page = "<main><p>Hello world</p></main>"
    work = repo_factory(published=None)
    rendered = write(work, "_site/chapters/01.html", page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="skipped",
        SKIP_REASON="branch does not exist",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert result == page


def test_idempotent_re_run_does_not_duplicate_banner(highlighter, monkeypatch, repo_factory):
    old_page = "<main><p>Old prose.</p></main>"
    new_page = "<main><p>New modified prose.</p></main>"
    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    first_run = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert first_run.count("gha-preview-page-banner:start") == 1

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    second_run = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert second_run.count("gha-preview-page-banner:start") == 1


def test_invalid_json_in_changed_chapters_raises_error(highlighter, monkeypatch, repo_factory):
    work = repo_factory(published={"chapters/01.html": "<main><p>Hi</p></main>"})
    rendered = write(work, "_site/chapters/01.html", "<main><p>Hi</p></main>").parent.parent

    with pytest.raises(highlighter.HighlightError, match="not valid JSON"):
        run_highlighter(
            highlighter,
            monkeypatch,
            REPO_DIR=str(work),
            RENDERED_DIR=str(rendered),
            CHANGED_CHAPTERS="not-json",
        )


def test_invalid_normalize_pattern_raises_error(highlighter, monkeypatch, repo_factory):
    work = repo_factory(published={"chapters/01.html": "<main><p>Hi</p></main>"})
    rendered = write(work, "_site/chapters/01.html", "<main><p>Hi</p></main>").parent.parent

    with pytest.raises(highlighter.HighlightError, match="matches the empty string"):
        run_highlighter(
            highlighter,
            monkeypatch,
            REPO_DIR=str(work),
            RENDERED_DIR=str(rendered),
            CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
            NORMALIZE_PATTERNS=".*",
        )


def test_single_word_edit_in_very_long_paragraph_is_highlighted(highlighter, monkeypatch, repo_factory):
    # Paragraph with ~800 words where single word edit produces ratio > 0.999
    base_words = ["word"] * 800
    old_para = "<p>" + " ".join(base_words) + "</p>"
    new_words = list(base_words)
    new_words[400] = "changed"
    new_para = "<p>" + " ".join(new_words) + "</p>"

    old_page = f"<main>{old_para}</main>"
    new_page = f"<main>{new_para}</main>"

    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert "preview-text-changed" in result
    assert "changed" in result


def test_element_replacement_scoped_to_main_does_not_corrupt_nav(highlighter, monkeypatch, repo_factory):
    old_page = (
        "<nav><p>Common text</p></nav>\n"
        "<main><p>Common text</p></main>"
    )
    new_page = (
        "<nav><p>Common text</p></nav>\n"
        "<main><p>Common text modified</p></main>"
    )

    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    # Nav paragraph must be unchanged without any highlight marks
    assert "<nav><p>Common text</p></nav>" in result
    # Main paragraph must carry the highlight
    assert "<p>Common text<mark" in result and "preview-text-added" in result


def test_missing_main_or_body_anchor_raises_error(highlighter):
    with pytest.raises(highlighter.HighlightError, match="has no <main> or <body>"):
        highlighter.apply_page_banner("<div>No anchor here</div>", "<!-- banner -->", "doc.html")


def test_pairwise_cap_skips_highlighting_on_many_elements(highlighter, monkeypatch, repo_factory, capsys):
    monkeypatch.setattr(highlighter, "MAX_ELEMENTS_FOR_PAIRWISE", 5)

    old_paras = "\n".join(f"<p>Paragraph {i} original text.</p>" for i in range(10))
    new_paras = "\n".join(f"<p>Paragraph {i} modified text.</p>" for i in range(10))

    old_page = f"<main>\n{old_paras}\n</main>"
    new_page = f"<main>\n{new_paras}\n</main>"

    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    assert "preview-text-changed" not in result
    assert "preview-element-added" not in result
    captured = capsys.readouterr()
    assert "exceed the 5-element cap" in captured.err


def test_exact_offset_splice_handles_identical_repeated_elements(highlighter, monkeypatch, repo_factory):
    old_page = (
        "<main>\n"
        "<p>Same text.</p>\n"
        "<p>Completely unrelated old wording lives here today.</p>\n"
        "</main>"
    )
    new_page = (
        "<main>\n"
        "<p>Same text.</p>\n"
        "<p>Same text.</p>\n"
        "</main>"
    )

    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent

    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )

    result = (rendered / "chapters/01.html").read_text(encoding="utf-8")
    lines = [line.strip() for line in result.splitlines() if line.strip().startswith("<p>")]
    assert lines[0] == "<p>Same text.</p>"
    assert "preview-element-added" in lines[1]
    assert "Same text." in lines[1]


def test_max_elements_for_pairwise_handles_empty_or_invalid_env(highlighter, monkeypatch):
    monkeypatch.setenv("MAX_ELEMENTS_FOR_PAIRWISE", "")
    assert highlighter._get_max_elements_for_pairwise() == 500

    monkeypatch.setenv("MAX_ELEMENTS_FOR_PAIRWISE", "not-a-number")
    assert highlighter._get_max_elements_for_pairwise() == 500

    monkeypatch.setenv("MAX_ELEMENTS_FOR_PAIRWISE", "250")
    assert highlighter._get_max_elements_for_pairwise() == 250


def _run_single_page(highlighter, monkeypatch, repo_factory, old_page, new_page):
    work = repo_factory(published={"chapters/01.html": old_page})
    rendered = write(work, "_site/chapters/01.html", new_page).parent.parent
    run_highlighter(
        highlighter,
        monkeypatch,
        REPO_DIR=str(work),
        RENDERED_DIR=str(rendered),
        CHANGED_CHAPTERS=json.dumps(["chapters/01"]),
        DETECTION_STATUS="compared",
    )
    return (rendered / "chapters/01.html").read_text(encoding="utf-8")


def test_edit_after_a_code_chunk_and_widget_is_highlighted(highlighter, monkeypatch, repo_factory):
    # The real trigger, as Quarto renders it: a downlit code chunk, the
    # htmlwidget it produces, then a paragraph. Without the word boundary in
    # ELEMENT_RE, `<p` matched `<pre`, and since no </p> closes a <pre>, one
    # "element" ran from the <pre> through the widget's <script> JSON to the
    # paragraph's </p>. Diffing it was quadratic in the JSON (Morrison-Lab/mds's
    # algebra.html: 10 MB, never finished), and skipping it instead hid the
    # paragraph's edit. The edit must be highlighted and the widget untouched.

    # Near-identical payloads over a wide alphabet: difflib's autojunk
    # heuristic cannot discard their characters as "popular", so diffing them
    # is genuinely quadratic (about 8 s for 20000 characters, 130 s for 50000,
    # measured). Digits-only JSON would be junked and stay fast.
    import random

    rnd = random.Random(0)
    alphabet = [chr(c) for c in range(0x100, 0x200)]
    chars = [rnd.choice(alphabet) for _ in range(25000)]
    old_json = '{"x": "' + "".join(chars) + '"}'
    for i in range(0, len(chars), 200):
        chars[i] = "Z"
    new_json = '{"x": "' + "".join(chars) + '"}'

    def page(widget_json, question):
        return (
            "<main>\n"
            '<pre class="downlit sourceCode r code-with-copy"><code class="sourceCode r">'
            "plot_ly(x = ~x)</code></pre>\n"
            '<div class="html-widget"><script type="application/json" data-for="w1">'
            + widget_json
            + "</script></div>\n"
            "<p>Exercise 2. For a, b and c, " + question + " the identity hold?</p>\n"
            "</main>"
        )

    result = _run_single_page(
        highlighter,
        monkeypatch,
        repo_factory,
        page(old_json, "when does"),
        page(new_json, "under what conditions does"),
    )
    exercise = result[result.index("<p>Exercise 2"):]
    exercise = exercise[: exercise.index("</p>")]
    assert "<mark" in exercise
    assert "conditions" in exercise
    assert new_json in result
    # Nothing between the code chunk and the paragraph is marked. (The page
    # banner inserted after <main> carries <mark> legend swatches of its own.)
    assert "<mark" not in result[result.index("<pre"): result.index("<p>Exercise 2")]


def test_element_regex_does_not_match_pre(highlighter):
    assert highlighter.ELEMENT_RE.match("<pre>code</pre><p>text</p>") is None
    assert highlighter.ELEMENT_RE.match('<p class="x">text</p>')


def test_over_length_element_is_not_highlighted(highlighter, monkeypatch, repo_factory, capsys):
    monkeypatch.setattr(highlighter, "MAX_ELEMENT_TEXT_CHARS", 50)
    long_old = "alpha " * 20
    long_new = "alpha " * 19 + "omega "
    result = _run_single_page(
        highlighter,
        monkeypatch,
        repo_factory,
        f"<main>\n<p>{long_old}</p>\n<p>Short one.</p>\n</main>",
        f"<main>\n<p>{long_new}</p>\n<p>Short two.</p>\n</main>",
    )
    long_line = next(line for line in result.splitlines() if "omega" in line)
    assert "<mark" not in long_line
    short_line = next(line for line in result.splitlines() if "Short" in line)
    assert "<mark" in short_line
    # One notice, naming the page and the element by its visible text, and
    # counting the element once although it is over-length on both pages.
    out = capsys.readouterr().out
    assert "::notice::chapters/01.html: left 1 element(s) unhighlighted" in out
    assert "alpha alpha" in out


def test_exhausted_time_budget_leaves_page_unhighlighted_with_warning(
    highlighter, monkeypatch, repo_factory, capsys
):
    monkeypatch.setattr(highlighter, "PAGE_TIME_BUDGET_SECONDS", -1.0)
    new_page = "<main>\n<p>Paragraph with modified wording.</p>\n</main>"
    result = _run_single_page(
        highlighter,
        monkeypatch,
        repo_factory,
        "<main>\n<p>Paragraph with original wording.</p>\n</main>",
        new_page,
    )
    assert result == new_page
    captured = capsys.readouterr()
    assert "exceeded its time budget" in captured.out
    assert "chapters/01.html" in captured.out



def test_budget_exit_still_reports_skipped_elements(highlighter, monkeypatch, repo_factory, capsys):
    monkeypatch.setattr(highlighter, "PAGE_TIME_BUDGET_SECONDS", -1.0)
    monkeypatch.setattr(highlighter, "MAX_ELEMENT_TEXT_CHARS", 20)
    _run_single_page(
        highlighter,
        monkeypatch,
        repo_factory,
        "<main>\n<p>Short original.</p>\n<p>This paragraph is well over twenty characters.</p>\n</main>",
        "<main>\n<p>Short changed.</p>\n<p>This paragraph is well over twenty characters.</p>\n</main>",
    )
    out = capsys.readouterr().out
    assert "chapters/01.html: left 1 element(s) unhighlighted" in out
    assert "exceeded its time budget" in out


def test_cap_exit_still_reports_skipped_elements(highlighter, monkeypatch, repo_factory, capsys):
    monkeypatch.setattr(highlighter, "MAX_ELEMENTS_FOR_PAIRWISE", 1)
    monkeypatch.setattr(highlighter, "MAX_ELEMENT_TEXT_CHARS", 20)
    _run_single_page(
        highlighter,
        monkeypatch,
        repo_factory,
        "<main>\n<p>One a.</p>\n<p>Two a.</p>\n<p>This paragraph is well over twenty characters.</p>\n</main>",
        "<main>\n<p>One b.</p>\n<p>Two b.</p>\n<p>This paragraph is well over twenty characters.</p>\n</main>",
    )
    captured = capsys.readouterr()
    assert "element cap" in captured.err
    assert "chapters/01.html: left 1 element(s) unhighlighted" in captured.out


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "", "abc"])
def test_env_float_falls_back_on_non_finite_or_invalid(highlighter, monkeypatch, value):
    monkeypatch.setenv("HIGHLIGHT_PAGE_BUDGET_SECONDS", value)
    assert highlighter._env_float("HIGHLIGHT_PAGE_BUDGET_SECONDS", 60.0) == 60.0
