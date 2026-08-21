"""Tests for inject_canonical_urls.py (gha#332).

Fixtures are generated per-test into tmp_path rather than committed, per
CLAUDE.md's "Generate selftest fixtures at runtime" rule -- committed HTML
under an action's tests/ dir gets swept into other selftest jobs' repo-wide
scans.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "inject_canonical_urls.py"
spec = importlib.util.spec_from_file_location("inject_canonical_urls", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["inject_canonical_urls"] = mod
spec.loader.exec_module(mod)

BASE = "https://owner.github.io/repo/"


def page(title: str = "Reference") -> str:
    return (
        "<!DOCTYPE html>\n<html><head>\n"
        f"<meta charset='utf-8'>\n<title>{title}</title>\n"
        "</head><body><p>hi</p></body></html>\n"
    )


def build(tmp_path: Path, files: dict) -> Path:
    docs = tmp_path / "docs"
    for rel, content in files.items():
        p = docs / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return docs


def run(docs: Path, **env):
    defaults = {
        "DOCS_DIR": str(docs),
        "DOCS_BASE_URL": BASE,
        "DEPLOY_KIND": "release",
        "DEPLOY_SUBDIR": "dev",
        "LATEST_TAG_MANIFEST": "",
    }
    defaults.update({k: str(v) for k, v in env.items()})
    old = dict(os.environ)
    os.environ.update(defaults)
    try:
        return mod.main()
    finally:
        os.environ.clear()
        os.environ.update(old)


def canon_of(p: Path) -> str:
    m = mod._CANONICAL_RE.search(p.read_text(encoding="utf-8"))
    assert m, f"no canonical in {p}"
    line = p.read_text(encoding="utf-8")
    start = line.index('<link rel="canonical"', m.start() - 30 if m.start() > 30 else 0)
    return line[start : line.index(">", start) + 1]


# --- the core behaviour the issue asks for ---------------------------------


def test_page_present_in_latest_tag_canonicalizes_there(tmp_path):
    docs = build(tmp_path, {"index.html": page(), "ref/api.html": page()})
    manifest = tmp_path / "m.txt"
    manifest.write_text("index.html\nref/api.html\n", encoding="utf-8")
    run(docs, DEPLOY_SUBDIR="v1.2.0", LATEST_TAG_MANIFEST=manifest)
    assert f'href="{BASE}latest-tag/ref/api.html"' in (docs / "ref/api.html").read_text()


def test_page_absent_from_latest_tag_self_canonicalizes(tmp_path):
    """The gha#332 decision point: never point a canonical at a 404."""
    docs = build(tmp_path, {"index.html": page(), "brand-new.html": page()})
    manifest = tmp_path / "m.txt"
    manifest.write_text("index.html\n", encoding="utf-8")
    run(docs, DEPLOY_SUBDIR="dev", LATEST_TAG_MANIFEST=manifest)
    assert f'href="{BASE}dev/brand-new.html"' in (docs / "brand-new.html").read_text()
    assert "latest-tag/brand-new.html" not in (docs / "brand-new.html").read_text()


def test_no_manifest_self_canonicalizes_everything(tmp_path):
    docs = build(tmp_path, {"a.html": page()})
    run(docs, DEPLOY_SUBDIR="dev")
    assert f'href="{BASE}dev/a.html"' in (docs / "a.html").read_text()


def test_preview_gets_noindex_not_canonical(tmp_path):
    docs = build(tmp_path, {"a.html": page()})
    run(docs, DEPLOY_KIND="preview", DEPLOY_SUBDIR="pr-preview/pr-7")
    html = (docs / "a.html").read_text()
    assert 'name="robots" content="noindex"' in html
    assert "rel=\"canonical\"" not in html


def test_404_is_left_untagged(tmp_path):
    docs = build(tmp_path, {"index.html": page(), "404.html": page("Not found")})
    run(docs)
    assert "canonical" not in (docs / "404.html").read_text()


# --- idempotence and the verification pass ---------------------------------


def test_existing_canonical_is_not_double_tagged(tmp_path):
    pre = page().replace(
        "<title>", '<link rel="canonical" href="https://elsewhere/x.html">\n<title>'
    )
    docs = build(tmp_path, {"a.html": pre})
    run(docs)
    assert (docs / "a.html").read_text().count("rel=\"canonical\"") == 1
    assert "https://elsewhere/x.html" in (docs / "a.html").read_text()


def test_running_twice_is_idempotent(tmp_path):
    docs = build(tmp_path, {"a.html": page()})
    run(docs)
    first = (docs / "a.html").read_text()
    run(docs)
    assert (docs / "a.html").read_text() == first


# --- fail-loud conditions --------------------------------------------------


def test_zero_html_files_aborts(tmp_path):
    docs = build(tmp_path, {"readme.md": "not html"})
    with pytest.raises(SystemExit):
        run(docs)


def test_non_https_base_url_aborts(tmp_path):
    docs = build(tmp_path, {"a.html": page()})
    with pytest.raises(SystemExit):
        run(docs, DOCS_BASE_URL="http://insecure.example/")


def test_empty_base_url_aborts(tmp_path):
    docs = build(tmp_path, {"a.html": page()})
    with pytest.raises(SystemExit):
        run(docs, DOCS_BASE_URL="")


def test_missing_docs_dir_aborts(tmp_path):
    with pytest.raises(SystemExit):
        run(tmp_path / "nope")


def test_page_without_head_or_title_aborts(tmp_path):
    docs = build(tmp_path, {"a.html": "<html><body>bare</body></html>"})
    with pytest.raises(SystemExit):
        run(docs)


def test_head_without_title_still_gets_tagged(tmp_path):
    docs = build(
        tmp_path, {"a.html": "<html><head lang='en'><meta charset='utf-8'></head><body>x</body></html>"}
    )
    run(docs)
    assert 'rel="canonical"' in (docs / "a.html").read_text()


# --- base-url normalisation ------------------------------------------------


def test_base_url_without_trailing_slash_does_not_double_up(tmp_path):
    docs = build(tmp_path, {"a.html": page()})
    run(docs, DOCS_BASE_URL="https://owner.github.io/repo", DEPLOY_SUBDIR="dev")
    assert f'href="{BASE}dev/a.html"' in (docs / "a.html").read_text()


def test_empty_subdir_yields_root_relative_canonical(tmp_path):
    docs = build(tmp_path, {"a.html": page()})
    run(docs, DEPLOY_SUBDIR="")
    assert f'href="{BASE}a.html"' in (docs / "a.html").read_text()
