"""The "Render Quarto project" step runs quarto-publish/render-site.sh.

The step moved out of action.yml so a cluster job can run it (gha#1563). These
cases run the script against a stub `quarto` and pin what the inline step did:
the per-format split render, the warning gate, and the forbidden-pattern gate.
"""

import os
import pathlib
import stat
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quarto-publish" / "render-site.sh"

STUB_QUARTO = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$QUARTO_CALLS"
mkdir -p site/site_libs
if [ -n "${STUB_OUTPUT:-}" ]; then printf '%s\\n' "$STUB_OUTPUT"; fi
"""


def render(tmp_path, **env):
    """Run the script in tmp_path and return (result, quarto call lines)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    quarto = bin_dir / "quarto"
    quarto.write_text(STUB_QUARTO, encoding="utf-8")
    quarto.chmod(quarto.stat().st_mode | stat.S_IXUSR)
    calls = tmp_path / "calls.txt"
    full_env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "QUARTO_CALLS": str(calls),
        "PROJECT_PATH": ".",
        "OUTPUT_DIR": "site",
        "RENDER_PROFILE": "website",
        "FORMATS": "html pdf",
        "PER_FILE_FORMATS": "",
        "PER_FILE_SCRIPT": str(ROOT / "quarto-publish" / "render-per-file.py"),
        "REDIRECT_STUBS_SCRIPT": str(ROOT / "quarto-publish" / "redirect-stubs.py"),
        "FAIL_ON_WARN": "false",
        "FORBID_PATTERNS": "",
        "SETUP_JULIA": "false",
        **env,
    }
    result = subprocess.run(["bash", str(SCRIPT)], cwd=tmp_path, env=full_env,
                            capture_output=True, text=True)
    lines = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, lines


def test_each_format_renders_once_and_later_ones_keep_the_output(tmp_path):
    result, calls = render(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [c.split("--to ")[1].split()[0] for c in calls] == ["html", "pdf"]
    assert "--no-clean" not in calls[0]
    assert "--no-clean" in calls[1]
    assert all("--profile website" in c for c in calls)


def test_no_formats_is_one_render_of_the_project(tmp_path):
    result, calls = render(tmp_path, FORMATS="")
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls) == 1 and "--to" not in calls[0]


def test_a_warning_fails_only_when_asked(tmp_path):
    ok, _ = render(tmp_path / "off", STUB_OUTPUT="WARN something")
    assert ok.returncode == 0
    bad, _ = render(tmp_path / "on", FAIL_ON_WARN="true", STUB_OUTPUT="WARN something")
    assert bad.returncode == 1


def test_a_forbidden_pattern_fails_the_render(tmp_path):
    result, _ = render(tmp_path, FORBID_PATTERNS="  nope  \n", STUB_OUTPUT="a nope line")
    assert result.returncode == 1
    assert "forbidden pattern 'nope'" in result.stdout + result.stderr


def test_the_action_runs_the_script_with_the_same_environment():
    action = yaml.safe_load((ROOT / "quarto-publish" / "action.yml").read_text(encoding="utf-8"))
    step = next(s for s in action["runs"]["steps"] if s.get("name") == "Render Quarto project")
    assert step["run"] == 'bash "$GITHUB_ACTION_PATH/render-site.sh"'
    for name in ("PROJECT_PATH", "OUTPUT_DIR", "RENDER_PROFILE", "FORMATS",
                 "PER_FILE_FORMATS", "PER_FILE_SCRIPT", "REDIRECT_STUBS_SCRIPT",
                 "FAIL_ON_WARN", "FORBID_PATTERNS", "SETUP_JULIA"):
        assert name in step["env"]
