"""Run the composite's "Render Quarto site" script against a stub `quarto`.

The stub records each `quarto render` call, so these cases pin which formats
the preview renders for a given combination of inputs and labels -- in
particular that `docx-tracked-changes: true` keeps docx in the render even
under the default `skip-docx: true` (gha#1059), since the tracked-changes
step has nothing to compare without it.
"""

import os
import pathlib
import shutil
import stat
import subprocess

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
RENDER_STEP = "Render Quarto site"

STUB_QUARTO = """#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = "inspect" ]; then
  printf '%s\\n' '{"config": {"format": {"html": {}, "docx": {}}}}'
  exit 0
fi
printf '%s\\n' "$*" >> "$QUARTO_CALLS"
"""


@pytest.fixture(scope="module")
def render_script():
    action = yaml.safe_load((REPO_ROOT / "preview" / "action.yml").read_text(encoding="utf-8"))
    steps = [s for s in action["runs"]["steps"] if s.get("name") == RENDER_STEP]
    assert len(steps) == 1, f"expected exactly one {RENDER_STEP!r} step"
    return steps[0]["run"]


def run_render(tmp_path, script, **env):
    if shutil.which("jq") is None:
        pytest.skip("jq is required by the render script")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    quarto = bin_dir / "quarto"
    quarto.write_text(STUB_QUARTO, encoding="utf-8")
    quarto.chmod(quarto.stat().st_mode | stat.S_IXUSR)
    calls = tmp_path / "calls.txt"
    full_env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "QUARTO_CALLS": str(calls),
        "PROJECT_PATH": ".",
        "RENDER_PROFILE": "",
        "OUTPUT_DIR": "_site",
        "FORMATS": "",
        "SKIP_DOCX": "true",
        "DOCX_TRACKED_CHANGES": "false",
        "TINYTEX": "false",
        "HAS_LABEL_PDF": "false",
        "HAS_LABEL_DOCX": "false",
        "HAS_LABEL_REVEALJS": "false",
        "SETUP_JULIA": "false",
        **env,
    }
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        env=full_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    renders = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return renders, result.stdout


def to_formats(renders):
    """The `--to` value of each render call, or None for a bare render."""
    formats = []
    for line in renders:
        words = line.split()
        formats.append(words[words.index("--to") + 1] if "--to" in words else None)
    return formats


NOTICE = "docx-tracked-changes is on"


def test_empty_formats_render_html_only(tmp_path, render_script):
    renders, stdout = run_render(tmp_path, render_script)
    assert to_formats(renders) == ["html"]
    assert NOTICE not in stdout


def test_empty_formats_add_docx_for_tracked_changes(tmp_path, render_script):
    renders, stdout = run_render(tmp_path, render_script, DOCX_TRACKED_CHANGES="true")
    assert to_formats(renders) == ["docx", "html"]
    assert NOTICE in stdout


def test_default_formats_keep_docx_for_tracked_changes(tmp_path, render_script):
    renders, stdout = run_render(
        tmp_path, render_script, FORMATS="default", DOCX_TRACKED_CHANGES="true"
    )
    # A bare render, so every declared format, docx included, is rendered
    # (gha#1061); tracked changes changes nothing here, so no notice.
    assert to_formats(renders) == [None]
    assert NOTICE not in stdout


def test_explicit_formats_skip_docx(tmp_path, render_script):
    renders, _ = run_render(tmp_path, render_script, FORMATS="html docx")
    assert to_formats(renders) == ["html"]


def test_explicit_formats_keep_docx_for_tracked_changes(tmp_path, render_script):
    renders, stdout = run_render(
        tmp_path, render_script, FORMATS="html docx", DOCX_TRACKED_CHANGES="true"
    )
    assert to_formats(renders) == ["html", "docx"]
    assert NOTICE in stdout


def test_explicit_formats_without_docx_stay_as_written(tmp_path, render_script):
    renders, stdout = run_render(
        tmp_path, render_script, FORMATS="html pdf", DOCX_TRACKED_CHANGES="true"
    )
    assert to_formats(renders) == ["html", "pdf"]
    assert NOTICE not in stdout


def test_no_notice_when_skip_docx_already_off(tmp_path, render_script):
    renders, stdout = run_render(
        tmp_path,
        render_script,
        FORMATS="html docx",
        SKIP_DOCX="false",
        DOCX_TRACKED_CHANGES="true",
    )
    assert to_formats(renders) == ["html", "docx"]
    assert NOTICE not in stdout
