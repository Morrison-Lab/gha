"""Unit tests for check-bitmap-figures.

Covers the three findings (a new bitmap file, a new reference to a bitmap, a
new raster device), what does not count (an SVG, a reference in a code fence
or an HTML comment, a renamed bitmap, a moved line), the allow pragma and its
reason, paths-ignore for files and image targets, diff scoping, the
skip-not-fallback guard, and the defaults the action, the reusable workflow
and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_bitmap_figures", _DIR / "check-bitmap-figures.py"
)
assert _spec is not None and _spec.loader is not None
cbf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cbf)


def found(text, rel="chapters/page.qmd", ignores=None):
    """Line numbers of the findings in a document string."""
    lines = text.split("\n")
    return [f.line for f in cbf.scan_lines(rel, lines, None, ignores or [])]


# -- references ----------------------------------------------------------------

@pytest.mark.parametrize("line", [
    "![](../images/figures/scan.png){.figure-plate}",
    "![A plot](plot.JPG)",
    "![](<my figure.jpeg>)",
    '<img src="photo.gif" alt="x">',
    "<img alt='x' src=pic.webp>",
    'knitr::include_graphics("figs/a.png")',
    "![](https://example.org/a.png)",
    "![](a.png?raw=true)",
])
def test_bitmap_references_are_flagged(line):
    assert found(line) == [1]


@pytest.mark.parametrize("line", [
    "![](../images/tikz/diagram.svg){.figure-plate}",
    "![](figure.pdf)",
    "![](plot.png.svg)",
    "<img src=\"plot.png.svg\">",
    "The file a.png is mentioned in prose.",
    "Use `![](a.png)` in Markdown.",
])
def test_vector_and_prose_are_clean(line):
    assert found(line) == []


def test_reference_in_a_code_fence_is_not_an_image():
    doc = "```markdown\n![](a.png)\n```\n"
    assert found(doc) == []


def test_reference_in_an_html_comment_is_skipped():
    doc = "<!--\n![](a.png)\n-->\n<!-- ![](b.png) -->\n"
    assert found(doc) == []


def test_ignored_target_is_allowed():
    doc = "![](../images/screenshots/canvas.png)"
    ignores = cbf.diffscope.compile_ignores(["images/screenshots/"])
    assert found(doc, ignores=ignores) == []
    assert found(doc) == [1]


def test_target_resolves_from_the_file_directory():
    assert cbf.resolve_target("chapters/a.qmd", "../images/x.png") == "images/x.png"
    assert cbf.resolve_target("chapters/a.qmd", "/images/x.png") == "images/x.png"
    assert cbf.resolve_target("a.qmd", "https://e.org/x.png") == "https://e.org/x.png"


# -- devices -------------------------------------------------------------------

@pytest.mark.parametrize("line", [
    "    fig-format: png",
    "fig-format: retina",
    "#| fig-format: jpeg",
    "#| dev: png",
    "    dev: 'ragg_png'",
    'knitr::opts_chunk$set(dev = "png")',
    'ggsave("out.png", p)',
    "plt.savefig('fig.png', dpi=300)",
])
def test_raster_devices_are_flagged(line):
    assert found(line) == [1]


@pytest.mark.parametrize("line", [
    "fig-format: svg",
    "#| dev: svglite",
    'knitr::opts_chunk$set(dev = "svglite")',
    'ggsave("out.svg", p)',
    "plt.savefig('fig.svg')",
    "fig-width: 6",
])
def test_vector_devices_are_clean(line):
    assert found(line) == []


def test_markdown_image_in_a_script_is_not_a_reference():
    assert found('doc = "![](a.png)"', rel="tools/make.py") == []
    assert found('<img src="a.png">', rel="tools/make.R") == []


def test_include_graphics_and_devices_count_in_a_script():
    assert found('knitr::include_graphics("a.png")', rel="R/fig.R") == [1]
    assert found("plt.savefig('a.png')", rel="tools/make.py") == [1]
    assert found("    fig-format: png", rel="_quarto.yml") == [1]


def test_device_inside_a_code_fence_is_flagged():
    doc = "```{r}\nggsave('a.png')\n```\n"
    assert found(doc) == [2]


# -- the allow pragma ----------------------------------------------------------

def test_allow_with_reason_on_the_line_exempts_it():
    doc = "![](shot.png) <!-- check-bitmap-figures: allow: screenshot -->"
    assert found(doc) == []


def test_allow_with_reason_on_the_line_above_exempts_it():
    doc = "<!-- check-bitmap-figures: allow: a photo -->\n![](photo.jpg)\n"
    assert found(doc) == []


def test_allow_without_reason_does_not_exempt():
    doc = "<!-- check-bitmap-figures: allow: -->\n![](photo.jpg)\n"
    assert found(doc) == [2]


def test_allow_two_lines_up_does_not_exempt():
    doc = "<!-- check-bitmap-figures: allow: a photo -->\n\n![](photo.jpg)\n"
    assert found(doc) == [3]


# -- diff scoping --------------------------------------------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow: synthetic test address
    _git(tmp_path, "config", "user.name", "t")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write(repo, name, data):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
    _git(repo, "add", name)


def _commit(repo, name, data):
    _write(repo, name, data)
    _git(repo, "commit", "-q", "-m", "c")


PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(64))


def _run(base, ignores=None):
    return cbf.run_check(base, cbf.DEFAULT_GLOBS.split(), ignores or [], False)


def _hits(report):
    return [(f.path, f.line) for f in report.findings]


def test_new_bitmap_file_is_flagged(repo):
    _commit(repo, "page.qmd", "Intro.\n")
    _write(repo, "images/new.png", PNG)
    assert _hits(_run("HEAD")) == [("images/new.png", 1)]


def test_existing_bitmap_file_is_grandfathered(repo):
    _commit(repo, "images/old.png", PNG)
    _write(repo, "page.qmd", "Intro.\n")
    assert _run("HEAD").findings == []


def test_renamed_bitmap_file_is_not_new(repo):
    _commit(repo, "images/old.png", PNG)
    _git(repo, "mv", "images/old.png", "images/renamed.png")
    assert _run("HEAD").findings == []


def test_new_svg_file_is_clean(repo):
    _commit(repo, "page.qmd", "Intro.\n")
    _write(repo, "images/new.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>\n")
    assert _run("HEAD").findings == []


def test_ignored_bitmap_file_is_allowed(repo):
    _commit(repo, "page.qmd", "Intro.\n")
    _write(repo, "images/screenshots/shot.png", PNG)
    ignores = cbf.diffscope.compile_ignores(["images/screenshots/"])
    assert _run("HEAD", ignores).findings == []


def test_new_reference_is_flagged_and_old_one_is_not(repo):
    _commit(repo, "page.qmd", "![](old.png)\n")
    _write(repo, "page.qmd", "![](old.png)\n\n![](new.png)\n")
    assert _hits(_run("HEAD")) == [("page.qmd", 3)]


def test_moved_reference_is_not_new(repo):
    _commit(repo, "a.qmd", "![](old.png)\n")
    _git(repo, "rm", "-q", "a.qmd")
    _write(repo, "b.qmd", "Intro.\n\n![](old.png)\n")
    assert _run("HEAD").findings == []


def test_no_base_ref_skips_instead_of_scanning_the_tree(repo):
    _commit(repo, "images/old.png", PNG)
    report = _run("")
    assert report.skipped and report.findings == []


def test_unresolvable_base_ref_skips(repo):
    _commit(repo, "images/old.png", PNG)
    assert _run("no-such-ref").skipped


def test_whole_tree_reports_every_bitmap_and_reference(repo):
    _commit(repo, "images/old.png", PNG)
    _commit(repo, "page.qmd", "![](images/old.png)\n")
    report = cbf.run_check("", cbf.DEFAULT_GLOBS.split(), [], True)
    assert _hits(report) == [("images/old.png", 1), ("page.qmd", 1)]
    assert report.bitmaps == 1


# -- defaults agree across script, action and workflow ----------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-bitmap-figures.yml").read_text(encoding="utf-8")
    assert cbf._DEFAULT_FAIL is True
    assert "default: 'true'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: true" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert f"default: '{cbf.DEFAULT_GLOBS}'" in action
    assert f"default: '{cbf.DEFAULT_GLOBS}'" in workflow
    for name in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"CBF_{name}" in action


def test_main_exit_codes(repo, monkeypatch):
    _commit(repo, "images/old.png", PNG)
    monkeypatch.setenv("CBF_WHOLE_TREE", "true")
    assert cbf.main() == 1
    monkeypatch.setenv("CBF_FAIL", "false")
    assert cbf.main() == 0
