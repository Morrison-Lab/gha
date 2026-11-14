"""The "Plan the cluster render" step writes the command lines condor-batch runs.

The job has no runner environment, so the render's inputs travel on the command
line. These cases run the generated line against a stub `quarto` and pin that
every input arrives intact, quoting included, and that the per-file render
helpers travel with it (gha#1563).
"""

import os
import pathlib
import stat
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAN = ROOT / "quarto-publish" / "plan-cluster-render.sh"

STUB_QUARTO = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$QUARTO_CALLS"
mkdir -p site/site_libs
"""

RENDER_ENV = {
    "PROJECT_PATH": ".",
    "OUTPUT_DIR": "site",
    "RENDER_PROFILE": "website,fast",
    "FORMATS": "html pdf",
    "PER_FILE_FORMATS": "",
    "FAIL_ON_WARN": "false",
    "FORBID_PATTERNS": "",
    "SETUP_JULIA": "false",
}


def plan(tmp_path, **env):
    """Run the planner in tmp_path and return the two lines it wrote."""
    out = tmp_path / "github_output"
    full_env = {
        **os.environ, **RENDER_ENV, **env,
        "GITHUB_ACTION_PATH": str(ROOT / "quarto-publish"),
        "GITHUB_OUTPUT": str(out),
    }
    subprocess.run(["bash", str(PLAN)], cwd=tmp_path, env=full_env, check=True)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "steps<<GHA_CLUSTER_STEPS" and lines[-1] == "GHA_CLUSTER_STEPS"
    return lines[1:-1]


def run_render(tmp_path, line):
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
    result = subprocess.run(["bash", "-c", line], cwd=tmp_path, env=env,
                            capture_output=True, text=True)
    return result, calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []


def test_two_steps_are_planned_and_the_helpers_are_copied(tmp_path):
    lines = plan(tmp_path)
    assert len(lines) == 2
    assert lines[1] == "test -d ./site"
    helpers = tmp_path / ".gha-render"
    for name in ("render-site.sh", "redirect-stubs.py", "render-per-file.py"):
        assert (helpers / name).is_file()
    assert (helpers / "per_file" / "__init__.py").is_file()
    assert not (helpers / "per_file" / "__pycache__").exists()


def test_the_planned_render_runs_with_every_input_intact(tmp_path):
    lines = plan(tmp_path)
    result, calls = run_render(tmp_path, lines[0])
    assert result.returncode == 0, result.stdout + result.stderr
    assert [c.split("--to ")[1].split()[0] for c in calls] == ["html", "pdf"]
    assert all("--profile website,fast" in c for c in calls)
    assert (tmp_path / ".texvar").is_dir()


def test_the_planned_render_gets_a_writable_tex_cache(tmp_path):
    # The cluster job has no usable home, so a PDF render fails unless the
    # TeX cache points under the checkout (epi202#28).
    lines = plan(tmp_path)
    probe = subprocess.run(
        ["bash", "-c", lines[0].replace(
            "bash .gha-render/render-site.sh",
            "bash -c 'printf \"%s|%s\" \"$TEXMFVAR\" \"$TEXMFCACHE\"'")],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    cache = str(tmp_path / ".texvar")
    assert probe.stdout == f"{cache}|{cache}"
    assert (tmp_path / ".texvar").is_dir()


def test_a_multi_line_forbidden_pattern_survives_one_command_line(tmp_path):
    lines = plan(tmp_path, FORBID_PATTERNS="alpha beta\nit's gamma\n")
    assert len(lines) == 2
    assert "\n" not in lines[0]
    probe = subprocess.run(
        ["bash", "-c", lines[0].replace("bash .gha-render/render-site.sh", "bash -c 'printf %s \"$FORBID_PATTERNS\"'")],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    assert probe.stdout == "alpha beta\nit's gamma\n"


def test_a_value_with_a_space_and_a_quote_survives(tmp_path):
    lines = plan(tmp_path, OUTPUT_DIR="out dir's")
    probe = subprocess.run(
        ["bash", "-c", lines[1].replace("test -d", "printf '%s' ")],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout == "./out dir's"


def test_the_action_wires_the_cluster_steps():
    action = yaml.safe_load((ROOT / "quarto-publish" / "action.yml").read_text(encoding="utf-8"))
    assert action["inputs"]["cluster-render"]["default"] == "false"
    steps = {s.get("name"): s for s in action["runs"]["steps"]}
    local = steps["Render Quarto project"]
    assert local["if"] == "inputs.cluster-render != 'true'"
    remote = steps["Render Quarto project on the cluster"]
    assert remote["if"] == "inputs.cluster-render == 'true'"
    assert remote["uses"].endswith("/condor-batch@v3")
    assert remote["with"]["steps"] == "${{ steps.cluster-plan.outputs.steps }}"
    for needle in ("_freeze", ".quarto"):
        assert needle in remote["with"]["output"]
    # The plan step reads the same inputs the local render step does.
    plan_env = steps["Plan the cluster render"]["env"]
    for name, value in local["env"].items():
        if name not in ("PER_FILE_SCRIPT", "REDIRECT_STUBS_SCRIPT"):
            assert plan_env[name] == value


def test_r_packages_add_an_install_step_before_the_render(tmp_path):
    """The image has its own R library, so r-packages are installed in the job (gha#2007)."""
    specs = "deps::.\nany::knitr"
    install, render, check = plan(tmp_path, R_PACKAGES=specs)
    assert install == (
        'Rscript .gha-render/install-cluster-r-packages.R "$PWD/.gha-rlib" '
        ".gha-render/r-packages.txt"
    )
    assert (tmp_path / ".gha-render" / "r-packages.txt").read_text(encoding="utf-8") == specs + "\n"
    assert (tmp_path / ".gha-render" / "install-cluster-r-packages.R").is_file()
    assert ' R_LIBS="$PWD/.gha-rlib" ' in render
    assert check.startswith("test -d ")


def test_no_r_packages_plans_no_install_step(tmp_path):
    lines = plan(tmp_path, R_PACKAGES="")
    assert len(lines) == 2
    assert "R_LIBS" not in lines[0]


def test_use_renv_sends_no_r_packages_to_the_cluster():
    # renv restores the library on the runner side only, so with use-renv the
    # plan gets no r-packages and plans no install step (the case above).
    action = yaml.safe_load((ROOT / "quarto-publish" / "action.yml").read_text(encoding="utf-8"))
    steps = {s.get("name"): s for s in action["runs"]["steps"]}
    r_packages = steps["Plan the cluster render"]["env"]["R_PACKAGES"]
    assert r_packages == "${{ inputs.use-renv != 'true' && inputs.r-packages || '' }}"


TWO_HEADS = "cse-head.cluster.cs.wwu.edu csci-head.cluster.cs.wwu.edu"
THREE_HEADS = TWO_HEADS + " csci-lab-head.cs.wwu.edu:922"


def test_an_empty_cluster_head_spreads_over_the_heads_the_image_reaches():
    # gha#1518: the desktop pool reads the image only from cluster-image-file,
    # so it joins the default list only when that input is set.
    action = yaml.safe_load((ROOT / "quarto-publish" / "action.yml").read_text(encoding="utf-8"))
    assert action["inputs"]["cluster-head"]["default"] == ""
    steps = {s.get("name"): s for s in action["runs"]["steps"]}
    head = steps["Render Quarto project on the cluster"]["with"]["head"]
    assert head == (
        "${{ inputs.cluster-head || (inputs.cluster-image-file != '' && "
        f"'{THREE_HEADS}' || '{TWO_HEADS}') }}}}"
    )


def test_the_reusable_workflow_leaves_cluster_head_empty():
    workflows = ROOT / ".github" / "workflows"
    # A review job restores the default branch's workflows (gha#598, gha#765).
    if (workflows / ".restored-from-default-branch").is_file():
        pytest.skip("workflows restored from the default branch")
    workflow = yaml.safe_load(
        (workflows / "quarto-publish.yml").read_text(encoding="utf-8")
    )
    assert workflow[True]["workflow_call"]["inputs"]["cluster-head"]["default"] == ""
