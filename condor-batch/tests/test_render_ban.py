"""Guard for the self-hosted render ban (gha#2108).

Ezra, 2026-11-17: CI rendering is banned on the self-hosted runners
(cf463-01, cf463-02) and on his Mac. A self-hosted runner may only submit a
render to the cluster. These tests fail if a render composite can render on
the runner itself: through condor-batch's local fallback, through its own
local render step, or through the equation-render crawl's headless browser.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

RENDER_COMPOSITES = [
    "preview/action.yml",
    "quarto-publish/action.yml",
    ".github/actions/student-copy-render/action.yml",
]
# Composites that also have a local render step get a refusal step first.
# student-copy-render has no local render step: it renders only through
# condor-batch, whose disabled fallback already covers it.
GUARDED = ["preview/action.yml", "quarto-publish/action.yml"]


def steps(rel):
    return yaml.safe_load((ROOT / rel).read_text())["runs"]["steps"]


def test_condor_batch_has_fallback_switch():
    action = yaml.safe_load(
        (ROOT / ".github/actions/condor-batch/action.yml").read_text())
    assert action["inputs"]["allow-local-fallback"]["default"] == "true"
    run = action["runs"]["steps"][0]["run"]
    assert 'if [ "${ALLOW_LOCAL_FALLBACK:-true}" = "false" ] && [ "${RUNNER_ENVIRONMENT:-}" = "self-hosted" ]' in run
    refusal = run.split("run_local()", 1)[1].split("::notice::running the steps", 1)[0]
    assert "exit 1" in refusal


def test_render_composites_disable_local_fallback():
    for rel in RENDER_COMPOSITES:
        uses = [s for s in steps(rel) if "condor-batch" in str(s.get("uses", ""))]
        assert uses, f"{rel}: no condor-batch step"
        for s in uses:
            assert s.get("with", {}).get("allow-local-fallback") == "false", (
                f"{rel}: '{s['name']}' may fall back to rendering on the runner")


def test_render_composites_refuse_self_hosted_local_render():
    for rel in GUARDED:
        first = steps(rel)[0]
        assert "self-hosted" in first["if"] and "cluster-render != 'true'" in first["if"], rel
        assert "exit 1" in first["run"], rel


def test_equation_crawl_skips_on_self_hosted():
    all_steps = steps("check-equation-renders/action.yml")
    for s in all_steps[1:]:
        assert s.get("if") == "runner.environment != 'self-hosted'", (
            f"'{s['name']}' would start a browser on a self-hosted runner")
