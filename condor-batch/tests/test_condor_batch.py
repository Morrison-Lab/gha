"""Offline test of condor-batch.sh.

Stub ssh runs the remote script locally; stub rsync, condor_submit and
condor_wait record their calls, so the real remote logic is exercised.
"""

import os
import stat
from pathlib import Path
import subprocess

SCRIPT = Path(__file__).resolve().parent.parent / "condor-batch.sh"

SSH_STUB = """\
echo "ssh $*" >> "$STUB_LOG"
[ -z "${STUB_SSH_RC:-}" ] || exit "$STUB_SSH_RC"
while [ "$1" != bash ]; do shift; done
exec "$@"
"""

RSYNC_STUB = """\
echo "rsync $*" >> "$STUB_LOG"
[ -z "${STUB_RSYNC_RC:-}" ] || exit "$STUB_RSYNC_RC"
dest="${@: -1}"; dest="${dest#*:}"
src="${@: -2:1}"
if [ -f "$src" ]; then mkdir -p "$(dirname "$dest")"; cp "$src" "$dest"
else mkdir -p "$dest"; fi
"""

SUBMIT_STUB = 'echo "condor_submit $*" >> "$STUB_LOG"\n'

WAIT_STUB = """\
echo "condor_wait $*" >> "$STUB_LOG"
if [ -n "${STUB_RV:-}" ]; then
  echo "004 (1.0) Job terminated. (1) Normal termination (return value $STUB_RV)" >> condor.log
fi
exit "${STUB_WAIT_RC:-0}"
"""


def _stub(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path: Path, steps: list[str], **extra_env: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    _stub(bin_dir / "ssh", SSH_STUB)
    _stub(bin_dir / "rsync", RSYNC_STUB)
    _stub(bin_dir / "condor_submit", SUBMIT_STUB)
    _stub(bin_dir / "condor_wait", WAIT_STUB)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    steps_file = tmp_path / "steps.txt"
    steps_file.write_text("\n".join(steps) + "\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUN_ID": "42",
        "CLUSTER_CI_ROOT": str(tmp_path / "ci"),
        "STUB_LOG": str(log),
        **extra_env,
    }
    proc = subprocess.run(
        ["bash", str(SCRIPT), str(checkout), str(steps_file)],
        env=env, capture_output=True, text=True, check=False,
    )
    calls = log.read_text().splitlines() if log.exists() else []
    return proc, calls


def _count(calls: list[str], prefix: str) -> int:
    return sum(line.startswith(prefix) for line in calls)


def test_five_steps_make_exactly_one_submission(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b", "c", "d", "e"], STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    assert _count(calls, "condor_submit") == 1
    assert _count(calls, "ssh ") == 1


def test_single_step_is_refused_without_contacting_the_cluster(tmp_path):
    proc, calls = _run(tmp_path, ["only"])
    assert proc.returncode == 71
    assert "refusing" in proc.stderr
    assert calls == []


def test_job_return_value_becomes_the_exit_code(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="5")
    assert proc.returncode == 5


def test_step_exit_codes_that_look_like_infrastructure_become_1(tmp_path):
    for rv in ("70", "71", "255"):
        case_dir = tmp_path / rv
        case_dir.mkdir()
        proc, _ = _run(case_dir, ["a", "b"], STUB_RV=rv)
        assert proc.returncode == 1, rv


def test_failed_ssh_exits_70(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_SSH_RC="255")
    assert proc.returncode == 70
    assert "ssh to the cluster head failed" in proc.stderr


def test_failed_copy_exits_70_without_submitting(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b"], STUB_RSYNC_RC="23")
    assert proc.returncode == 70
    assert _count(calls, "ssh ") == 0


def test_held_or_aborted_job_exits_70(tmp_path):
    # No "return value" line in condor.log, and condor_wait itself failed.
    proc, _ = _run(tmp_path, ["a", "b"], STUB_WAIT_RC="1")
    assert proc.returncode == 70
    assert "did not end normally" in proc.stderr


def test_ssh_key_with_whitespace_is_refused(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b"], CONDOR_SSH_KEY="/tmp/my key")
    assert proc.returncode == 64
    assert calls == []


ACTION = Path(__file__).resolve().parents[2] / ".github/actions/condor-batch/action.yml"


def _run_action(tmp_path: Path, script_rc: int):
    import yaml

    action = yaml.safe_load(ACTION.read_text())
    run = next(s["run"] for s in action["runs"]["steps"] if "run" in s)
    script = tmp_path / "stub.sh"
    script.write_text(f"exit {script_rc}\n")
    key = tmp_path / "key"
    key.write_text("k")
    marker = tmp_path / "marker"
    env = {
        **os.environ,
        "STEPS": f"touch {marker}\ntrue",
        "CONDOR_HEAD": "h",
        "WORKDIR": str(tmp_path),
        "SCRIPT": str(script),
        "CONDOR_SSH_KEY": str(key),
        "RUNNER_TEMP": str(tmp_path),
    }
    # GitHub runs `shell: bash` as this command line, with errexit on.
    cmd = ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", run]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    return proc.returncode, marker.exists()


def test_composite_reruns_locally_only_for_infrastructure_codes(tmp_path):
    for rc, reruns, final in [(70, True, 0), (71, True, 0), (0, False, 0), (2, False, 2), (3, False, 3), (255, False, 255)]:
        case_dir = tmp_path / str(rc)
        case_dir.mkdir()
        code, ran_locally = _run_action(case_dir, rc)
        assert (code, ran_locally) == (final, reruns), rc
