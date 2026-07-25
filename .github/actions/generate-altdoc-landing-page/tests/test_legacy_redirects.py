"""Offline tests for generate_legacy_redirects.py.

The composite that runs this script only executes on non-PR builds of a
consumer repo, so without these the parsing and validation logic would have no
coverage until a bad `legacy-paths` value reached production.
"""

import importlib.util
import pathlib
import sys

import pytest

_ACTION_DIR = pathlib.Path(__file__).resolve().parents[1]

# The action runs these scripts as `python3 <action-dir>/<script>.py`, which
# puts the action directory on sys.path and lets them import `_site_output`.
# Loading a script by file path here does not, so add it explicitly.
if str(_ACTION_DIR) not in sys.path:
    sys.path.insert(0, str(_ACTION_DIR))

_SCRIPT = _ACTION_DIR / "generate_legacy_redirects.py"
_spec = importlib.util.spec_from_file_location("generate_legacy_redirects", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

import _site_output  # noqa: E402  (needs the sys.path insert above)


class TestParseLegacyPaths:
    def test_empty_input_yields_no_pairs(self):
        assert mod.parse_legacy_paths("") == []
        assert mod.parse_legacy_paths("\n  \n") == []

    def test_single_pair(self):
        assert mod.parse_legacy_paths("main=dev") == [("main", "dev")]

    @pytest.mark.parametrize(
        "raw",
        [
            "main=dev,master=dev",
            "main=dev\nmaster=dev",
            "  main = dev , master = dev  ",
            "/main/=/dev/,master=dev",
            "main=dev,,master=dev",
        ],
    )
    def test_separators_whitespace_and_slashes(self, raw):
        assert mod.parse_legacy_paths(raw) == [("main", "dev"), ("master", "dev")]

    def test_order_is_preserved(self):
        parsed = mod.parse_legacy_paths("b=dev,a=dev")
        assert parsed == [("b", "dev"), ("a", "dev")]

    @pytest.mark.parametrize(
        "raw,message",
        [
            ("main", "must have the form"),
            ("main=dev=extra", "must have the form"),
            ("=dev", "empty source or target"),
            ("main=", "empty source or target"),
            ("dev=dev", "which would loop"),
            ("main=dev,main=latest-tag", "mapped more than once"),
        ],
    )
    def test_invalid_entries_raise(self, raw, message):
        with pytest.raises(ValueError, match=message):
            mod.parse_legacy_paths(raw)


class TestBasePathOf:
    @pytest.mark.parametrize(
        "base_url,expected",
        [
            ("https://owner.github.io/repo/", "/repo/"),
            ("https://owner.github.io/repo", "/repo/"),
            ("https://owner.github.io/", "/"),
            ("https://docs.example.com", "/"),
            ("https://owner.github.io/a/b/", "/a/b/"),
        ],
    )
    def test_path_component_always_has_both_slashes(self, base_url, expected):
        assert mod.base_path_of(base_url) == expected


class TestRender:
    def test_mapping_and_base_path_reach_the_page(self):
        page = mod.render(
            "/repo/", [("main", "dev")], "https://owner.github.io/repo/"
        )
        assert '"/repo/"' in page
        assert '{"main": "dev"}' in page
        assert "https://owner.github.io/repo/" in page

    def test_noscript_readers_get_a_link_not_a_blank_page(self):
        page = mod.render("/repo/", [("main", "dev")], "https://owner.github.io/repo/")
        assert "Page not found" in page
        assert '<a href="https://owner.github.io/repo/">' in page

    def test_embedded_values_cannot_close_the_script_block(self):
        page = mod.render(
            "/a</script><b>/", [("main", "dev")], "https://owner.github.io/repo/"
        )
        script = page.split("<script>", 1)[1].split("</script>", 1)[0]
        assert "<\\/script>" in script


class TestMain:
    def test_no_legacy_paths_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LEGACY_PATHS", "")
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "site-root"))
        monkeypatch.setenv("DOCS_BASE_URL", "https://owner.github.io/repo/")
        mod.main()
        assert not (tmp_path / "site-root" / "404.html").exists()

    def test_writes_404_html(self, tmp_path, monkeypatch):
        out = tmp_path / "site-root"
        monkeypatch.setenv("LEGACY_PATHS", "main=dev")
        monkeypatch.setenv("OUTPUT_DIR", str(out))
        monkeypatch.setenv("DOCS_BASE_URL", "https://owner.github.io/repo/")
        mod.main()
        page = (out / "404.html").read_text(encoding="utf-8")
        assert '{"main": "dev"}' in page

    def test_invalid_input_exits_nonzero(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LEGACY_PATHS", "dev=dev")
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "site-root"))
        monkeypatch.setenv("DOCS_BASE_URL", "https://owner.github.io/repo/")
        with pytest.raises(SystemExit) as excinfo:
            mod.main()
        assert excinfo.value.code == 1


class TestSiteOutput:
    """The plumbing both generator scripts share (`_site_output.py`)."""

    def test_output_dir_default_matches_action_yml(self):
        action = (_ACTION_DIR / "action.yml").read_text(encoding="utf-8")
        assert f"default: '{_site_output.DEFAULT_OUTPUT_DIR}'" in action

    def test_output_dir_is_created(self, tmp_path, monkeypatch):
        target = tmp_path / "nested" / "out"
        monkeypatch.setenv("OUTPUT_DIR", str(target))
        assert _site_output.site_output_dir() == target
        assert target.is_dir()

    def test_output_dir_falls_back_to_the_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        assert _site_output.site_output_dir().name == _site_output.DEFAULT_OUTPUT_DIR

    def test_base_url_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("DOCS_BASE_URL", "https://owner.github.io/repo/")
        assert _site_output.docs_base_url() == "https://owner.github.io/repo/"

    def test_missing_base_url_raises_rather_than_defaulting(self, monkeypatch):
        monkeypatch.delenv("DOCS_BASE_URL", raising=False)
        with pytest.raises(KeyError):
            _site_output.docs_base_url()
