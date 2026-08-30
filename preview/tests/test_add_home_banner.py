"""Tests for `preview/add-home-banner.py`.

The banner is the cheapest consumer of the changed-chapter substrate, so these
cases are mostly about the two ways it can be wrong without anything going red:
a banner that never gets inserted, and a banner that asserts "no changes" when
the comparison never ran.
"""

import json

import pytest

from conftest import write


HOME = "<html><body><main id=\"quarto-document-content\"><p>home</p></main></body></html>"


def run_banner(banner, monkeypatch, rendered_dir, changed=(), status="compared", reason="", **env):
    for key in ("RENDERED_DIR", "CHANGED_CHAPTERS", "DETECTION_STATUS", "SKIP_REASON", "BANNER_INDEX"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RENDERED_DIR", str(rendered_dir))
    monkeypatch.setenv("CHANGED_CHAPTERS", json.dumps(list(changed)))
    monkeypatch.setenv("DETECTION_STATUS", status)
    monkeypatch.setenv("SKIP_REASON", reason)
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    banner.main()
    return (rendered_dir / env.get("BANNER_INDEX", "index.html")).read_text(encoding="utf-8")


def test_banner_is_inserted_after_main(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/index.html", HOME).parent
    write(site, "chapters/01.html", "<html><body><h1>Chapter one</h1></body></html>")

    result = run_banner(banner, monkeypatch, site, changed=["chapters/01"])

    assert result.index("<main") < result.index("gha-preview-banner:start")
    assert '<a href="chapters/01.html">Chapter one</a>' in result


def test_banner_falls_back_to_body(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/index.html", "<html><body><p>home</p></body></html>").parent

    result = run_banner(banner, monkeypatch, site)

    assert result.index("<body") < result.index("gha-preview-banner:start")


def test_no_insertion_point_is_an_error(banner, monkeypatch, tmp_path):
    """win printed to stderr and left the run green with no banner at all."""
    site = write(tmp_path, "site/index.html", "<html><p>home</p></html>").parent

    with pytest.raises(banner.BannerError, match="no <main> or <body>"):
        run_banner(banner, monkeypatch, site)


def test_a_second_run_replaces_rather_than_stacks(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/index.html", HOME).parent

    run_banner(banner, monkeypatch, site, changed=[])
    result = run_banner(banner, monkeypatch, site, changed=[])

    assert result.count("gha-preview-banner:start") == 1


def test_a_title_with_markup_characters_is_escaped(banner, monkeypatch, tmp_path):
    """win interpolated the heading straight in, so `&` or `<` broke the markup."""
    site = write(tmp_path, "site/index.html", HOME).parent
    write(site, "chapters/01.html", "<html><body><h1>Risk &amp; <em>reward</em> &lt;3</h1></body></html>")

    result = run_banner(banner, monkeypatch, site, changed=["chapters/01"])

    assert "Risk &amp; reward &lt;3" in result
    assert "Risk & reward <3" not in result


def test_a_skipped_comparison_does_not_read_as_no_changes(banner, monkeypatch, tmp_path):
    """The distinction the whole port exists to preserve."""
    site = write(tmp_path, "site/index.html", HOME).parent

    result = run_banner(
        banner, monkeypatch, site, status="skipped", reason="branch 'gh-pages' does not exist"
    )

    assert "not determined" in result
    assert "no differences were found" not in result
    assert "gh-pages" in result


def test_an_empty_comparison_says_no_differences(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/index.html", HOME).parent

    result = run_banner(banner, monkeypatch, site, changed=[])

    assert "no differences were found" in result


def test_a_chapter_without_a_heading_falls_back_to_its_id(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/index.html", HOME).parent
    write(site, "chapters/01.html", "<html><body><p>no heading</p></body></html>")

    result = run_banner(banner, monkeypatch, site, changed=["chapters/01"])

    assert '<a href="chapters/01.html">chapters/01</a>' in result


def test_a_chapter_heading_may_come_from_h2(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/index.html", HOME).parent
    write(site, "chapters/01.html", "<html><body><h2>Second level</h2></body></html>")

    result = run_banner(banner, monkeypatch, site, changed=["chapters/01"])

    assert "Second level" in result


def test_a_chapter_with_no_rendered_file_is_listed_without_a_link(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/index.html", HOME).parent

    result = run_banner(banner, monkeypatch, site, changed=["chapters/ghost"])

    assert "chapters/ghost" in result
    assert "<a href=" not in result


def test_a_missing_home_page_is_an_error(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/chapters/01.html", "<html></html>").parent.parent

    with pytest.raises(banner.BannerError, match="home page"):
        run_banner(banner, monkeypatch, site)


def test_a_custom_banner_index_is_honored(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/home.html", HOME).parent

    result = run_banner(banner, monkeypatch, site, BANNER_INDEX="home.html")

    assert "gha-preview-banner:start" in result


def test_invalid_changed_chapters_json_is_an_error(banner, monkeypatch, tmp_path):
    site = write(tmp_path, "site/index.html", HOME).parent
    monkeypatch.setenv("RENDERED_DIR", str(site))
    monkeypatch.setenv("CHANGED_CHAPTERS", "{not json")
    monkeypatch.delenv("DETECTION_STATUS", raising=False)
    monkeypatch.delenv("SKIP_REASON", raising=False)
    monkeypatch.delenv("BANNER_INDEX", raising=False)

    with pytest.raises(banner.BannerError, match="not valid JSON"):
        banner.main()


def test_an_unknown_detection_status_is_an_error(banner, monkeypatch, tmp_path):
    """A third status must not be absorbed into the 'compared' branch, which
    would assert a comparison that never happened."""
    site = write(tmp_path, "site/index.html", HOME).parent

    with pytest.raises(banner.BannerError, match="DETECTION_STATUS"):
        run_banner(banner, monkeypatch, site, status="unknown")
