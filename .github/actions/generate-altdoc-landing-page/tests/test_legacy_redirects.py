"""Offline tests for generate_legacy_redirects.py.

The composite that runs this script only executes on non-PR builds of a
consumer repo, so without these the parsing and validation logic would have no
coverage until a bad `legacy-paths` value reached production.
"""

import importlib.util
import pathlib
import sys

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "generate_legacy_redirects.py"
_spec = importlib.util.spec_from_file_location("generate_legacy_redirects", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)


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
