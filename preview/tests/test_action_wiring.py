"""Pin the composite and reusable-workflow wiring for preview steps.

Pins the composite and reusable-workflow wiring -- the `if:` gates, the `env:` assembly,
the step ordering, and the composite outputs.
"""

import pathlib
import sys

import pytest

try:
    import yaml
except ImportError as exc:  # pragma: no cover - depends on the runner image
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
    matches = [s for s in steps if s.get("name") == name]
    assert len(matches) == 1, f"expected exactly one step named {name!r}, found {len(matches)}"
    return matches[0]


def index_of(steps, name):
    for position, step in enumerate(steps):
        if step.get("name") == name:
            return position
    raise AssertionError(f"no step named {name!r}")


def test_the_steps_keep_the_ids_every_output_references(steps, action):
    assert step_named(steps, DETECT_STEP)["id"] == DETECT_STEP_ID
    assert step_named(steps, DOCX_STEP)["id"] == DOCX_STEP_ID
    for name in DETECT_OUTPUTS:
        assert f"steps.{DETECT_STEP_ID}.outputs.{name}" in action["outputs"][name]["value"]
    for name in DOCX_OUTPUTS:
        assert f"steps.{DOCX_STEP_ID}.outputs.{name}" in action["outputs"][name]["value"]


def test_each_output_reads_its_own_name(action):
    for name in DETECT_OUTPUTS:
        assert f"steps.{DETECT_STEP_ID}.outputs.{name}" in action["outputs"][name]["value"]
    for name in DOCX_OUTPUTS:
        assert f"steps.{DOCX_STEP_ID}.outputs.{name}" in action["outputs"][name]["value"]


def test_the_composite_declares_exactly_what_the_scripts_write(
    action, detector, docx_generator, monkeypatch, repo_factory
):
    from test_create_docx_tracked_changes import make_docx

    page = "<html><body><main><h1>One</h1></main></body></html>"
    docx_bytes = make_docx(["One"])
    work = repo_factory(published={"chapters/01.html": page, "chapters/01.docx": docx_bytes})
    rendered = write(work, "_site/chapters/01.html", page).parent.parent
    write(work, "_site/chapters/01.docx", docx_bytes)
    output_file = rendered.parent / "wiring-output.txt"
    output_file.write_text("", encoding="utf-8")

    for key, value in {
        "REPO_DIR": str(work),
        "RENDERED_DIR": str(rendered),
        "CHAPTER_GLOB": "chapters/*.html",
        "DOCX_GLOB": "chapters/*.docx",
        "GITHUB_OUTPUT": str(output_file),
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("DEPLOYED_REMOTE", "DEPLOYED_BRANCH", "DEPLOYED_SUBDIR", "NORMALIZE_PATTERNS"):
        monkeypatch.delenv(key, raising=False)

    detector.main()
    from conftest import read_outputs
    detector_written = set(read_outputs.parse(output_file.read_text(encoding="utf-8")))
    assert detector_written == DETECT_OUTPUTS

    output_file.write_text("", encoding="utf-8")
    docx_generator.main()
    docx_written = set(read_outputs.parse(output_file.read_text(encoding="utf-8")))
    assert docx_written == DOCX_OUTPUTS

    assert (detector_written | docx_written) == set(action["outputs"])


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


@pytest.mark.parametrize("step_name", [DETECT_STEP, BANNER_STEP, DOCX_STEP])
def test_rendered_dir_uses_both_the_path_and_the_output_dir(steps, step_name):
    rendered_dir = step_named(steps, step_name)["env"]["RENDERED_DIR"]
    assert "inputs.path" in rendered_dir
    assert "inputs.output-dir" in rendered_dir


def test_the_banner_implies_the_comparison(steps):
    condition = " ".join(step_named(steps, DETECT_STEP)["if"].split())
    assert "inputs.detect-changed-chapters == 'true'" in condition
    assert "inputs.changed-chapters-banner == 'true'" in condition
    assert "||" in condition


def test_the_banner_step_is_gated_on_its_own_input_only(steps):
    condition = " ".join(step_named(steps, BANNER_STEP)["if"].split())
    assert "inputs.changed-chapters-banner == 'true'" in condition
    assert "inputs.detect-changed-chapters" not in condition


def test_the_docx_step_is_gated_on_its_own_input(steps):
    condition = " ".join(step_named(steps, DOCX_STEP)["if"].split())
    assert "inputs.docx-tracked-changes == 'true'" in condition


@pytest.mark.parametrize("step_name", [DETECT_STEP, BANNER_STEP, DOCX_INSTALL_STEP, DOCX_STEP])
def test_steps_stand_down_on_the_closed_event(steps, step_name):
    assert "github.event.action != 'closed'" in step_named(steps, step_name)["if"]


def test_step_execution_order_before_staging(steps):
    assert index_of(steps, RENDER_STEP) < index_of(steps, DETECT_STEP)
    assert index_of(steps, DETECT_STEP) < index_of(steps, BANNER_STEP)
    assert index_of(steps, BANNER_STEP) < index_of(steps, DOCX_STEP)
    assert index_of(steps, DOCX_STEP) < index_of(steps, STAGE_STEP)


@pytest.mark.parametrize("step_name", [DETECT_STEP, BANNER_STEP, DOCX_STEP])
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
