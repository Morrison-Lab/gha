"""Pin the composite and reusable-workflow wiring for the changed-chapters steps.

The gha#763 review's second finding: the selftest job invokes
`detect-changed-chapters.py` and `add-home-banner.py` directly, so the step
wiring added to `preview/action.yml` -- the `if:` gates, the `env:` assembly,
the step ordering, and the four composite outputs -- is never proven by CI.

A live `uses: ./preview` call is the usual proof and is out of reach here: the
composite installs R, renv and Chrome and renders the caller's own Quarto
project, which a selftest job cannot stand up (CLAUDE.md says so for this
composite specifically). So this pins the wiring statically instead, the way
`run-r-cmd-check-workflow-tests.py` and `run-version-check-workflow-tests.py`
already do for workflows a live run cannot reach.

What it is for is the class of edit that breaks the feature while every other
check stays green:

  * renaming the detect step's `id`, which silently empties all four outputs;
  * moving the banner step after `Stage site for upload`, so the uploaded
    artifact carries an un-bannered home page;
  * dropping an `env:` key, so the script falls back to a default;
  * composing `RENDERED_DIR` from `inputs.path` alone, which is correct only
    for the default `output-dir`;
  * adding an output to the script, or to `action.yml`, without the other.

None of those produces an error. Each produces a quietly wrong preview.
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
RENDER_STEP = "Render Quarto site"
STAGE_STEP = "Stage site for upload"

DETECT_STEP_ID = "changed-chapters"

NEW_INPUTS = (
    "detect-changed-chapters",
    "changed-chapters-banner",
    "changed-chapters-glob",
    "deployed-branch",
    "deployed-subdir",
    "changed-chapters-normalize-patterns",
    "banner-index",
)


@pytest.fixture(scope="module")
def action():
    return yaml.safe_load((REPO_ROOT / "preview" / "action.yml").read_text(encoding="utf-8"))


def workflow_call(document):
    """The `workflow_call:` block, whichever key YAML gave it.

    YAML 1.1 resolves a bare `on` to the boolean True, so a workflow's trigger
    block lands under `True` rather than `"on"` unless the author quoted it.
    Accepting both is what keeps this suite from depending on that quoting.
    """
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


def test_the_detect_step_keeps_the_id_every_output_references(steps, action):
    """A renamed id empties all four outputs and nothing goes red."""
    assert step_named(steps, DETECT_STEP)["id"] == DETECT_STEP_ID
    for name, spec in action["outputs"].items():
        assert f"steps.{DETECT_STEP_ID}.outputs." in spec["value"], name


def test_each_output_reads_its_own_name(action):
    """`changed-chapters: steps.x.outputs.any-changed` would be silently wrong."""
    for name, spec in action["outputs"].items():
        assert f"steps.{DETECT_STEP_ID}.outputs.{name} " in spec["value"] + " ", name


def test_the_composite_declares_exactly_what_the_script_writes(
    action, detector, monkeypatch, repo_factory
):
    """The gha#303 precedent: two declarations of one contract must agree.

    Derived by running a real detection rather than by reading the script's
    source, so the test measures what the script does rather than what it says.
    """
    page = "<html><body><main><h1>One</h1></main></body></html>"
    work = repo_factory(published={"chapters/01.html": page})
    rendered = write(work, "_site/chapters/01.html", page).parent.parent
    output_file = rendered.parent / "wiring-output.txt"
    output_file.write_text("", encoding="utf-8")

    for key, value in {
        "REPO_DIR": str(work),
        "RENDERED_DIR": str(rendered),
        "CHAPTER_GLOB": "chapters/*.html",
        "GITHUB_OUTPUT": str(output_file),
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("DEPLOYED_REMOTE", "DEPLOYED_BRANCH", "DEPLOYED_SUBDIR", "NORMALIZE_PATTERNS"):
        monkeypatch.delenv(key, raising=False)
    detector.main()

    from conftest import read_outputs

    written = set(read_outputs.parse(output_file.read_text(encoding="utf-8")))
    assert written == set(action["outputs"])


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
    ],
)
def test_every_env_key_the_scripts_read_is_supplied(steps, step_name, required):
    """A dropped key is not an error; the script falls back to a default."""
    assert set(step_named(steps, step_name)["env"]) == required


@pytest.mark.parametrize("step_name", [DETECT_STEP, BANNER_STEP])
def test_rendered_dir_uses_both_the_path_and_the_output_dir(steps, step_name):
    """Composing it from `inputs.path` alone is correct only for the default
    `output-dir`, so the bug hides until a consumer sets one."""
    rendered_dir = step_named(steps, step_name)["env"]["RENDERED_DIR"]
    assert "inputs.path" in rendered_dir
    assert "inputs.output-dir" in rendered_dir


def test_the_banner_implies_the_comparison(steps):
    """`changed-chapters-banner` alone must still run the detection, or the
    banner renders against empty outputs and reports no changes."""
    condition = " ".join(step_named(steps, DETECT_STEP)["if"].split())
    assert "inputs.detect-changed-chapters == 'true'" in condition
    assert "inputs.changed-chapters-banner == 'true'" in condition
    assert "||" in condition


def test_the_banner_step_is_gated_on_its_own_input_only(steps):
    condition = " ".join(step_named(steps, BANNER_STEP)["if"].split())
    assert "inputs.changed-chapters-banner == 'true'" in condition
    assert "inputs.detect-changed-chapters" not in condition


@pytest.mark.parametrize("step_name", [DETECT_STEP, BANNER_STEP])
def test_both_steps_stand_down_on_the_closed_event(steps, step_name):
    """Every other step in this composite skips the PR-closed (preview removal)
    path; a step that did not would run with no checkout."""
    assert "github.event.action != 'closed'" in step_named(steps, step_name)["if"]


def test_the_banner_is_written_before_the_site_is_staged(steps):
    """Staging copies the rendered tree into the upload directory, so a banner
    written afterwards never reaches the artifact -- and the preview looks
    exactly like a run where no chapter changed."""
    assert index_of(steps, RENDER_STEP) < index_of(steps, DETECT_STEP)
    assert index_of(steps, DETECT_STEP) < index_of(steps, BANNER_STEP)
    assert index_of(steps, BANNER_STEP) < index_of(steps, STAGE_STEP)


@pytest.mark.parametrize("step_name", [DETECT_STEP, BANNER_STEP])
def test_no_value_reaches_the_run_body_through_interpolation(steps, step_name):
    """`skip-reason` and `changed-chapters` are built from git's error text and
    from file names, so interpolating either into a `run:` body is command
    injection. They must arrive through `env:`."""
    assert "${{" not in step_named(steps, step_name)["run"]


def test_the_reusable_workflow_forwards_every_new_input(workflow, action):
    build = workflow["jobs"]["build"]["steps"][0]
    for name in NEW_INPUTS:
        assert name in action["inputs"], f"{name} missing from the composite"
        assert name in workflow_call(workflow)["inputs"], f"{name} missing from the workflow"
        assert name in build["with"], f"{name} not forwarded to the composite"


def test_the_reusable_workflow_surfaces_every_output(workflow, action):
    """Two hops -- step to job, job to workflow -- and a break in either leaves
    a consumer reading an empty string rather than seeing an error."""
    build_step = workflow["jobs"]["build"]["steps"][0]
    assert build_step["id"] == "build"

    job_outputs = workflow["jobs"]["build"]["outputs"]
    workflow_outputs = workflow_call(workflow)["outputs"]
    for name in action["outputs"]:
        assert f"steps.build.outputs.{name} " in job_outputs[name] + " "
        assert f"jobs.build.outputs.{name} " in workflow_outputs[name]["value"] + " "
