"""Contract tests for preview/action.yml's changed-chapters wiring.

Ensures that the composite action and its caller reusable workflow agree on
input names, types, step IDs, and output forwarding.
"""

import pathlib
import sys

import pytest

try:
    import yaml
except ImportError as exc:
    raise RuntimeError(
        "PyYAML is required to parse the composite "
        "(install it with `python3 -m pip install pyyaml`)."
    ) from exc

from conftest import write

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ROOT / ".github" / "workflows" / "scripts"))
from workflow_discovery import is_workflows_restored  # noqa: E402

DETECT_STEP = "Detect chapters changed since the published render"
BANNER_STEP = "Add the changed-chapters banner to the preview home page"
HIGHLIGHT_STEP = "Highlight rendered HTML changes in modified chapters"
DOCX_INSTALL_STEP = "Install Python dependencies for DOCX tracked changes"
DOCX_STEP = "Create DOCX tracked changes"
RENDER_STEP = "Render Quarto site"
STAGE_STEP = "Stage site for upload"

DETECT_STEP_ID = "changed-chapters"
DOCX_STEP_ID = "docx-tracked-changes"

DETECT_OUTPUTS = {
    "changed-chapters",
    "any-changed",
    "detection-status",
    "skip-reason",
}

DOCX_OUTPUTS = {
    "docx-status",
    "docx-skip-reason",
    "docx-tracked-changes-files",
    "any-docx-changed",
}

NEW_INPUTS = (
    "detect-changed-chapters",
    "changed-chapters-banner",
    "highlight-changes",
    "changed-chapters-glob",
    "deployed-branch",
    "deployed-subdir",
    "changed-chapters-normalize-patterns",
    "banner-index",
    "docx-tracked-changes",
    "docx-tracked-changes-glob",
)


@pytest.fixture(scope="module")
def action():
    return yaml.safe_load((REPO_ROOT / "preview" / "action.yml").read_text(encoding="utf-8"))


def workflow_call(document):
    triggers = document.get("on", document.get(True))
    assert triggers is not None, "workflow has no trigger block"
    return triggers["workflow_call"]


@pytest.fixture(scope="module")
def workflow():
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    if is_workflows_restored(workflows_dir):
        pytest.skip(".github/workflows/ was restored from default branch (gha#598, gha#765)")
    path = workflows_dir / "preview.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(action):
    return action["runs"]["steps"]


def step_named(steps, name):
    for step in steps:
        if step.get("name") == name:
            return step
    raise KeyError(f"no step named {name!r}")


def step_with_id(steps, step_id):
    for step in steps:
        if step.get("id") == step_id:
            return step
    raise KeyError(f"no step with id {step_id!r}")


def index_of(steps, name):
    for idx, step in enumerate(steps):
        if step.get("name") == name:
            return idx
    raise KeyError(f"no step named {name!r}")


def test_every_new_input_defaults_to_safe_value(action):
    for name in NEW_INPUTS:
        assert name in action["inputs"], f"{name} missing from inputs"
        default = action["inputs"][name]["default"]
        if name in (
            "detect-changed-chapters",
            "changed-chapters-banner",
            "highlight-changes",
            "docx-tracked-changes",
        ):
            assert default == "false"
        elif name == "changed-chapters-glob":
            assert default == "chapters/*.html"
        elif name == "docx-tracked-changes-glob":
            assert default == "chapters/*.docx"
        elif name == "deployed-branch":
            assert default == "gh-pages"


def test_every_declared_output_has_a_description(action):
    for name in action["outputs"]:
        assert action["outputs"][name].get("description"), f"{name} missing description"


def test_every_output_resolves_to_the_changed_chapters_step(action):
    for name in DETECT_OUTPUTS:
        assert (
            action["outputs"][name]["value"]
            == f"${{{{ steps.{DETECT_STEP_ID}.outputs.{name} }}}}"
        )
    for name in DOCX_OUTPUTS:
        assert (
            action["outputs"][name]["value"]
            == f"${{{{ steps.{DOCX_STEP_ID}.outputs.{name} }}}}"
        )


def test_step_id_matches_the_output_references(steps):
    assert step_with_id(steps, DETECT_STEP_ID)["name"] == DETECT_STEP
    assert step_with_id(steps, DOCX_STEP_ID)["name"] == DOCX_STEP


