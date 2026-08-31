#!/usr/bin/env python3
"""Assert load-bearing contracts of the r-cmd-check reusable workflow.

The reusable workflow wraps r-lib/actions and is not exercised end-to-end
in this repo (gha is not an R package; a 5-way matrix is a real write of
CI time). What can go silently wrong is YAML shape: dropping cache: false
on the hard job, gating that job off pull_request, copying upstream's
head_ref-only concurrency group, omitting error-on from the full matrix,
forwarding it on the hard job, leaving _R_CHECK_CRAN_INCOMING_ unset
(r-lib then forces it false), or skipping Quarto on every ubuntu cell.

This script parses the workflow and the example stub and asserts those
contracts. Mutations that reverse each one are confirmed to fail in
--self-test rather than assumed to.

Usage::

    python3 run-r-cmd-check-workflow-tests.py
    python3 run-r-cmd-check-workflow-tests.py --self-test
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys
import tempfile

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the runner image
    print(
        "::error::PyYAML is required to parse the r-cmd-check workflow "
        "(install it with `python3 -m pip install pyyaml`).",
        file=sys.stderr,
    )
    sys.exit(1)


REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
DEFAULT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "r-cmd-check.yml"
DEFAULT_EXAMPLE = REPO_ROOT / "examples" / "r-cmd-check.yml"

REQUIRED_INPUTS = (
    "hard",
    "extra-packages",
    "error-on",
    "cran-incoming-remote",
    "force-suggests",
    "stop-on-invalid-numeric-version-inputs",
    "setup-pandoc",
    "install-quarto",
    "setup-julia",
    "linux-container",
    "checkout-submodules",
    "timeout-minutes",
    "build-args",
)

HARD_EXTRAS = ("knitr", "rcmdcheck", "rmarkdown", "curl", "testthat")


def die(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    sys.exit(1)


def load_yaml(path: pathlib.Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def workflow_call_inputs(doc: dict) -> dict:
    # PyYAML 1.1 parses a bare `on:` key as the boolean True.
    triggers = doc.get(True, doc.get("on"))
    if not isinstance(triggers, dict):
        die("workflow has no `on:` mapping")
    call = triggers.get("workflow_call")
    if not isinstance(call, dict):
        die("workflow is not a workflow_call reusable workflow")
    inputs = call.get("inputs")
    if not isinstance(inputs, dict):
        die("workflow_call declares no inputs")
    return inputs


def find_step(job: dict, uses_needle: str) -> dict | None:
    for step in job.get("steps") or []:
        if not isinstance(step, dict):
            continue
        uses = str(step.get("uses") or "")
        if uses_needle in uses:
            return step
    return None


def check_workflow(path: pathlib.Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    doc = load_yaml(path)
    if not isinstance(doc, dict):
        return [f"{path}: not a YAML mapping"]

    if "concurrency" in doc:
        errors.append(
            f"{path}: reusable workflow must not set top-level concurrency "
            "(put a github.ref-keyed group in the caller stub instead; "
            "upstream's github.head_ref group cancelled pushes across branches)"
        )

    if "github.repository_owner" in text:
        errors.append(
            f"{path}: must not restrict github.repository_owner "
            "(IndrajeetPatil/workflows does; this repo is shared)"
        )

    inputs = workflow_call_inputs(doc)
    if "cache" in inputs:
        errors.append(
            f"{path}: cache must not be a workflow_call input; it is "
            "hard-coded false on the hard job so a restored pak cache "
            "cannot silently contain Suggests"
        )
    for name in REQUIRED_INPUTS:
        if name not in inputs:
            errors.append(f"{path}: missing workflow_call input `{name}`")

    error_on = inputs.get("error-on") or {}
    default = error_on.get("default")
    if default != '"note"':
        errors.append(
            f"{path}: error-on default is {default!r}, expected '\"note\"' "
            "to match rpt"
        )

    jobs = doc.get("jobs") or {}
    full = jobs.get("R-CMD-check")
    hard = jobs.get("R-CMD-check-hard")
    if not isinstance(full, dict):
        errors.append(f"{path}: missing job R-CMD-check")
        return errors
    if not isinstance(hard, dict):
        errors.append(f"{path}: missing job R-CMD-check-hard")
        return errors

    full_if = str(full.get("if") or "")
    if "inputs.hard" not in full_if or "!" not in full_if:
        errors.append(
            f"{path}: R-CMD-check job if: must skip when inputs.hard is true "
            f"(got {full_if!r})"
        )

    hard_if = str(hard.get("if") or "")
    if "inputs.hard" not in hard_if or "pull_request" not in hard_if:
        errors.append(
            f"{path}: R-CMD-check-hard job if: must require inputs.hard and "
            f"github.event_name == 'pull_request' (got {hard_if!r})"
        )

    if hard.get("container") not in (None, "", False):
        errors.append(
            f"{path}: R-CMD-check-hard must not set container "
            "(rocker/verse would preinstall Suggests)"
        )

    hard_env = hard.get("env") or {}
    force = hard_env.get("_R_CHECK_FORCE_SUGGESTS_")
    if force not in (False, "false"):
        errors.append(
            f"{path}: hard job must hard-code _R_CHECK_FORCE_SUGGESTS_ false "
            f"(got {force!r})"
        )

    deps = find_step(hard, "setup-r-dependencies")
    if deps is None:
        errors.append(f"{path}: hard job has no setup-r-dependencies step")
        return errors
    with_block = deps.get("with") or {}
    if with_block.get("cache") is not False:
        errors.append(
            f"{path}: hard job setup-r-dependencies must set cache: false "
            f"(got {with_block.get('cache')!r}); a restored cache can contain "
            "Suggests and silently defeat the job"
        )
    dependencies = str(with_block.get("dependencies") or "")
    if "hard" not in dependencies:
        errors.append(
            f"{path}: hard job must pass dependencies: '\"hard\"' "
            f"(got {dependencies!r})"
        )
    extras = str(with_block.get("extra-packages") or "")
    for pkg in HARD_EXTRAS:
        if f"any::{pkg}" not in extras:
            errors.append(
                f"{path}: hard job extra-packages must include any::{pkg}"
            )

    full_deps = find_step(full, "setup-r-dependencies")
    if full_deps is not None:
        full_with = full_deps.get("with") or {}
        if full_with.get("cache") is False:
            errors.append(
                f"{path}: full matrix job must not set cache: false "
                "(that pin is specific to the hard job)"
            )

    if "timeout-minutes" not in full or "timeout-minutes" not in hard:
        errors.append(f"{path}: both jobs must set timeout-minutes")

    hard_check = find_step(hard, "check-r-package")
    if hard_check is None:
        errors.append(f"{path}: hard job has no check-r-package step")
    else:
        hard_check_with = hard_check.get("with") or {}
        if "error-on" in hard_check_with:
            errors.append(
                f"{path}: hard job must omit error-on so r-lib's "
                "default '\"warning\"' applies; forwarding "
                "inputs.error-on (default note) fails the job on "
                "missing-Suggests NOTEs"
            )

    full_check = find_step(full, "check-r-package")
    if full_check is None:
        errors.append(f"{path}: full matrix job has no check-r-package step")
    else:
        full_error_on = str((full_check.get("with") or {}).get("error-on") or "")
        if "inputs.error-on" not in full_error_on:
            errors.append(
                f"{path}: full matrix check-r-package must forward "
                "inputs.error-on (got "
                f"{full_error_on!r}); dropping it silently applies "
                "r-lib's '\"warning\"' default"
            )

    for job_name, job in (("R-CMD-check", full), ("R-CMD-check-hard", hard)):
        incoming = str((job.get("env") or {}).get("_R_CHECK_CRAN_INCOMING_") or "")
        if "inputs.cran-incoming-remote" not in incoming:
            errors.append(
                f"{path}: {job_name} must set _R_CHECK_CRAN_INCOMING_ from "
                "inputs.cran-incoming-remote; r-lib/check-r-package sets "
                "it false when unset, so REMOTE-only cannot enable "
                "incoming checks"
            )

    quarto = find_step(full, "quarto-actions/setup")
    if quarto is None:
        errors.append(f"{path}: full matrix job has no Quarto setup step")
    else:
        qif = str(quarto.get("if") or "")
        if "ubuntu-latest" not in qif or (
            "contains(inputs.linux-container, 'verse')" not in qif
        ):
            errors.append(
                f"{path}: full job Quarto if: must skip ubuntu-latest "
                "only when linux-container contains 'verse' "
                f"(got {qif!r})"
            )

    full_force = str((full.get("env") or {}).get("_R_CHECK_FORCE_SUGGESTS_") or "")
    if "inputs.force-suggests" not in full_force:
        errors.append(
            f"{path}: full matrix job must set _R_CHECK_FORCE_SUGGESTS_ from "
            "inputs.force-suggests; r-lib/check-r-package sets it false when "
            "unset, so omitting the env makes force-suggests: true a no-op"
        )

    return errors


def check_example(path: pathlib.Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    doc = load_yaml(path)
    if not isinstance(doc, dict):
        return [f"{path}: not a YAML mapping"]

    if "@v2" not in text:
        errors.append(f"{path}: caller stub must pin @v2")

    jobs = doc.get("jobs") or {}
    if "R-CMD-check" not in jobs:
        errors.append(f"{path}: missing caller job R-CMD-check")
    if "R-CMD-check-hard" not in jobs:
        errors.append(f"{path}: missing caller job R-CMD-check-hard")
    else:
        hard = jobs["R-CMD-check-hard"]
        with_block = hard.get("with") or {}
        if with_block.get("hard") is not True:
            errors.append(
                f"{path}: R-CMD-check-hard must pass hard: true "
                f"(got {with_block.get('hard')!r})"
            )

    concurrency = doc.get("concurrency") or {}
    group = str(concurrency.get("group") or "")
    if not group:
        errors.append(
            f"{path}: caller stub should set concurrency.group keyed on "
            "github.ref (not github.head_ref alone)"
        )
    elif "github.head_ref" in group and "github.ref" not in group:
        errors.append(
            f"{path}: concurrency.group uses github.head_ref with no "
            "github.ref fallback; that is the IndrajeetPatil/workflows bug "
            f"(got {group!r})"
        )
    elif "github.ref" not in group:
        errors.append(
            f"{path}: concurrency.group must include github.ref "
            f"(got {group!r})"
        )

    return errors


def run_checks(workflow: pathlib.Path, example: pathlib.Path) -> int:
    errors = check_workflow(workflow) + check_example(example)
    if errors:
        for err in errors:
            print(f"::error::{err}", file=sys.stderr)
        print(
            f"::error::{len(errors)} r-cmd-check workflow contract(s) failed",
            file=sys.stderr,
        )
        return 1
    print(f"OK   {workflow.relative_to(REPO_ROOT)}")
    print(f"OK   {example.relative_to(REPO_ROOT)}")
    return 0


def expect(label: str, code: int, should_pass: bool, stderr: str, needle: str | None = None) -> int:
    passed = code == 0
    if passed != should_pass:
        print(
            f"::error::{label}: expected {'pass' if should_pass else 'failure'}, "
            f"got exit {code}\n{stderr}",
            file=sys.stderr,
        )
        return 1
    if needle and needle not in stderr:
        print(
            f"::error::{label}: expected output to mention {needle!r}\n{stderr}",
            file=sys.stderr,
        )
        return 1
    print(f"OK   {label}")
    return 0


def run_self_test(workflow: pathlib.Path, example: pathlib.Path) -> int:
    print("Running run-r-cmd-check-workflow-tests offline unit tests...")
    failures = 0

    # 1. The real files pass.
    failures += expect(
        "real workflow and example pass",
        run_checks(workflow, example),
        True,
        "",
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        wf = tmp_path / "r-cmd-check.yml"
        ex = tmp_path / "example.yml"
        shutil.copy(workflow, wf)
        shutil.copy(example, ex)

        # 2. cache: false -> true on the hard job must fail.
        mutated = wf.read_text(encoding="utf-8")
        # Mutate the YAML key, not the header comment that also says
        # "cache: false". A first-occurrence replace of that phrase
        # would rewrite the comment, leave the job untouched, and
        # pass while the guard was live.
        yaml_key = "          cache: false"
        if yaml_key not in mutated:
            print(
                "::error::self-test: fixture workflow has no indented "
                "`cache: false` YAML key to mutate",
                file=sys.stderr,
            )
            return 1
        wf.write_text(mutated.replace(yaml_key, "          cache: true", 1))
        mutated_hard = find_step(
            (load_yaml(wf).get("jobs") or {}).get("R-CMD-check-hard") or {},
            "setup-r-dependencies",
        )
        if (mutated_hard or {}).get("with", {}).get("cache") is not True:
            print(
                "::error::self-test: cache mutation did not flip the YAML key "
                "(it likely rewrote a comment instead)",
                file=sys.stderr,
            )
            return 1
        errors = check_workflow(wf)
        failures += expect(
            "cache: true on the hard job fails",
            1 if errors else 0,
            False,
            "\n".join(errors),
            "cache: false",
        )
        wf.write_text(mutated)

        # 3. Dropping the pull_request gate must fail.
        no_pr = re.sub(
            r"github\.event_name == 'pull_request'",
            "true",
            mutated,
            count=1,
        )
        wf.write_text(no_pr)
        errors = check_workflow(wf)
        failures += expect(
            "hard job without pull_request gate fails",
            1 if errors else 0,
            False,
            "\n".join(errors),
            "pull_request",
        )
        wf.write_text(mutated)

        # 4. Example concurrency keyed on head_ref alone must fail.
        ex_text = ex.read_text(encoding="utf-8")
        bad_group = ex_text.replace(
            "r-cmd-check-${{ github.ref }}",
            "${{ github.workflow }}-${{ github.head_ref }}",
        )
        if bad_group == ex_text:
            print(
                "::error::self-test: example has no github.ref concurrency group to mutate",
                file=sys.stderr,
            )
            return 1
        ex.write_text(bad_group)
        errors = check_example(ex)
        failures += expect(
            "head_ref-only concurrency group fails",
            1 if errors else 0,
            False,
            "\n".join(errors),
            "head_ref",
        )

        # 5. Forwarding inputs.error-on on the hard job must fail.
        omit_marker = (
            "          # Omit error-on: r-lib's default '\"warning\"' keeps missing-Suggests\n"
            "          # NOTEs from failing the job that exists to tolerate them.\n"
            "          build_args: ${{ inputs.build-args }}"
        )
        if omit_marker not in mutated:
            print(
                "::error::self-test: fixture workflow has no hard-job "
                "error-on omission comment to mutate",
                file=sys.stderr,
            )
            return 1
        wf.write_text(
            mutated.replace(
                omit_marker,
                "          error-on: ${{ inputs.error-on }}\n"
                "          build_args: ${{ inputs.build-args }}",
                1,
            )
        )
        errors = check_workflow(wf)
        failures += expect(
            "hard job forwarding error-on fails",
            1 if errors else 0,
            False,
            "\n".join(errors),
            "error-on",
        )
        wf.write_text(mutated)

        # 6. Dropping error-on from the full matrix Check step must fail.
        full_error_on = (
            "          error-on: ${{ inputs.error-on }}\n"
            "          build_args: ${{ inputs.build-args }}"
        )
        if full_error_on not in mutated:
            print(
                "::error::self-test: fixture workflow has no full-matrix "
                "error-on forwarding to mutate",
                file=sys.stderr,
            )
            return 1
        wf.write_text(
            mutated.replace(
                full_error_on,
                "          build_args: ${{ inputs.build-args }}",
                1,
            )
        )
        errors = check_workflow(wf)
        failures += expect(
            "full matrix omitting error-on fails",
            1 if errors else 0,
            False,
            "\n".join(errors),
            "inputs.error-on",
        )
        wf.write_text(mutated)

        # 7. Dropping _R_CHECK_CRAN_INCOMING_ on the full job must fail.
        incoming_line = (
            "      _R_CHECK_CRAN_INCOMING_: ${{ inputs.cran-incoming-remote }}\n"
        )
        if incoming_line not in mutated:
            print(
                "::error::self-test: fixture workflow has no "
                "_R_CHECK_CRAN_INCOMING_ env line to mutate",
                file=sys.stderr,
            )
            return 1
        wf.write_text(mutated.replace(incoming_line, "", 1))
        errors = check_workflow(wf)
        failures += expect(
            "full job without _R_CHECK_CRAN_INCOMING_ fails",
            1 if errors else 0,
            False,
            "\n".join(errors),
            "_R_CHECK_CRAN_INCOMING_",
        )
        wf.write_text(mutated)

        # 8. Quarto skip on every ubuntu cell (rpt's os != ubuntu-latest)
        # must fail; last round's verse-only skip is load-bearing.
        verse_quarto = (
            "        if: inputs.install-quarto && !(matrix.config.os == "
            "'ubuntu-latest' && contains(inputs.linux-container, 'verse'))"
        )
        rpt_quarto = (
            "        if: inputs.install-quarto && "
            "matrix.config.os != 'ubuntu-latest'"
        )
        if verse_quarto not in mutated:
            print(
                "::error::self-test: fixture workflow has no verse-gated "
                "Quarto if: to mutate",
                file=sys.stderr,
            )
            return 1
        wf.write_text(mutated.replace(verse_quarto, rpt_quarto, 1))
        errors = check_workflow(wf)
        failures += expect(
            "Quarto skip on all ubuntu cells fails",
            1 if errors else 0,
            False,
            "\n".join(errors),
            "verse",
        )
        wf.write_text(mutated)

        # 9. Quarto skip on verse images on every OS (verse without
        # ubuntu-latest) must fail; a 'verse' substring is not enough.
        verse_any_os = (
            "        if: inputs.install-quarto && "
            "!contains(inputs.linux-container, 'verse')"
        )
        wf.write_text(mutated.replace(verse_quarto, verse_any_os, 1))
        errors = check_workflow(wf)
        failures += expect(
            "Quarto skip on verse images on every OS fails",
            1 if errors else 0,
            False,
            "\n".join(errors),
            "ubuntu-latest",
        )
        wf.write_text(mutated)

        # 10. Dropping _R_CHECK_FORCE_SUGGESTS_ from the full job must fail.
        force_line = (
            "      _R_CHECK_FORCE_SUGGESTS_: ${{ inputs.force-suggests }}\n"
        )
        if force_line not in mutated:
            print(
                "::error::self-test: fixture workflow has no full-job "
                "_R_CHECK_FORCE_SUGGESTS_ env line to mutate",
                file=sys.stderr,
            )
            return 1
        wf.write_text(mutated.replace(force_line, "", 1))
        errors = check_workflow(wf)
        failures += expect(
            "full job without _R_CHECK_FORCE_SUGGESTS_ fails",
            1 if errors else 0,
            False,
            "\n".join(errors),
            "inputs.force-suggests",
        )

    if failures:
        print(
            f"::error::{failures} r-cmd-check workflow self-test case(s) failed",
            file=sys.stderr,
        )
        return 1
    print("All r-cmd-check workflow self-test cases passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", type=pathlib.Path, default=DEFAULT_WORKFLOW)
    parser.add_argument("--example", type=pathlib.Path, default=DEFAULT_EXAMPLE)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test(args.workflow, args.example)

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from workflow_discovery import is_workflows_restored

    if is_workflows_restored(args.workflow.parent):
        print(
            "::notice::Skipping r-cmd-check workflow tests: .github/workflows/ "
            "was restored from default branch (gha#598, gha#765)."
        )
        return 0

    return run_checks(args.workflow, args.example)


if __name__ == "__main__":
    sys.exit(main())
