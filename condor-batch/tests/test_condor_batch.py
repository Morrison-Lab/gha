"""Offline test of condor-batch.sh.

Stub ssh runs the remote script locally; stub rsync, condor_submit and
condor_wait record their calls, so the real remote logic is exercised.
"""

import os
import signal
import stat
from pathlib import Path
import subprocess
import time

SCRIPT = Path(__file__).resolve().parent.parent / "condor-batch.sh"

SSH_STUB = """\
echo "ssh $*" >> "$STUB_LOG"
[ -z "${STUB_SSH_RC:-}" ] || exit "$STUB_SSH_RC"
while [ "$1" != bash ]; do shift; done
# Real ssh joins its arguments into one command string that the remote shell
# splits again, so an empty argument vanishes; eval reproduces that.
args="$*"
eval "exec $args"
"""

RSYNC_STUB = """\
echo "rsync $*" >> "$STUB_LOG"
[ -z "${STUB_RSYNC_RC:-}" ] || exit "$STUB_RSYNC_RC"
dest="${@: -1}"; dest="${dest#*:}"
src="${@: -2:1}"
if [ -f "$src" ]; then mkdir -p "$(dirname "$dest")"; cp "$src" "$dest"
else mkdir -p "$dest"; fi
"""

SUBMIT_STUB = """\
echo "condor_submit $*" >> "$STUB_LOG"
echo "1 job(s) submitted to cluster 77."
cp .condor.sub "$STUB_LOG.sub"
cp .condor-run.sh "$STUB_LOG.run"
tar -tzf checkout.tar.gz > "$STUB_LOG.tar"
"""

WAIT_STUB = """\
echo "condor_wait $*" >> "$STUB_LOG"
[ -z "${STUB_WAIT_SLEEP:-}" ] || sleep "$STUB_WAIT_SLEEP"
if [ -n "${STUB_RV:-}" ]; then
  echo "004 (1.0) Job terminated. (1) Normal termination (return value $STUB_RV)" >> condor.log
fi
exit "${STUB_WAIT_RC:-0}"
"""


RM_STUB = 'echo "condor_rm $*" >> "$STUB_LOG"\n'


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
    _stub(bin_dir / "condor_rm", RM_STUB)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    (checkout / ".git" / "pack").write_text("x")
    (checkout / "node_modules").mkdir()
    (checkout / "node_modules" / "m.js").write_text("x")
    (checkout / "keep.txt").write_text("x")
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
    assert _count(calls, "condor_submit") == 0


def test_failed_copy_sweeps_only_old_run_directories_then_retries(tmp_path):
    ci = tmp_path / "ci"
    for name in ("1", "99", "image"):
        (ci / name).mkdir(parents=True)
    old = 1_000_000_000
    for name in ("1", "image"):
        os.utime(ci / name, (old, old))
    proc, calls = _run(tmp_path, ["a", "b"], STUB_RSYNC_RC="23")
    assert proc.returncode == 70
    assert _count(calls, "rsync ") == 2
    assert not (ci / "1").exists()
    assert (ci / "99").exists()
    assert (ci / "image").exists()


def _tar_listing(tmp_path: Path) -> str:
    return (tmp_path / "calls.log.tar").read_text()


def test_exclude_patterns_keep_paths_out_of_the_tarball(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="0", RSYNC_EXCLUDE=".git  node_modules")
    assert proc.returncode == 0, proc.stderr
    listing = _tar_listing(tmp_path)
    assert "keep.txt" in listing
    assert ".git" not in listing
    assert "node_modules" not in listing


