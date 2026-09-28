"""Unit tests for check-orphaned-images.

The fixtures are throwaway git repositories built in ``tmp_path`` per case,
never committed. The images are a few bytes of text with an image
extension: the check never opens an image, only lists it.

The cases worth keeping if this is ever trimmed:

  * each way a source names an image (Markdown, YAML, CSS url(), HTML src,
    percent-encoding, a name with a space) counts as a use -- the direction
    that would bury real findings under false ones
  * an untracked image is not reported
  * an unresolvable base-ref SKIPS rather than scanning the whole tree
  * the default is warn-only, and `fail: true` blocks

check-orphaned-images.py is not an importable module name (the hyphen), so
it is loaded by path, the same pattern check-new-line-breaks/tests uses.
"""

from __future__ import annotations

import importlib.util
import subprocess
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_MOD_PATH = _HERE.parent / "check-orphaned-images.py"
_ACTION_YML = _HERE.parent / "action.yml"
_WORKFLOW_YML = _HERE.parent.parent / ".github" / "workflows" / "check-orphaned-images.yml"
_spec = importlib.util.spec_from_file_location("check_orphaned_images", _MOD_PATH)
assert _spec is not None and _spec.loader is not None
oi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oi)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path: Path, files: dict, commit: bool = True) -> Path:
    if not (tmp_path / ".git").exists():
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "config", "user.email", "t@example.invalid")
        _git(tmp_path, "config", "user.name", "t")
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(tmp_path, "add", "-A")
    if commit:
        _git(tmp_path, "commit", "-q", "-m", "x", "--allow-empty")
    return tmp_path


def _main(tmp_path, monkeypatch, **env) -> int:
    monkeypatch.chdir(tmp_path)
    for key in ("OI_PATHS", "OI_EXTENSIONS", "OI_SOURCE_EXTENSIONS",
                "OI_PATHS_IGNORE", "OI_BASE_REF", "OI_FAIL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return oi.main()


def _orphans(capsys) -> list:
    return [
        line.split("file=", 1)[1].split(",", 1)[0]
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(("::warning file=", "::error file="))
    ]


def test_every_way_of_naming_an_image_counts_as_a_use(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {
        "page.qmd": (
            "![a](images/md.png){fig-alt=\"x\"}\n"
            "![b](<images/with space.png>)\n"
            "![c](images/pct%20name.png)\n"
            '<img src="../images/html.svg">\n'
            "Trailing period images/prose.jpg.\n"
        ),
        "_quarto.yml": "website:\n  favicon: images/favicon.png\n",
        "custom.scss": "body { background: url('images/bg.webp'); }\n",
        "filters/f.lua": 'local logo = "Logo.PNG"\n',
        "images/md.png": "x", "images/with space.png": "x",
        "images/pct name.png": "x", "images/html.svg": "x",
        "images/prose.jpg": "x", "images/favicon.png": "x",
        "images/bg.webp": "x", "images/logo.png": "x",
        "images/unused.png": "x", "images/sub/also-unused.gif": "x",
    })
    assert _main(tmp_path, monkeypatch) == 0
    assert _orphans(capsys) == ["images/sub/also-unused.gif", "images/unused.png"]


def test_untracked_images_and_other_extensions_are_not_examined(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"page.qmd": "# p\n", "notes.txt": "x", "data.csv": "x"})
    (tmp_path / "scratch.png").write_text("x")
    assert _main(tmp_path, monkeypatch) == 0
    out = capsys.readouterr().out
    assert "Examined 0 image(s)" in out


def test_a_script_counts_only_when_its_extension_is_added(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"make.R": 'ggsave("figs/plot.png")\n', "figs/plot.png": "x"})
    _main(tmp_path, monkeypatch)
    assert _orphans(capsys) == ["figs/plot.png"]
    _main(tmp_path, monkeypatch, OI_SOURCE_EXTENSIONS=".qmd, .R")
    assert _orphans(capsys) == []


def test_paths_and_paths_ignore(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"a/x.png": "x", "b/y.png": "x", "b/gen/z.png": "x"})
    _main(tmp_path, monkeypatch, OI_PATHS="b")
    assert _orphans(capsys) == ["b/gen/z.png", "b/y.png"]
    _main(tmp_path, monkeypatch, OI_PATHS_IGNORE="b/gen, a/*.png")
    assert _orphans(capsys) == ["b/y.png"]


def test_base_ref_reports_only_added_images(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"old.png": "x", "page.qmd": "# p\n"})
    _repo(tmp_path, {"new.png": "x"})
    _main(tmp_path, monkeypatch, OI_BASE_REF="HEAD~1")
    assert _orphans(capsys) == ["new.png"]


def test_unresolvable_base_ref_skips_rather_than_scanning_everything(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, {"old.png": "x"})
    assert _main(tmp_path, monkeypatch, OI_BASE_REF="no-such-ref", OI_FAIL="true") == 0
    out = capsys.readouterr().out
    assert out.startswith("::warning::Skipping the orphaned-images check")
    assert "old.png" not in out


@pytest.mark.parametrize("value,expected", [("", 0), ("false", 0), ("yes", 0), ("true", 1), (" TRUE ", 1)])
def test_warn_only_by_default_and_true_blocks(tmp_path, monkeypatch, value, expected):
    _repo(tmp_path, {"unused.png": "x"})
    assert _main(tmp_path, monkeypatch, OI_FAIL=value) == expected


def test_empty_extensions_is_an_error(tmp_path, monkeypatch):
    _repo(tmp_path, {"unused.png": "x"})
    assert _main(tmp_path, monkeypatch, OI_EXTENSIONS=" , ") == 1


def test_long_line_is_linear(tmp_path, monkeypatch, capsys):
    blob = "![](data:image/png;base64," + "A" * 3_000_000 + ")\n![](used.png)\n"
    _repo(tmp_path, {"page.html": blob, "used.png": "x", "unused.png": "x"})
    start = time.monotonic()
    _main(tmp_path, monkeypatch)
    assert time.monotonic() - start < 20
    assert _orphans(capsys) == ["unused.png"]


# -- defaults declared in three places must agree ---------------------------

# Parsed with a line scan rather than a YAML library on purpose: the selftest
# job installs only pytest.

def _declared_default(path: Path, name: str) -> str:
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f"{name}:":
            indent = len(line) - len(line.lstrip())
            for body in lines[i + 1:]:
                if body.strip() and len(body) - len(body.lstrip()) <= indent:
                    break
                if body.strip().startswith("default:"):
                    return body.split("default:", 1)[1].strip().strip("'")
    raise AssertionError(f"no default for {name} in {path}")


@pytest.mark.parametrize("path", [_ACTION_YML, _WORKFLOW_YML])
@pytest.mark.parametrize("name,script_default", [
    ("extensions", oi.DEFAULT_EXTENSIONS),
    ("source-extensions", oi.DEFAULT_SOURCE_EXTENSIONS),
    ("paths", "."),
    ("fail", "false"),
])
def test_declared_defaults_match_the_script(path, name, script_default):
    assert _declared_default(path, name) == script_default
