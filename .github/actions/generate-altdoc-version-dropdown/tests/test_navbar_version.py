"""Tests for navbar_version.py, generate-altdoc-version-dropdown's helpers.

Run with `python3 -m pytest .github/actions/generate-altdoc-version-dropdown/tests -q`;
CI runs the same command in `_selftest.yml`'s `altdoc-docs` job.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from navbar_version import (  # noqa: E402
    DEV,
    GENERATED_MARKER,
    find_versions_entry,
    format_dropdown_title,
    parse_bool,
    resolve_current_version,
    set_navbar_title,
    version_badge_html,
    yaml_quote,
)

TAGS = ["v1.2.0", "v1.1.0", "v1.0.0"]
LATEST = "v1.2.0"

# A config as a consumer writes it: the Versions menu still carries its
# pre-rewrite `- text: Versions` label, and the site title is altdoc's
# package-name placeholder.
CONFIG = """\
website:
  title: "$ALTDOC_PACKAGE_NAME"
  navbar:
    search: true
    right:
      - text: Versions
        menu:
          - text: Stable
            href: https://example.com/latest-tag/
      - icon: github
        href: https://example.com/repo
""".splitlines(keepends=True)


def test_release_build_is_labeled_stable():
    current = resolve_current_version("1.2.0", TAGS, LATEST, "v1.2.0")
    assert current == ("v1.2.0", "v1.2.0 (stable)", False)


def test_archived_release_is_labeled_by_its_tag_alone():
    current = resolve_current_version("1.0.0", TAGS, LATEST, "v1.0.0")
    assert current == ("v1.0.0", "v1.0.0", False)


def test_dev_build_is_labeled_with_the_rendered_branch_version():
    current = resolve_current_version("1.2.0.9000", TAGS, LATEST, DEV)
    assert current == ("1.2.0.9000", "1.2.0.9000 (dev)", True)


def test_a_tag_missing_from_the_release_list_still_labels_itself():
    # A release published too recently to appear in the collected list.
    current = resolve_current_version("1.3.0", TAGS, LATEST, "v1.3.0")
    assert current.label == "v1.3.0"


def test_version_matching_a_tag_is_inferred_as_that_release():
    assert resolve_current_version("1.2.0", TAGS, LATEST).label == "v1.2.0 (stable)"
    assert resolve_current_version("1.0.0", TAGS, LATEST).label == "v1.0.0"


def test_version_matching_no_tag_is_inferred_as_dev():
    current = resolve_current_version("1.2.0.9000", TAGS, LATEST)
    assert current.is_dev
    assert current.label == "1.2.0.9000 (dev)"


def test_inference_with_no_releases_yet():
    current = resolve_current_version("0.0.1", [], None)
    assert current.label == "0.0.1 (dev)"


def test_dropdown_title_template_substitutes_the_label():
    assert format_dropdown_title("{version}", "v1.2.0 (stable)") == "v1.2.0 (stable)"
    assert (
        format_dropdown_title("Version: {version}", "v1.2.0 (stable)")
        == "Version: v1.2.0 (stable)"
    )


def test_dropdown_title_template_without_a_placeholder_is_rejected():
    # Silently dropping the version would defeat the whole feature.
    with pytest.raises(ValueError, match=r"\{version\}"):
        format_dropdown_title("Versions", "v1.2.0 (stable)")


def test_dev_badge_is_red_and_release_badge_is_muted():
    dev = version_badge_html(resolve_current_version("1.2.0.9000", TAGS, LATEST, DEV))
    assert "text-danger" in dev
    assert ">1.2.0.9000<" in dev

    release = version_badge_html(resolve_current_version("1.2.0", TAGS, LATEST, "v1.2.0"))
    assert "text-muted" in release
    assert ">v1.2.0<" in release


@pytest.mark.parametrize("value,expected", [("true", True), ("TRUE", True), ("false", False), ("0", False)])
def test_parse_bool_accepts_the_usual_spellings(value, expected):
    assert parse_bool("version-in-navbar-title", value) is expected


def test_parse_bool_rejects_anything_else():
    # A typo must fail the build, not quietly turn the feature off.
    with pytest.raises(ValueError, match="boolean"):
        parse_bool("version-in-navbar-title", "flase")


def test_find_versions_entry_locates_the_unrewritten_anchor():
    block_start, entry_index, indent = find_versions_entry(CONFIG)
    assert block_start == entry_index
    assert CONFIG[entry_index].strip() == "- text: Versions"
    assert indent == 6


def test_find_versions_entry_locates_an_already_rewritten_block():
    # Idempotency: the rewrite replaces the `Versions` anchor with a version
    # label, so a second run has only the marker to go on.
    rewritten = CONFIG[:5] + [
        f"      {GENERATED_MARKER}\n",
        '      - text: "v1.2.0 (stable)"\n',
    ] + CONFIG[6:]
    block_start, entry_index, indent = find_versions_entry(rewritten)
    assert rewritten[block_start].strip() == GENERATED_MARKER
    assert entry_index == block_start + 1
    assert indent == 6


def test_find_versions_entry_returns_none_without_a_versions_menu():
    assert find_versions_entry(["website:\n", "  title: x\n"]) is None


def test_navbar_title_is_seeded_from_the_site_title():
    _, entry_index, _ = find_versions_entry(CONFIG)
    lines, title = set_navbar_title(CONFIG, entry_index, "<BADGE/>")
    assert title == "$ALTDOC_PACKAGE_NAME <BADGE/>"
    # Inserted as a navbar child, so `website.title` keeps driving <title>.
    assert lines[3] == '    title: "$ALTDOC_PACKAGE_NAME <BADGE/>"\n'
    assert lines[1] == '  title: "$ALTDOC_PACKAGE_NAME"\n'


def test_navbar_title_prefers_an_existing_navbar_title():
    config = CONFIG[:3] + ['    title: "Custom navbar name"\n'] + CONFIG[3:]
    _, entry_index, _ = find_versions_entry(config)
    lines, title = set_navbar_title(config, entry_index, "<BADGE/>")
    assert title == "Custom navbar name <BADGE/>"
    assert lines[3] == '    title: "Custom navbar name <BADGE/>"\n'
    assert len(lines) == len(config)


def test_rerunning_replaces_the_badge_rather_than_stacking_them():
    _, entry_index, _ = find_versions_entry(CONFIG)
    once, _ = set_navbar_title(CONFIG, entry_index, version_badge_html(
        resolve_current_version("1.2.0.9000", TAGS, LATEST, DEV)
    ))
    _, entry_index, _ = find_versions_entry(once)
    twice, title = set_navbar_title(once, entry_index, version_badge_html(
        resolve_current_version("1.2.0", TAGS, LATEST, "v1.2.0")
    ))
    assert title.count("<small") == 1
    assert "1.2.0.9000" not in title
    assert len(twice) == len(once)


def test_navbar_title_is_skipped_when_there_is_no_title_to_build_on():
    config = """\
website:
  navbar:
    right:
      - text: Versions
        menu:
          - text: Stable
            href: https://example.com/latest-tag/
""".splitlines(keepends=True)
    _, entry_index, _ = find_versions_entry(config)
    lines, title = set_navbar_title(config, entry_index, "<BADGE/>")
    assert title is None
    assert lines == config


def test_yaml_quote_escapes_quotes_and_backslashes():
    assert yaml_quote('a "b" \\c') == '"a \\"b\\" \\\\c"'
