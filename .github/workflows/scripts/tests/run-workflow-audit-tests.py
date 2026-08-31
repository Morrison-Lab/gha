#!/usr/bin/env python3
"""Offline tests for the two workflow audits `_selftest.yml` runs (gha#716).

These cover the AUDITS, not just the discovery underneath them, and that
distinction is the point: this repo's real tree carries 63 ``.yml`` workflows
and zero ``.yaml`` ones, so a consumer reverted to a ``*.yml``-only glob would
leave every other check green.  Each audit therefore gets a fixture whose
violation lives in a ``.yaml`` file, which no yml-only discovery can see.

The other cases to keep if this is ever trimmed are the negative ones, because
each pins a decision that is silent when reversed: an unparsable file is an
error rather than a clean file, an empty directory is an error rather than an
empty list, ``submodules-token:`` is not ``token:``, and a nested
``scripts/foo.yml`` is not a workflow.

Usage::

    python3 run-workflow-audit-tests.py
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import audit_workflow_action_pins as pins  # noqa: E402
import audit_workflow_token_usage as token  # noqa: E402
from workflow_discovery import discover_workflows, is_workflows_restored  # noqa: E402

# Assembled rather than typed, so this fixture text cannot itself be mistaken
# for a real expression by anything scanning this repo.
EXPR = "$" + "{{"

PINNED = "actions/checkout@1111111111111111111111111111111111111111"

failures = 0
cases = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures, cases
    cases += 1
    if condition:
        print(f"OK   {label}")
    else:
        print(f"::error::{label}{': ' + detail if detail else ''}", file=sys.stderr)
        failures += 1


def write(root: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def audit(module, directory: pathlib.Path) -> int:
    """Run one audit, swallowing its own output.

    An expected failure still prints `::error::`, and GitHub renders every one
    of those as an annotation --- so an unmuted suite decorates a passing job
    with a dozen errors it deliberately provoked, which is worse than useless
    to whoever reads the run.
    """
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        return module.main(["--workflows-dir", str(directory)])


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        # ------------------------------------------------------ discovery
        disc = root / "discovery"
        write(disc, "a.yml", "name: a\n")
        write(disc, "b.yaml", "name: b\n")
        write(disc, "c.txt", "not a workflow\n")
        write(disc, "scripts/nested.yml", "name: nested\n")
        check(
            "discovery: both extensions, no .txt, no nested file",
            [p.name for p in discover_workflows(disc)] == ["a.yml", "b.yaml"],
            f"got {[p.name for p in discover_workflows(disc)]}",
        )

        # ----------------------------------------------------- token audit
        clean = root / "token-clean"
        write(
            clean,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            "      - name: checkout\n"
            f"        uses: {PINNED}\n"
            "        with:\n"
            f"          submodules-token: {EXPR} secrets.SUBMODULES_TOKEN }}}}\n",
        )
        check(
            "token: submodules-token: is not flagged",
            audit(token, clean) == 0,
        )

        for ext in ("yml", "yaml"):
            bad = root / f"token-bad-{ext}"
            write(
                bad,
                f"a.{ext}",
                "jobs:\n"
                "  run:\n"
                "    steps:\n"
                "      - name: checkout\n"
                f"        uses: {PINNED}\n"
                "        with:\n"
                f"          token: {EXPR} secrets.SUBMODULES_TOKEN }}}}\n",
            )
            check(
                f"token: a .{ext} violation fails",
                audit(token, bad) == 1,
            )

        # ------------------------------------------------------ pins audit
        pins_clean = root / "pins-clean"
        write(
            pins_clean,
            "a.yml",
            "jobs:\n"
            "  call:\n"
            "    uses: Morrison-Lab/gha/.github/workflows/spellcheck.yml@v2\n"
            "  run:\n"
            "    steps:\n"
            f"      - uses: {PINNED}\n"
            "      - name: local\n"
            "        uses: ./.github/actions/local-thing\n",
        )
        check(
            "pins: pinned, local and self refs pass",
            audit(pins, pins_clean) == 0,
        )

        # gha#720: BOTH spellings must be caught. The list-item form is the one
        # the line-anchored regex this audit replaced could never see, so it is
        # first here rather than an afterthought.
        for label, step_block in (
            ("list-item form", f"      - uses: actions/checkout@v4\n"),
            (
                "continuation form",
                "      - name: checkout\n        uses: actions/checkout@v4\n",
            ),
        ):
            for ext in ("yml", "yaml"):
                bad = root / f"pins-{label.replace(' ', '-')}-{ext}"
                write(
                    bad,
                    f"a.{ext}",
                    "jobs:\n  run:\n    steps:\n" + step_block,
                )
                check(
                    f"pins: an unpinned {label} in a .{ext} file fails",
                    audit(pins, bad) == 1,
                )

        # A `docker://` action pinned by image digest is as immutable as a
        # commit-pinned repository action, so reporting it unpinned would be a
        # false positive on the safe spelling.
        docker = root / "pins-docker"
        write(
            docker,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            "      - uses: docker://alpine@sha256:" + ("a" * 64) + "\n",
        )
        check(
            "pins: a docker:// action pinned by image digest passes",
            audit(pins, docker) == 0,
        )

        docker_tag = root / "pins-docker-tag"
        write(
            docker_tag,
            "a.yml",
            "jobs:\n  run:\n    steps:\n      - uses: docker://alpine:3.20\n",
        )
        check(
            "pins: a docker:// action pinned only by tag fails",
            audit(pins, docker_tag) == 1,
        )

        job_uses = root / "pins-job-uses"
        write(
            job_uses,
            "a.yml",
            "jobs:\n  call:\n    uses: someone/else/.github/workflows/x.yml@main\n",
        )
        check(
            "pins: an unpinned reusable-workflow call fails",
            audit(pins, job_uses) == 1,
        )

        # A `uses:` inside a run: block is text, not a reference. This is what
        # made widening the old regex the wrong fix (gha#720).
        heredoc = root / "pins-heredoc"
        write(
            heredoc,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            "      - run: |\n"
            "          cat > bad.yml <<EOF\n"
            "          steps:\n"
            "            - uses: actions/checkout@v4\n"
            "          EOF\n",
        )
        check(
            "pins: a uses: written inside a run: block is not a reference",
            audit(pins, heredoc) == 0,
        )

        # A prefix is not a repository boundary: gha-evil is somebody else's
        # repo, and the exemption exists to say "this code is ours".
        lookalike = root / "pins-lookalike-owner"
        write(
            lookalike,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            "      - uses: Morrison-Lab/gha-evil/action@main\n",
        )
        check(
            "pins: a repo merely PREFIXED by Morrison-Lab/gha is not exempt",
            audit(pins, lookalike) == 1,
        )

        # The identifier, not a substring of one. A false positive here blocks
        # a valid workflow, which is the expensive direction for this check.
        other_secret = root / "token-lookalike-secret"
        write(
            other_secret,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            "      - name: checkout\n"
            f"        uses: {PINNED}\n"
            "        with:\n"
            f"          token: {EXPR} secrets.NOT_SUBMODULES_TOKEN }}}}\n",
        )
        check(
            "token: a secret merely CONTAINING the name is not flagged",
            audit(token, other_secret) == 0,
        )

        # The audit is deliberately not scoped to actions/checkout: any action
        # handed this secret through `token:` is being trusted to authenticate
        # against the caller's own repo, which is exactly what it cannot do.
        # This case pins that breadth, so narrowing it later is a decision
        # rather than a silent regression.
        non_checkout = root / "token-non-checkout"
        write(
            non_checkout,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            "      - uses: example/tool@1111111111111111111111111111111111111111\n"
            "        with:\n"
            f"          token: {EXPR} secrets.SUBMODULES_TOKEN }}}}\n",
        )
        check(
            "token: a non-checkout action is flagged too (audit is not scoped)",
            audit(token, non_checkout) == 1,
        )

        # Job level: a reusable-workflow caller passes values through `with:`
        # and `secrets:`, which no walk over `steps` reaches. The regex this
        # audit replaced covered these incidentally, so missing them would be a
        # coverage regression rather than a refactor.
        for block in ("with", "secrets"):
            job_level = root / f"token-job-{block}"
            write(
                job_level,
                "a.yml",
                "jobs:\n"
                "  call:\n"
                "    uses: other/repo/.github/workflows/x.yml@"
                + ("b" * 40)
                + "\n"
                f"    {block}:\n"
                f"      token: {EXPR} secrets.SUBMODULES_TOKEN }}}}\n",
            )
            check(
                f"token: a job-level '{block}.token' is flagged",
                audit(token, job_level) == 1,
            )

        inherit = root / "token-secrets-inherit"
        write(
            inherit,
            "a.yml",
            "jobs:\n"
            "  call:\n"
            "    uses: other/repo/.github/workflows/x.yml@" + ("b" * 40) + "\n"
            "    secrets: inherit\n",
        )
        check(
            "token: 'secrets: inherit' is the one legitimate scalar",
            audit(token, inherit) == 0,
        )

        # GitHub resolves an action's inputs case-insensitively, so a
        # differently-cased key is the same input and must not slip through.
        for spelling in ("Token", "TOKEN"):
            cased = root / f"token-cased-{spelling}"
            write(
                cased,
                "a.yml",
                "jobs:\n"
                "  run:\n"
                "    steps:\n"
                f"      - uses: actions/checkout@{'a' * 40}\n"
                "        with:\n"
                f"          {spelling}: {EXPR} secrets.SUBMODULES_TOKEN }}}}\n",
            )
            check(
                f"token: a step input spelled '{spelling}' is still flagged",
                audit(token, cased) == 1,
            )

        cased_job = root / "token-cased-job"
        write(
            cased_job,
            "a.yml",
            "jobs:\n"
            "  call:\n"
            "    uses: other/repo/.github/workflows/x.yml@" + ("b" * 40) + "\n"
            "    secrets:\n"
            f"      Token: {EXPR} secrets.SUBMODULES_TOKEN }}}}\n",
        )
        check(
            "token: a job-level input spelled 'Token' is still flagged",
            audit(token, cased_job) == 1,
        )

        # A differently-cased `submodules-token` is still a DIFFERENT key, so
        # case-insensitivity must not widen the match to it.
        cased_ok = root / "token-cased-submodules"
        write(
            cased_ok,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            f"      - uses: actions/checkout@{'a' * 40}\n"
            "        with:\n"
            f"          Submodules-Token: {EXPR} secrets.SUBMODULES_TOKEN }}}}\n",
        )
        check(
            "token: 'Submodules-Token' is still a different key",
            audit(token, cased_ok) == 0,
        )

        # ... and it is the ONLY one. A scalar `with:`, or a `secrets:` naming
        # anything else, is a block the audit never examined.
        bad_scalars = {
            "with-scalar": "    with: bad\n",
            "secrets-scalar": "    secrets: not-inherit\n",
        }
        for shape, tail in bad_scalars.items():
            bad = root / f"token-{shape}"
            write(
                bad,
                "a.yml",
                "jobs:\n"
                "  call:\n"
                "    uses: other/repo/.github/workflows/x.yml@" + ("b" * 40) + "\n"
                + tail,
            )
            check(
                f"token: a job-level '{shape}' is an error, not clean",
                audit(token, bad) == 2,
            )

        container_token = root / "token-container-value"
        write(
            container_token,
            "a.yml",
            "jobs:\n"
            "  run:\n"
            "    steps:\n"
            f"      - uses: actions/checkout@{'a' * 40}\n"
            "        with:\n"
            "          token:\n"
            "            - SUBMODULES_TOKEN\n",
        )
        check(
            "token: a list-valued 'token:' is an error, not clean",
            audit(token, container_token) == 2,
        )

        # The two pin forms are not interchangeable: neither crossed spelling
        # resolves to anything, so neither may read as pinned.
        crossed_forms = (
            (
                "a repository action pinned by an image digest",
                "actions/checkout@sha256:" + "a" * 64,
            ),
            ("a docker:// action pinned by a git commit", "docker://alpine@" + "a" * 40),
            (
                "a reusable workflow pinned by an image digest",
                "other/repo/.github/workflows/x.yml@sha256:" + "a" * 64,
            ),
        )
        for n, (label, ref) in enumerate(crossed_forms):
            crossed = root / f"pins-crossed-{n}"
            write(
                crossed,
                "a.yml",
                "jobs:\n  run:\n    steps:\n      - uses: " + ref + "\n",
            )
            check(f"pins: {label} fails", audit(pins, crossed) == 1)

        # ------------------------------------- refusals, not silent passes
        uses_not_string = root / "pins-uses-not-string"
        write(
            uses_not_string,
            "a.yml",
            "jobs:\n  run:\n    steps:\n      - uses:\n          - a\n          - b\n",
        )
        check(
            "pins: a step whose 'uses' is not a string is an error, not clean",
            audit(pins, uses_not_string) == 2,
        )

        # A structurally malformed workflow is one the audit walked NOTHING in,
        # which is not the same as one it found nothing in. Skipping these was
        # the parsed-walk version of reading grep's exit 2 as exit 1.
        malformed = {
            "empty-file": "",
            "no-jobs": "name: only\n",
            "jobs-not-mapping": "jobs: not-a-mapping\n",
            "job-not-mapping": "jobs:\n  run: not-a-mapping\n",
            "steps-not-list": "jobs:\n  run:\n    steps: not-a-list\n",
            "step-not-mapping": "jobs:\n  run:\n    steps:\n      - just-a-string\n",
        }
        for name, module in (("token", token), ("pins", pins)):
            for shape, body in malformed.items():
                bad = root / f"{name}-{shape}"
                write(bad, "a.yml", body)
                check(
                    f"{name}: '{shape}' is an error, not a clean workflow",
                    audit(module, bad) == 2,
                )

        for name, module in (("token", token), ("pins", pins)):
            unparsable = root / f"{name}-unparsable"
            write(unparsable, "a.yml", "jobs:\n  run:\n   - bad\n  : : :\n")
            check(
                f"{name}: an unparsable workflow is an error, not a clean file",
                audit(module, unparsable) == 2,
            )

            empty = root / f"{name}-empty"
            empty.mkdir(parents=True, exist_ok=True)
            check(
                f"{name}: an empty workflows directory fails closed",
                audit(module, empty) == 2,
            )

            check(
                f"{name}: a missing workflows directory fails closed",
                audit(module, root / f"{name}-absent") == 2,
            )

        # Restored workflows directory skips audits cleanly (gha#598, gha#765)
        restored = root / "restored-tree"
        write(
            restored,
            "bad.yml",
            f"name: bad\njobs:\n  run:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: unpinned/action@v1\n        with:\n          token: {EXPR} secrets.SUBMODULES_TOKEN }}\n",
        )
        write(restored, ".restored-from-default-branch", "")
        check(
            "is_workflows_restored detects .restored-from-default-branch marker",
            is_workflows_restored(restored),
        )
        check(
            "discover_workflows ignores hidden files",
            [p.name for p in discover_workflows(restored)] == ["bad.yml"],
        )
        check(
            "pins: skips restored workflows directory with exit 0",
            audit(pins, restored) == 0,
        )
        check(
            "token: skips restored workflows directory with exit 0",
            audit(token, restored) == 0,
        )

    if failures:
        print(f"::error::{failures} of {cases} workflow-audit case(s) failed", file=sys.stderr)
        return 1
    print(f"All {cases} workflow-audit tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
