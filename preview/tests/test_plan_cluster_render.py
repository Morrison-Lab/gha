"""The "Plan the cluster render" step writes the command lines condor-batch runs.

The job has no runner environment, so the render's inputs travel on the
command line. These cases run the generated line against a stub `quarto` and
pin that every input arrives intact, quoting included (gha#1618).
"""

import os
import pathlib
import shutil
import stat
import subprocess

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAN = REPO_ROOT / "preview" / "plan-cluster-render.sh"

STUB_QUARTO = """#!/usr/bin/env bash
if [ "$1" = "inspect" ]; then
  printf '%s\\n' '{"config": {"format": {"html": {}, "docx": {}}}}'
  exit 0
fi
printf '%s\\n' "$*" >> "$QUARTO_CALLS"
"""

RENDER_ENV = {
    "PROJECT_PATH": ".",
    "RENDER_PROFILE": "website,fast",
    "OUTPUT_DIR": "_site",
    "FORMATS": "html docx",
    "SKIP_DOCX": "false",
    "DOCX_TRACKED_CHANGES": "false",
    "TINYTEX": "false",
    "HAS_LABEL_PDF": "false",
    "HAS_LABEL_DOCX": "false",
    "HAS_LABEL_REVEALJS": "false",
    "SETUP_JULIA": "false",
    "INCREMENTAL_MODE": "",
    "INCREMENTAL_PAGES": "./_incremental_pages.txt",
}


def plan(tmp_path, **env):
    """Run the planner in tmp_path and return the two lines it wrote."""
    out = tmp_path / "github_output"
    full_env = {
        **os.environ, **RENDER_ENV, **env,
        "GITHUB_ACTION_PATH": str(REPO_ROOT / "preview"),
        "GITHUB_OUTPUT": str(out),
    }
    subprocess.run(["bash", str(PLAN)], cwd=tmp_path, env=full_env, check=True)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "steps<<GHA_CLUSTER_STEPS" and lines[-1] == "GHA_CLUSTER_STEPS"
    return lines[1:-1]


def test_two_steps_are_planned_and_the_scripts_are_copied(tmp_path):
    lines = plan(tmp_path)
    assert len(lines) == 2
    assert lines[1] == "test -d ./_site"
    assert (tmp_path / ".gha-render-site.sh").is_file()
    assert (tmp_path / ".gha-redirect-stubs.py").is_file()


def test_the_planned_render_runs_with_every_input_intact(tmp_path):
    if shutil.which("jq") is None:
        pytest.skip("jq is required by the render script")
    lines = plan(tmp_path, RENDER_PROFILE="website,fast")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    quarto = bin_dir / "quarto"
    quarto.write_text(STUB_QUARTO, encoding="utf-8")
    quarto.chmod(quarto.stat().st_mode | stat.S_IXUSR)
    calls = tmp_path / "calls.txt"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "QUARTO_CALLS": str(calls),
    }
    result = subprocess.run(["bash", "-c", lines[0]], cwd=tmp_path, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    renders = calls.read_text(encoding="utf-8").splitlines()
    # FORMATS "html docx" with SKIP_DOCX false renders both, under the profile.
    assert [r.split("--to ")[1].split()[0] for r in renders] == ["html", "docx"]
    assert all("--profile website,fast" in r for r in renders)
    assert (tmp_path / ".texvar").is_dir()


def test_a_value_with_a_space_and_a_quote_survives(tmp_path):
    lines = plan(tmp_path, OUTPUT_DIR="out dir's")
    probe = subprocess.run(
        ["bash", "-c", lines[1].replace("test -d", "printf '%s' ")],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout == "./out dir's"


def test_the_action_wires_the_cluster_steps():
    action = yaml.safe_load((REPO_ROOT / "preview" / "action.yml").read_text(encoding="utf-8"))
    assert action["inputs"]["cluster-render"]["default"] == "false"
    steps = {s.get("name"): s for s in action["runs"]["steps"]}
    local = steps["Render Quarto site"]
    assert "inputs.cluster-render != 'true'" in local["if"]
    remote = steps["Render Quarto site on the cluster"]
    assert "inputs.cluster-render == 'true'" in remote["if"]
    assert remote["uses"].endswith("/condor-batch@v3")
    # Renaming the plan step must fail here, not silently pass an empty list.
    assert remote["with"]["steps"] == "${{ steps.cluster-plan.outputs.steps }}"
    # The freeze cache and Quarto's project state come back with the site.
    for needle in ("_freeze", ".quarto", "_quarto_preview_render.log"):
        assert needle in remote["with"]["output"]


def test_r_packages_add_an_install_step_before_the_render(tmp_path):
    """The image has its own R library, so r-packages are installed in the job (gha#2007)."""
    specs = "any::knitr\nMorrison-Lab/qnp"
    install, render, check = plan(tmp_path, R_PACKAGES=specs)
    assert install == 'Rscript .gha-install-r-packages.R "$PWD/.gha-rlib" .gha-r-packages.txt'
    assert (tmp_path / ".gha-r-packages.txt").read_text(encoding="utf-8") == specs + "\n"
    assert (tmp_path / ".gha-install-r-packages.R").is_file()
    assert ' R_LIBS="$PWD/.gha-rlib" ' in render
    assert check.startswith("test -d ")


def test_no_r_packages_plans_no_install_step(tmp_path):
    lines = plan(tmp_path, R_PACKAGES="")
    assert len(lines) == 2
    assert "R_LIBS" not in lines[0]


TWO_HEADS = "cse-head.cluster.cs.wwu.edu csci-head.cluster.cs.wwu.edu"
THREE_HEADS = TWO_HEADS + " csci-lab-head.cs.wwu.edu:922"


def test_an_empty_cluster_head_spreads_over_the_heads_the_image_reaches():
    # gha#1518: the desktop pool reads the image only from cluster-image-file,
    # so it joins the default list only when that input is set.
    action = yaml.safe_load((REPO_ROOT / "preview" / "action.yml").read_text(encoding="utf-8"))
    assert action["inputs"]["cluster-head"]["default"] == ""
    steps = {s.get("name"): s for s in action["runs"]["steps"]}
    head = steps["Render Quarto site on the cluster"]["with"]["head"]
    assert head == (
        "${{ inputs.cluster-head || (inputs.cluster-image-file != '' && "
        f"'{THREE_HEADS}' || '{TWO_HEADS}') }}}}"
    )
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "preview.yml").read_text(encoding="utf-8")
    )
    assert workflow[True]["workflow_call"]["inputs"]["cluster-head"]["default"] == ""
