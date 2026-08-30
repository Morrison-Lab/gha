"""Tests for `preview/detect-changed-chapters.py`.

Every failure mode of this script degrades in one direction -- toward "nothing
changed" -- so the cases that matter most are the ones that are SILENT when
wrong: a comparison that could not run, a page that is new, and a page whose
only difference is a build stamp.
"""

import json
import os

import pytest

from conftest import read_outputs, write


PAGE = """<html><body><main><h1>Chapter one</h1><p>{body}</p></main></body></html>"""


def run_detect(detector, monkeypatch, work, rendered_dir, **env):
    """Invoke `main()` the way the composite does: entirely through the environment."""
    output_file = rendered_dir.parent / "github-output.txt"
    output_file.write_text("", encoding="utf-8")
    defaults = {
        "REPO_DIR": str(work),
        "RENDERED_DIR": str(rendered_dir),
        "CHAPTER_GLOB": "chapters/*.html",
        "DEPLOYED_REMOTE": "origin",
        "DEPLOYED_BRANCH": "gh-pages",
        "DEPLOYED_SUBDIR": "",
        "NORMALIZE_PATTERNS": "",
        "GITHUB_OUTPUT": str(output_file),
    }
    for key in [*defaults, "CHANGED_CHAPTERS"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in {**defaults, **env}.items():
        monkeypatch.setenv(key, str(value))

    detector.main()

    return read_outputs.parse(output_file.read_text(encoding="utf-8"))


def test_missing_deployed_branch_is_a_stated_skip(detector, monkeypatch, repo_factory):
    """The case the port exists to fix.

    win ran the fetch with `check=False` and returned an empty list, which is
    indistinguishable from a genuinely unchanged PR.
    """
    work = repo_factory(published=None)
    rendered = write(work, "_site/chapters/01.html", PAGE.format(body="a")).parent.parent

    outputs = run_detect(detector, monkeypatch, work, rendered)

    assert outputs["detection-status"] == "skipped"
    assert "gh-pages" in outputs["skip-reason"]
    assert outputs["any-changed"] == "false"
    assert json.loads(outputs["changed-chapters"]) == []


def test_unreachable_remote_is_an_error_not_an_empty_result(detector, monkeypatch, repo_factory, tmp_path):
    """A network or permission failure must stop the run, never read as clean."""
    work = repo_factory(published={"chapters/01.html": PAGE.format(body="a")})
    rendered = write(work, "_site/chapters/01.html", PAGE.format(body="a")).parent.parent

    with pytest.raises(detector.DetectionError):
        run_detect(
            detector,
            monkeypatch,
            work,
            rendered,
            DEPLOYED_REMOTE=f"file://{tmp_path / 'no-such-repo.git'}",
        )


def test_new_file_is_reported_as_changed(detector, monkeypatch, repo_factory):
    work = repo_factory(published={"chapters/01.html": PAGE.format(body="a")})
    write(work, "_site/chapters/01.html", PAGE.format(body="a"))
    rendered = write(work, "_site/chapters/02.html", PAGE.format(body="new")).parent.parent

    outputs = run_detect(detector, monkeypatch, work, rendered)

    assert json.loads(outputs["changed-chapters"]) == ["chapters/02"]
    assert outputs["any-changed"] == "true"
    assert outputs["detection-status"] == "compared"


def test_identical_file_is_not_reported(detector, monkeypatch, repo_factory):
    same = PAGE.format(body="a")
    work = repo_factory(published={"chapters/01.html": same})
    rendered = write(work, "_site/chapters/01.html", same).parent.parent

    outputs = run_detect(detector, monkeypatch, work, rendered)

    assert json.loads(outputs["changed-chapters"]) == []
    assert outputs["any-changed"] == "false"
    assert outputs["detection-status"] == "compared"


def test_edited_file_is_reported(detector, monkeypatch, repo_factory):
    work = repo_factory(published={"chapters/01.html": PAGE.format(body="before")})
    rendered = write(work, "_site/chapters/01.html", PAGE.format(body="after")).parent.parent

    outputs = run_detect(detector, monkeypatch, work, rendered)

    assert json.loads(outputs["changed-chapters"]) == ["chapters/01"]


@pytest.mark.parametrize(
    ("published_body", "rendered_body"),
    [
        # htmlwidgets mint a fresh random element id on every render.
        (
            '<div id="htmlwidget-3f2a91c4" class="plotly"></div>',
            '<div id="htmlwidget-b70e15dd" class="plotly"></div>',
        ),
        # A build stamp written as an ISO-8601 datetime.
        (
            '<meta name="generated" content="2026-08-29T04:11:07Z">',
            '<meta name="generated" content="2026-08-30T22:59:41Z">',
        ),
    ],
)
def test_volatile_only_difference_is_not_reported(
    detector, monkeypatch, repo_factory, published_body, rendered_body
):
    """The case that decides whether the feature is usable at all.

    If every page reads as changed on every run, the banner is noise.
    """
    work = repo_factory(published={"chapters/01.html": PAGE.format(body=published_body)})
    rendered = write(work, "_site/chapters/01.html", PAGE.format(body=rendered_body)).parent.parent

    outputs = run_detect(detector, monkeypatch, work, rendered)

    assert json.loads(outputs["changed-chapters"]) == []


def test_a_bare_date_in_prose_is_still_a_real_change(detector, monkeypatch, repo_factory):
    """The normalization must not reach past build stamps into content.

    A `YYYY-MM-DD` with no time component is prose, so editing it is an edit.
    """
    work = repo_factory(published={"chapters/01.html": PAGE.format(body="surveyed 2026-08-29")})
    rendered = write(work, "_site/chapters/01.html", PAGE.format(body="surveyed 2026-08-30")).parent.parent

    outputs = run_detect(detector, monkeypatch, work, rendered)

    assert json.loads(outputs["changed-chapters"]) == ["chapters/01"]


def test_extra_normalize_patterns_are_applied(detector, monkeypatch, repo_factory):
    work = repo_factory(published={"chapters/01.html": PAGE.format(body="build 41")})
    rendered = write(work, "_site/chapters/01.html", PAGE.format(body="build 42")).parent.parent

    outputs = run_detect(
        detector, monkeypatch, work, rendered, NORMALIZE_PATTERNS="build \\d+"
    )

    assert json.loads(outputs["changed-chapters"]) == []


def test_a_pattern_matching_the_empty_string_is_rejected(detector, monkeypatch, repo_factory):
    """Such a pattern blanks every document, so every page would read as unchanged."""
    work = repo_factory(published={"chapters/01.html": PAGE.format(body="a")})
    rendered = write(work, "_site/chapters/01.html", PAGE.format(body="b")).parent.parent

    with pytest.raises(detector.DetectionError, match="empty string"):
        run_detect(detector, monkeypatch, work, rendered, NORMALIZE_PATTERNS="x*")


def test_an_invalid_pattern_is_rejected(detector, monkeypatch, repo_factory):
    work = repo_factory(published={"chapters/01.html": PAGE.format(body="a")})
    rendered = write(work, "_site/chapters/01.html", PAGE.format(body="a")).parent.parent

    with pytest.raises(detector.DetectionError, match="invalid normalize pattern"):
        run_detect(detector, monkeypatch, work, rendered, NORMALIZE_PATTERNS="(unclosed")


def test_deployed_subdir_is_honored(detector, monkeypatch, repo_factory):
    """A deployed tree that nests the site under a prefix compares against it."""
    same = PAGE.format(body="a")
    work = repo_factory(published={"pr-preview/pr-7/chapters/01.html": same})
    rendered = write(work, "_site/chapters/01.html", same).parent.parent

    outputs = run_detect(
        detector, monkeypatch, work, rendered, DEPLOYED_SUBDIR="pr-preview/pr-7"
    )

    assert json.loads(outputs["changed-chapters"]) == []


def test_a_wrong_subdir_warns_rather_than_reporting_a_clean_sweep(
    detector, monkeypatch, repo_factory, capsys
):
    same = PAGE.format(body="a")
    work = repo_factory(published={"chapters/01.html": same})
    rendered = write(work, "_site/chapters/01.html", same).parent.parent

    outputs = run_detect(detector, monkeypatch, work, rendered, DEPLOYED_SUBDIR="wrong")

    assert json.loads(outputs["changed-chapters"]) == ["chapters/01"]
    assert "::warning::" in capsys.readouterr().out


def test_a_glob_matching_nothing_is_an_error(detector, monkeypatch, repo_factory):
    """Not an empty result: it means the render is missing or the glob is wrong."""
    work = repo_factory(published={"chapters/01.html": PAGE.format(body="a")})
    rendered = write(work, "_site/index.html", "<html></html>").parent

    with pytest.raises(detector.DetectionError, match="no rendered files matched"):
        run_detect(detector, monkeypatch, work, rendered)


def test_a_binary_file_is_compared_byte_for_byte(detector, monkeypatch, repo_factory):
    """Normalization is text-only; a non-text suffix must not silently decode.

    The two payloads differ ONLY in something the default patterns would blank,
    so a version that normalized every suffix would call them unchanged. A pair
    differing in ordinary bytes would pass either way and pin nothing.
    """
    work = repo_factory(published={"chapters/01.docx": b"PK\x03\x04htmlwidget-3f2a91c4"})
    rendered = write(work, "_site/chapters/01.docx", b"PK\x03\x04htmlwidget-b70e15dd").parent.parent

    outputs = run_detect(detector, monkeypatch, work, rendered, CHAPTER_GLOB="chapters/*.docx")

    assert json.loads(outputs["changed-chapters"]) == ["chapters/01"]


def test_a_quoted_published_path_is_matched(detector, monkeypatch, repo_factory):
    """`git ls-tree` is read NUL-separated.

    Without `-z`, git quotes and C-escapes any path outside plain ASCII, so the
    listing would carry `"chapters/caf\\303\\251.html"` and this page would read
    as absent -- reporting an unchanged chapter as new, on every run. The name is
    written as an escape so this source file itself stays ASCII.
    """
    name = "chapters/caf\u00e9.html"
    same = PAGE.format(body="a")
    work = repo_factory(published={name: same})
    rendered = write(work, f"_site/{name}", same).parent.parent

    outputs = run_detect(detector, monkeypatch, work, rendered)

    assert json.loads(outputs["changed-chapters"]) == []


def test_missing_rendered_dir_is_an_error(detector, monkeypatch, tmp_path):
    monkeypatch.setenv("RENDERED_DIR", str(tmp_path / "absent"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    with pytest.raises(detector.DetectionError, match="does not exist"):
        detector.main()


def test_outputs_are_absent_when_github_output_is_unset(detector, monkeypatch, repo_factory):
    """Running outside Actions must not fail; it just has nowhere to write."""
    same = PAGE.format(body="a")
    work = repo_factory(published={"chapters/01.html": same})
    rendered = write(work, "_site/chapters/01.html", same).parent.parent
    for key, value in {
        "REPO_DIR": str(work),
        "RENDERED_DIR": str(rendered),
        "CHAPTER_GLOB": "chapters/*.html",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    for key in ("DEPLOYED_REMOTE", "DEPLOYED_BRANCH", "DEPLOYED_SUBDIR", "NORMALIZE_PATTERNS"):
        monkeypatch.delenv(key, raising=False)

    assert detector.main() == 0


def test_a_newline_in_a_skip_reason_cannot_declare_another_output(
    detector, monkeypatch, repo_factory
):
    """`skip-reason` is free text built from a caller-supplied branch name and
    git's own wording, so a bare `key=value` line in `$GITHUB_OUTPUT` would let
    it forge further outputs -- here, a comparison that never ran claiming a
    change was found."""
    work = repo_factory(published={"chapters/01.html": PAGE.format(body="a")})
    rendered = write(work, "_site/chapters/01.html", PAGE.format(body="a")).parent.parent

    outputs = run_detect(
        detector,
        monkeypatch,
        work,
        rendered,
        DEPLOYED_BRANCH="ghost\nany-changed=true\ndetection-status=compared",
    )

    assert outputs["detection-status"] == "skipped"
    assert outputs["any-changed"] == "false"