@pytest.mark.parametrize(
    ("step_name", "required"),
    [
        (
            DETECT_STEP,
            {
                "RENDERED_DIR",
                "CHAPTER_GLOB",
                "DEPLOYED_BRANCH",
                "DEPLOYED_SUBDIR",
                "NORMALIZE_PATTERNS",
            },
        ),
        (
            BANNER_STEP,
            {
                "RENDERED_DIR",
                "BANNER_INDEX",
                "CHANGED_CHAPTERS",
                "DETECTION_STATUS",
                "SKIP_REASON",
            },
        ),
        (
            HIGHLIGHT_STEP,
            {
                "RENDERED_DIR",
                "CHANGED_CHAPTERS",
                "DETECTION_STATUS",
                "SKIP_REASON",
                "CHAPTER_GLOB",
                "DEPLOYED_BRANCH",
                "DEPLOYED_SUBDIR",
                "NORMALIZE_PATTERNS",
            },
        ),
        (
            DOCX_STEP,
            {
                "RENDERED_DIR",
                "DOCX_GLOB",
                "DEPLOYED_BRANCH",
                "DEPLOYED_SUBDIR",
            },
        ),
    ],
)
def test_every_env_key_the_scripts_read_is_supplied(steps, step_name, required):
    assert set(step_named(steps, step_name)["env"]) == required


@pytest.mark.parametrize("step_name", [DETECT_STEP, BANNER_STEP, HIGHLIGHT_STEP, DOCX_STEP])
def test_rendered_dir_uses_both_the_path_and_the_output_dir(steps, step_name):
    rendered_dir = step_named(steps, step_name)["env"]["RENDERED_DIR"]
    assert "inputs.path" in rendered_dir
    assert "inputs.output-dir" in rendered_dir


def test_the_banner_and_highlight_imply_the_comparison(steps):
    """`changed-chapters-banner` or `highlight-changes` or `docx-tracked-changes` alone must still run the detection."""
    condition = " ".join(step_named(steps, DETECT_STEP)["if"].split())
    assert "inputs.detect-changed-chapters == 'true'" in condition
    assert "inputs.changed-chapters-banner == 'true'" in condition
    assert "inputs.highlight-changes == 'true'" in condition
    assert "||" in condition


def test_the_banner_step_is_gated_on_its_own_input_only(steps):
    condition = " ".join(step_named(steps, BANNER_STEP)["if"].split())
    assert "inputs.changed-chapters-banner == 'true'" in condition
    assert "inputs.detect-changed-chapters" not in condition


def test_the_docx_step_is_gated_on_its_own_input(steps):
    condition = " ".join(step_named(steps, DOCX_STEP)["if"].split())
    assert "inputs.docx-tracked-changes == 'true'" in condition


@pytest.mark.parametrize("step_name", [DETECT_STEP, BANNER_STEP, HIGHLIGHT_STEP, DOCX_INSTALL_STEP, DOCX_STEP])
def test_steps_stand_down_on_the_closed_event(steps, step_name):
    """Every other step in this composite skips the PR-closed (preview removal)
    path; a step that did not would run with no checkout."""
    assert "github.event.action != 'closed'" in step_named(steps, step_name)["if"]


def test_step_execution_order_before_staging(steps):
    """Staging copies the rendered tree into the upload directory, so modifications
    written afterwards never reach the artifact."""
    assert index_of(steps, RENDER_STEP) < index_of(steps, DETECT_STEP)
    assert index_of(steps, DETECT_STEP) < index_of(steps, BANNER_STEP)
    assert index_of(steps, BANNER_STEP) < index_of(steps, HIGHLIGHT_STEP)
    assert index_of(steps, HIGHLIGHT_STEP) < index_of(steps, DOCX_STEP)
    assert index_of(steps, DOCX_STEP) < index_of(steps, STAGE_STEP)


@pytest.mark.parametrize("step_name", [DETECT_STEP, BANNER_STEP, HIGHLIGHT_STEP, DOCX_STEP])
def test_no_value_reaches_the_run_body_through_interpolation(steps, step_name):
    assert "${{" not in step_named(steps, step_name)["run"]


def test_the_reusable_workflow_forwards_every_new_input(workflow, action):
    build = workflow["jobs"]["build"]["steps"][0]
    for name in NEW_INPUTS:
        assert name in action["inputs"], f"{name} missing from the composite"
        assert name in workflow_call(workflow)["inputs"], f"{name} missing from the workflow"
        assert name in build["with"], f"{name} not forwarded to the composite"


def test_the_reusable_workflow_surfaces_every_output(workflow, action):
    build_step = workflow["jobs"]["build"]["steps"][0]
    assert build_step["id"] == "build"

    job_outputs = workflow["jobs"]["build"]["outputs"]
    workflow_outputs = workflow_call(workflow)["outputs"]
    for name in action["outputs"]:
        assert f"steps.build.outputs.{name} " in job_outputs[name] + " "
        assert f"jobs.build.outputs.{name} " in workflow_outputs[name]["value"] + " "