def test_no_exclude_by_default(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    assert ".git/pack" in _tar_listing(tmp_path)


def test_only_two_files_are_copied_to_the_home(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b"], STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    copies = [line for line in calls if line.startswith("rsync ")]
    assert len(copies) == 2
    assert "checkout.tar.gz" in copies[0]
    assert ".condor-steps" in copies[1]


def test_job_uses_file_transfer_and_runs_in_scratch(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    sub = (tmp_path / "calls.log.sub").read_text()
    assert "should_transfer_files = YES" in sub
    assert "transfer_input_files = " in sub and "checkout.tar.gz" in sub
    assert "request_disk = 20GB" in sub
    run = (tmp_path / "calls.log.run").read_text()
    assert 'scratch=$PWD' in run
    assert "tar -xzf checkout.tar.gz" in run
    assert 'cd "$1"' not in run


def test_held_or_aborted_job_exits_70(tmp_path):
    # No "return value" line in condor.log, and condor_wait itself failed.
    proc, _ = _run(tmp_path, ["a", "b"], STUB_WAIT_RC="1")
    assert proc.returncode == 70
    assert "did not end normally" in proc.stderr


def test_ssh_key_with_whitespace_is_refused(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b"], CONDOR_SSH_KEY="/tmp/my key")
    assert proc.returncode == 64
    assert calls == []


def _arguments(tmp_path: Path) -> str:
    sub = (tmp_path / "calls.log.sub").read_text().splitlines()
    return next(line for line in sub if line.startswith("arguments = "))


def test_no_image_submits_only_the_run_dir(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    assert _arguments(tmp_path).strip() == "arguments ="


def test_image_is_passed_to_the_job_and_used_by_the_run_script(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="0", CONDOR_IMAGE="/c/lds-ci.sif")
    assert proc.returncode == 0, proc.stderr
    assert _arguments(tmp_path).endswith("= /c/lds-ci.sif")
    run = (tmp_path / "calls.log.run").read_text()
    assert "apptainer exec --containall" in run
    assert "--pwd /work --home /work/.home" in run


def test_image_steps_execute_through_apptainer(tmp_path):
    """Run the generated .condor-run.sh with a stub apptainer that execs its command."""
    _run(tmp_path, ["echo one > one.txt", "echo two > two.txt"], STUB_RV="0", CONDOR_IMAGE="/c/x.sif")
    work = tmp_path / "work"
    work.mkdir()
    (work / ".condor-steps").write_text("echo one > one.txt\necho two > two.txt\n")
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "seed.txt").write_text("x")
    subprocess.run(["tar", "-czf", str(work / "checkout.tar.gz"), "-C", str(seed), "."], check=True)
    bin_dir = tmp_path / "abin"
    bin_dir.mkdir()
    _stub(bin_dir / "apptainer", 'echo "$@" >> "$STUB_LOG.app"\nwhile [ "$1" != "/c/x.sif" ]; do shift; done\nshift\nexec "$@"\n')
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_LOG": str(tmp_path / "calls.log")}
    proc = subprocess.run(
        ["bash", str(tmp_path / "calls.log.run"), "/c/x.sif"],
        cwd=work, env=env, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    work = work / "work"
    assert (work / "one.txt").read_text() == "one\n"
    assert (work / "two.txt").read_text() == "two\n"
    assert (tmp_path / "calls.log.app").read_text().count("/c/x.sif") == 2


def test_run_dir_is_removed_after_a_normal_end_even_with_a_failing_step(tmp_path):
    for rv in ("0", "3"):
        case_dir = tmp_path / rv
        case_dir.mkdir()
        _run(case_dir, ["a", "b"], STUB_RV=rv)
        assert not (case_dir / "ci" / "42").exists(), rv


def test_run_dir_is_kept_when_the_job_did_not_end_normally(tmp_path):
    _run(tmp_path, ["a", "b"], STUB_WAIT_RC="1")
    assert (tmp_path / "ci" / "42" / ".condor.sub").exists()


def test_cancelled_run_removes_its_cluster_job_and_directory(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    for name, body in [("ssh", SSH_STUB), ("rsync", RSYNC_STUB), ("condor_submit", SUBMIT_STUB),
                       ("condor_wait", WAIT_STUB), ("condor_rm", RM_STUB)]:
        _stub(bin_dir / name, body)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    steps_file = tmp_path / "steps.txt"
    steps_file.write_text("a\nb\n")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUN_ID": "42",
        "CLUSTER_CI_ROOT": str(tmp_path / "ci"),
        "STUB_LOG": str(log),
        "STUB_WAIT_SLEEP": "30",
    }
    proc = subprocess.Popen(
        ["bash", str(SCRIPT), str(checkout), str(steps_file)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    cluster_id = tmp_path / "ci" / "42" / ".cluster-id"
    for _ in range(100):
        if cluster_id.exists() and cluster_id.read_text().strip():
            break
        time.sleep(0.1)
    os.killpg(proc.pid, signal.SIGTERM)
    proc.wait(timeout=20)
    calls = log.read_text().splitlines()
    assert "condor_rm 77" in calls
    assert not (tmp_path / "ci" / "42").exists()


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
