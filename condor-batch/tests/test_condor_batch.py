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
case " $* " in *" ${STUB_SSH_FAIL_HOST:-none-} "*) exit 255 ;; esac
host=
while [ $# -gt 0 ] && [ "$1" != bash ] && [ "$1" != true ]; do host="$1"; shift; done
export STUB_HOST="$host"
[ "${1:-}" != true ] || exit 0
# Real ssh joins its arguments into one command string that the remote shell
# splits again, so an empty argument vanishes; eval reproduces that.
args="$*"
eval "exec $args"
"""

RSYNC_STUB = """\
echo "rsync $*" >> "$STUB_LOG"
[ -z "${STUB_RSYNC_RC:-}" ] || exit "$STUB_RSYNC_RC"
dest="${@: -1}"; dest="${dest#*:}"
src="${@: -2:1}"; src="${src#*:}"
if [ -f "$src" ]; then mkdir -p "$(dirname "$dest")"; cp "$src" "$dest"
else mkdir -p "$dest"; fi
"""

SUBMIT_STUB = """\
echo "condor_submit $*" >> "$STUB_LOG"
echo "1 job(s) submitted to cluster 77."
cp .condor.sub "$STUB_LOG.sub"
cp .condor-run.sh "$STUB_LOG.run"
tar -tzf checkout.tar.gz > "$STUB_LOG.tar"
if [ -n "${STUB_QUEUE_LOG:-}" ]; then
  echo "000 (077.000.000) 2026-11-17 10:00:00 Job submitted from host: <1.2.3.4>" >> condor.log
  echo "001 (077.000.000) 2026-11-17 10:03:20 Job executing on host: <5.6.7.8>" >> condor.log
fi
"""

WAIT_STUB = """\
echo "condor_wait $*" >> "$STUB_LOG"
[ -z "${STUB_WAIT_SLEEP:-}" ] || sleep "$STUB_WAIT_SLEEP"
w=$(cat "$STUB_LOG.wn" 2>/dev/null || echo 0); w=$((w + 1)); echo "$w" > "$STUB_LOG.wn"
if [ -n "${STUB_RV:-}" ] && [ "$w" -ge "${STUB_RV_FROM_WAIT:-1}" ]; then
  echo "004 (1.0) Job terminated. (1) Normal termination (return value $STUB_RV)" >> condor.log
fi
[ -z "${STUB_MADE:-}" ] || tar -czf output.tar.gz -C "$STUB_MADE" _site
exit "${STUB_WAIT_RC:-0}"
"""


RM_STUB = 'echo "condor_rm $*" >> "$STUB_LOG"\n'

Q_STUB = """\
echo "condor_q $*" >> "$STUB_LOG"
case " $* " in *" -af ClusterId "*)
  # The head probe: STUB_IDLE="host=count ..." gives each head's idle jobs.
  [ "$STUB_HOST" != "${STUB_Q_FAIL_HOST:-none-}" ] || exit 1
  [ "$STUB_HOST" != "${STUB_Q_SLOW_HOST:-none-}" ] || sleep 5
  for kv in ${STUB_IDLE:-}; do [ "${kv%%=*}" != "$STUB_HOST" ] || seq 1 "${kv#*=}"; done
  exit 0 ;;
esac
case " $* " in *" -af JobStatus "*)
  # STUB_Q_STATUSES gives one status per call, in order; then STUB_Q_STATUS.
  n=$(cat "$STUB_LOG.qn" 2>/dev/null || echo 0); echo $((n + 1)) > "$STUB_LOG.qn"
  read -ra seq <<< "${STUB_Q_STATUSES:-}"
  echo "${seq[$n]-${STUB_Q_STATUS-2}}"; exit "${STUB_Q_RC:-0}" ;;
esac
echo "analysis of $*: no machine matches the requirements"
[ -z "${STUB_Q_LINES:-}" ] || seq 1 "$STUB_Q_LINES"
[ -z "${STUB_Q_RC:-}" ] || exit "$STUB_Q_RC"
"""

STATUS_STUB = """\
echo "condor_status $*" >> "$STUB_LOG"
case " $* " in *" -af Cpus Memory Disk "*)
  # The head probe: STUB_SLOTS="host:cpus:mb:kib ..." gives each unclaimed slot.
  for slot in ${STUB_SLOTS:-}; do
    IFS=: read -r h c m d <<< "$slot"
    [ "$h" != "$STUB_HOST" ] || echo "$c $m $d"
  done
  exit 0 ;;
esac
echo "pool totals: 0 machines available"
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
    _stub(bin_dir / "condor_rm", RM_STUB)
    _stub(bin_dir / "condor_q", Q_STUB)
    _stub(bin_dir / "condor_status", STATUS_STUB)
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


def _submits(calls: list[str]) -> list[str]:
    """The ssh calls that submit a job; the head probes set ConnectTimeout."""
    return [c for c in calls
            if c.startswith("ssh ") and " bash " in c and "ConnectTimeout" not in c]


def test_five_steps_make_exactly_one_submission(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b", "c", "d", "e"], STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    assert _count(calls, "condor_submit") == 1
    assert _count(calls, "ssh ") == 1


def test_ssh_accepts_a_new_host_key_but_never_turns_checking_off(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b", "c", "d", "e"], STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    ssh_calls = [c for c in calls if c.startswith("ssh ")]
    assert ssh_calls
    for call in ssh_calls:
        assert "StrictHostKeyChecking=accept-new" in call
        assert "StrictHostKeyChecking=no" not in call


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


def test_wait_limit_is_passed_to_condor_wait_and_a_late_job_is_removed(tmp_path):
    # condor_wait -wait expired with no "return value" line: the job is removed
    # and the script exits 70, so the action reruns the steps on the runner.
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_WAIT_MINUTES="15", STUB_WAIT_RC="1"
    )
    assert proc.returncode == 70
    assert "condor_wait -wait 900 condor.log" in calls
    assert "condor_rm 77" in calls
    assert "did not end within 15 minutes" in proc.stderr


def test_a_late_job_is_explained_in_the_log_before_it_is_removed(tmp_path):
    # gha#2041: the queue entry is gone after condor_rm, so the analysis, the
    # pool totals and the tail of condor.log are printed first.
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_WAIT_MINUTES="15", STUB_WAIT_RC="1"
    )
    assert proc.returncode == 70
    assert "condor_q -better-analyze 77" in calls
    assert "condor_status -total" in calls
    assert calls.index("condor_q -better-analyze 77") < calls.index("condor_rm 77")
    assert "no machine matches the requirements" in proc.stderr
    assert "pool totals: 0 machines available" in proc.stderr
    assert "--- tail of condor.log" in proc.stderr


def test_a_failing_diagnostic_does_not_stop_the_fallback(tmp_path):
    # condor_q failing must not skip condor_status, condor_rm or exit 70.
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_WAIT_MINUTES="15", STUB_WAIT_RC="1", STUB_Q_RC="3"
    )
    assert proc.returncode == 70
    assert "condor_status -total" in calls
    assert "condor_rm 77" in calls
    assert "did not end within 15 minutes" in proc.stderr


def test_long_diagnostics_are_cut_and_do_not_stop_the_fallback(tmp_path):
    # head closes the pipe after 150 lines and the group gets SIGPIPE; under
    # set -eo pipefail the script must still remove the job and exit 70.
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_WAIT_MINUTES="15", STUB_WAIT_RC="1", STUB_Q_LINES="400"
    )
    assert proc.returncode == 70
    assert "condor_rm 77" in calls
    lines = proc.stderr.splitlines()
    assert "399" not in lines
    assert "did not end normally" in proc.stderr


def test_no_diagnostics_for_a_job_that_ended_or_without_a_limit(tmp_path):
    ended, ended_calls = _run(tmp_path, ["a", "b"], CONDOR_WAIT_MINUTES="15", STUB_RV="0")
    assert ended.returncode == 0, ended.stderr
    assert _count(ended_calls, "condor_q") == 0
    sub = tmp_path / "unbounded"
    sub.mkdir()
    proc, calls = _run(sub, ["a", "b"], STUB_WAIT_RC="1")
    assert proc.returncode == 70
    assert _count(calls, "condor_q") == 0
    assert _count(calls, "condor_status") == 0


def test_no_wait_limit_by_default(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b"], STUB_WAIT_RC="1")
    assert proc.returncode == 70
    assert "condor_wait condor.log" in calls
    assert _count(calls, "condor_rm") == 0


def test_wait_limit_does_not_remove_a_job_that_ended(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b"], CONDOR_WAIT_MINUTES="08", STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    assert "condor_wait -wait 480 condor.log" in calls
    assert _count(calls, "condor_rm") == 0


def test_wait_limit_does_not_remove_a_job_that_ended_without_a_value(tmp_path):
    # condor_wait returned 0 (the job ended, e.g. aborted) with no return
    # value: exit 70 without condor_rm or the timeout wording.
    proc, calls = _run(tmp_path, ["a", "b"], CONDOR_WAIT_MINUTES="15")
    assert proc.returncode == 70
    assert _count(calls, "condor_rm") == 0
    assert "did not end within" not in proc.stderr


def test_a_job_still_idle_after_the_idle_limit_is_explained_and_removed(tmp_path):
    # gha#2085: the job never started, so the runner takes over after the
    # idle limit instead of waiting until the job timeout.
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_IDLE_MINUTES="20", STUB_WAIT_RC="1",
        STUB_Q_STATUS="1",
    )
    assert proc.returncode == 70
    assert "condor_wait -wait 1200 condor.log" in calls
    assert "condor_q 77 -af JobStatus" in calls
    assert calls.index("condor_q -better-analyze 77") < calls.index("condor_rm 77")
    assert _count(calls, "condor_wait") == 1
    assert "did not start within 20 minutes" in proc.stderr
    assert "no machine matches the requirements" in proc.stderr


def test_a_job_that_started_is_not_removed_by_the_idle_limit(tmp_path):
    # Running (JobStatus 2) when the idle limit passes: wait on, unbounded.
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_IDLE_MINUTES="20", STUB_WAIT_RC="1",
        STUB_Q_STATUS="2", STUB_RV="0",
    )
    assert proc.returncode == 0, proc.stderr
    assert "condor_wait -wait 1200 condor.log" in calls
    assert "condor_wait condor.log" in calls
    assert _count(calls, "condor_rm") == 0


def test_an_unknown_job_status_does_not_remove_the_job(tmp_path):
    # condor_q failing says nothing about the job, so it is not removed.
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_IDLE_MINUTES="20", STUB_WAIT_RC="1",
        STUB_Q_RC="3", STUB_Q_STATUS="", STUB_RV="0",
    )
    assert proc.returncode == 0, proc.stderr
    assert _count(calls, "condor_rm") == 0


def test_the_wait_limit_still_counts_from_submission(tmp_path):
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_IDLE_MINUTES="20", CONDOR_WAIT_MINUTES="90",
        STUB_WAIT_RC="1", STUB_Q_STATUS="2",
    )
    assert proc.returncode == 70
    assert "condor_wait -wait 4200 condor.log" in calls
    assert "condor_rm 77" in calls
    assert "did not end within 90 minutes" in proc.stderr


def test_a_job_that_ends_inside_the_idle_window_is_waited_for_once(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b"], CONDOR_IDLE_MINUTES="20", STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    assert _count(calls, "condor_wait") == 1
    assert _count(calls, "condor_q") == 0


def test_no_idle_limit_by_default(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b"], STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    assert calls.count("condor_wait condor.log") == 1


def test_malformed_idle_limit_is_refused(tmp_path):
    for bad in ["0", "-5", "1.5", "ten"]:
        sub = tmp_path / bad.replace(".", "_")
        sub.mkdir()
        proc, calls = _run(sub, ["a", "b"], CONDOR_IDLE_MINUTES=bad)
        assert proc.returncode == 64, bad
        assert calls == [], bad


def test_malformed_wait_limit_is_refused(tmp_path):
    for bad in ["0", "00", "000", "-5", "1.5", "ten", "15 "]:
        sub = tmp_path / bad.replace(" ", "_").replace(".", "_")
        sub.mkdir()
        proc, calls = _run(sub, ["a", "b"], CONDOR_WAIT_MINUTES=bad)
        assert proc.returncode == 64, bad
        assert calls == [], bad


def test_ssh_key_with_whitespace_is_refused(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b"], CONDOR_SSH_KEY="/tmp/my key")
    assert proc.returncode == 64
    assert calls == []


def test_output_paths_that_break_the_submit_file_or_leave_the_checkout_are_refused(
    tmp_path,
):
    bad = [
        "my site",
        "_site,my site",
        'a"b',
        "a'b",
        "a\\b",
        "/etc",
        "..",
        "../up",
        "a/..",
        "a/../b",
        "_site,/abs",
    ]
    for i, output in enumerate(bad):
        run_dir = tmp_path / str(i)
        run_dir.mkdir()
        proc, calls = _run(run_dir, ["a", "b"], CONDOR_OUTPUT=output)
        assert proc.returncode == 64, output
        assert "CONDOR_OUTPUT" in proc.stderr, output
        assert calls == [], output


def test_output_paths_inside_the_checkout_are_accepted(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="0", CONDOR_OUTPUT="_site,docs/out,a..b")
    assert proc.returncode != 64, proc.stderr
    assert "CONDOR_OUTPUT must" not in proc.stderr
    assert "must stay inside" not in proc.stderr


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
    # The image's TeX tree is read-only, so LuaLaTeX needs a writable cache (gha#2012).
    assert "--env TEXMFVAR=/tmp --env TEXMFCACHE=/tmp" in run


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


def _run_action(tmp_path: Path, script_rc: int, **extra):
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
        # The fallback takes a render slot (gha#2062); keep its locks here.
        "SLOT_SCRIPT": str(ACTION.parents[3] / "scripts" / "with-render-slot.sh"),
        "RUNNER_ENVIRONMENT": "self-hosted",
        "RENDER_SLOTS": "1",
        "RENDER_SLOT_DIR": str(tmp_path / "slots"),
        **extra,
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


def test_composite_never_runs_locally_when_fallback_is_disabled(tmp_path):
    # gha#2108: a render composite passes allow-local-fallback 'false', so on a
    # self-hosted runner a cluster failure fails the step instead of
    # rendering there. A GitHub-hosted runner still falls back.
    for env, rc, final, local in [
        ("self-hosted", 70, 1, False), ("self-hosted", 71, 1, False),
        ("self-hosted", 0, 0, False), ("self-hosted", 2, 2, False),
        ("github-hosted", 70, 0, True), ("github-hosted", 71, 0, True),
    ]:
        case_dir = tmp_path / f"{env}-{rc}"
        case_dir.mkdir()
        code, ran_locally = _run_action(
            case_dir, rc, ALLOW_LOCAL_FALLBACK="false", RUNNER_ENVIRONMENT=env)
        assert (code, ran_locally) == (final, local), (env, rc)


def test_head_list_is_spread_by_run_number(tmp_path):
    for run, expected in (("42", "a.example"), ("43", "b.example")):
        case_dir = tmp_path / run
        case_dir.mkdir()
        _, calls = _run(
            case_dir, ["a", "b"], STUB_RV="0", RUN_ID=run,
            CONDOR_HEAD="a.example,b.example",
        )
        submit_ssh = [c for c in _submits(calls) if " -- " in c and "/ci/" in c]
        assert len(submit_ssh) == 1
        assert expected in submit_ssh[0], (run, submit_ssh)


def test_fallback_head_is_never_chosen_by_the_spreading(tmp_path):
    # gha#2091: whatever the run number, the job starts on a CONDOR_HEAD head.
    for run in ("42", "43"):
        case_dir = tmp_path / run
        case_dir.mkdir()
        _, calls = _run(
            case_dir, ["a", "b"], STUB_RV="0", RUN_ID=run,
            CONDOR_HEAD="a.example", CONDOR_FALLBACK_HEAD="z.example",
        )
        submit_ssh = [c for c in _submits(calls) if " -- " in c and "/ci/" in c]
        assert len(submit_ssh) == 1
        assert "a.example" in submit_ssh[0], (run, submit_ssh)


def test_fallback_head_takes_a_job_idle_everywhere_else(tmp_path):
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_HEAD="a.example",
        CONDOR_FALLBACK_HEAD="z.example",
        CONDOR_IDLE_MINUTES="20", STUB_WAIT_RC="1", STUB_Q_STATUSES="1 2",
        STUB_RV="0", STUB_RV_FROM_WAIT="2",
    )
    assert proc.returncode == 0, proc.stderr
    assert _count(calls, "condor_submit") == 2
    submits = [c for c in _submits(calls) if "/ci/" in c]
    assert "a.example" in submits[0] and "z.example" in submits[-1], submits
    assert "head a.example did not start the job; trying z.example" in proc.stderr


def test_fallback_head_is_tried_once(tmp_path):
    # The retry gets the untried heads as CONDOR_HEAD and no fallback, so the
    # fallback head is not appended a second time.
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_HEAD="a.example",
        CONDOR_FALLBACK_HEAD="z.example",
        CONDOR_IDLE_MINUTES="20", STUB_WAIT_RC="1", STUB_Q_STATUS="1",
    )
    assert proc.returncode == 70
    assert _count(calls, "condor_submit") == 2


def test_fallback_head_already_listed_is_not_tried_twice(tmp_path):
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_HEAD="a.example z.example",
        CONDOR_FALLBACK_HEAD="z.example",
        CONDOR_IDLE_MINUTES="20", STUB_WAIT_RC="1", STUB_Q_STATUS="1",
    )
    assert proc.returncode == 70
    assert _count(calls, "condor_submit") == 2


def test_unreachable_head_falls_back_to_the_next(tmp_path):
    proc, calls = _run(
        tmp_path, ["a", "b"], STUB_RV="0", STUB_SSH_FAIL_HOST="a.example",
        CONDOR_HEAD="a.example b.example",
    )
    assert proc.returncode == 0, proc.stderr
    assert "a.example did not answer" in proc.stderr
    assert _count(calls, "condor_submit") == 1
    assert any("b.example bash" in c for c in _submits(calls))


def test_a_job_idle_on_one_head_moves_to_the_next(tmp_path):
    # gha#2087: idle on a.example, started on b.example.
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_HEAD="a.example b.example",
        CONDOR_IDLE_MINUTES="20", STUB_WAIT_RC="1", STUB_Q_STATUSES="1 2",
        STUB_RV="0", STUB_RV_FROM_WAIT="2",
    )
    assert proc.returncode == 0, proc.stderr
    assert _count(calls, "condor_submit") == 2
    submits = [c for c in _submits(calls) if "/ci/" in c]
    assert "a.example" in submits[0] and "b.example" in submits[-1], submits
    assert "head a.example did not start the job; trying b.example" in proc.stderr
    assert any("b.example:" in c and "/42-h2/" in c for c in calls), calls
    assert not (tmp_path / "ci" / "42").exists()


def test_no_head_starting_the_job_falls_back_to_the_runner(tmp_path):
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_HEAD="a.example b.example c.example",
        CONDOR_IDLE_MINUTES="20", STUB_WAIT_RC="1", STUB_Q_STATUS="1",
    )
    assert proc.returncode == 70
    assert _count(calls, "condor_submit") == 3
    assert calls.count("condor_rm 77") == 3
    assert "no cluster head started the job within 20 minutes" in proc.stderr
    assert not any(p.name.startswith("42") for p in (tmp_path / "ci").iterdir())


def test_an_idle_job_with_output_still_moves_to_the_next_head(tmp_path):
    # The first head removed its run directory, so there is nothing to fetch
    # there; the output comes back from the head that ran the job.
    made = _site_stub(tmp_path)
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_HEAD="a.example b.example",
        CONDOR_IDLE_MINUTES="20", STUB_WAIT_RC="1", STUB_Q_STATUSES="1 2",
        STUB_RV="0", STUB_RV_FROM_WAIT="2", CONDOR_OUTPUT="_site", STUB_MADE=made,
    )
    assert proc.returncode == 0, proc.stderr
    assert _count(calls, "condor_submit") == 2
    assert "could not bring" not in proc.stderr
    assert not any("a.example:" in c and "output.tar.gz" in c for c in calls), calls
    assert (tmp_path / "checkout" / "_site" / "index.html").read_text() == "built"


def test_a_step_exiting_73_is_not_read_as_an_idle_job(tmp_path):
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_HEAD="a.example b.example", STUB_RV="73",
    )
    assert proc.returncode == 1
    assert _count(calls, "condor_submit") == 1


def test_queue_time_is_logged_with_the_head(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="0", STUB_QUEUE_LOG="1")
    assert proc.returncode == 0, proc.stderr
    assert "started the job after 200 s in the queue" in proc.stderr


def test_no_head_answering_exits_70(tmp_path):
    proc, calls = _run(
        tmp_path, ["a", "b"], STUB_SSH_RC="255", CONDOR_HEAD="a.example b.example",
    )
    assert proc.returncode == 70
    assert "no cluster head answered" in proc.stderr
    assert _count(calls, "condor_submit") == 0


def _desktop_run(tmp_path: Path, **extra_env: str):
    image = tmp_path / "lds-ci.sif"
    image.write_text("sif")
    return _run(
        tmp_path, ["a", "b"], STUB_RV="0", CONDOR_HEAD="desk.example:922",
        CONDOR_DESKTOP_HEADS="desk.example", CONDOR_IMAGE_FILE=str(image), **extra_env,
    )


def _submit_lines(tmp_path: Path) -> list[str]:
    return (tmp_path / "calls.log.sub").read_text().splitlines()


def test_desktop_head_uses_its_port_for_ssh_and_rsync(tmp_path):
    proc, calls = _desktop_run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    transfers = [c for c in calls if c.startswith(("ssh ", "rsync "))]
    assert transfers
    assert all("-p 922" in c for c in transfers), transfers
    assert all("desk.example:922" not in c for c in transfers), transfers


def test_desktop_head_requests_the_desktop_pool_and_a_home_relative_root(tmp_path):
    proc, calls = _desktop_run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "+CSCI_GrpDesktop = True" in _submit_lines(tmp_path)
    assert any("desk.example:lds-ci/42/checkout.tar.gz" in c for c in calls), calls


def test_desktop_head_transfers_the_image_with_the_job(tmp_path):
    proc, calls = _desktop_run(tmp_path, CONDOR_IMAGE="/cluster/home/x/lds-ci.sif")
    assert proc.returncode == 0, proc.stderr
    assert any("desk.example:lds-ci/42/lds-ci.sif" in c for c in calls), calls
    lines = _submit_lines(tmp_path)
    transfer = next(line for line in lines if line.startswith("transfer_input_files"))
    assert transfer.endswith("/lds-ci.sif")
    assert "arguments = lds-ci.sif" in lines
    run = (tmp_path / "calls.log.run").read_text()
    assert '"$scratch/$img"' in run


def test_cluster_head_ignores_the_image_file_and_the_desktop_pool(tmp_path):
    image = tmp_path / "lds-ci.sif"
    image.write_text("sif")
    proc, calls = _run(
        tmp_path, ["a", "b"], STUB_RV="0", CONDOR_HEAD="a.example",
        CONDOR_IMAGE="/c/x.sif", CONDOR_IMAGE_FILE=str(image),
    )
    assert proc.returncode == 0, proc.stderr
    assert "+CSCI_GrpDesktop = True" not in _submit_lines(tmp_path)
    assert "arguments = /c/x.sif" in _submit_lines(tmp_path)
    assert not any("lds-ci.sif" in c for c in calls if c.startswith("rsync "))


def test_unreadable_desktop_image_file_exits_70(tmp_path):
    proc, calls = _run(
        tmp_path, ["a", "b"], CONDOR_HEAD="desk.example:922",
        CONDOR_DESKTOP_HEADS="desk.example", CONDOR_IMAGE_FILE=str(tmp_path / "missing.sif"),
    )
    assert proc.returncode == 70
    assert _count(calls, "condor_submit") == 0


def test_unreachable_desktop_head_falls_back_with_its_port_probed(tmp_path):
    proc, calls = _run(
        tmp_path, ["a", "b"], STUB_RV="0", STUB_SSH_FAIL_HOST="a.example",
        CONDOR_HEAD="a.example desk.example:922", CONDOR_DESKTOP_HEADS="desk.example",
    )
    assert proc.returncode == 0, proc.stderr
    probe = next(c for c in calls if "ConnectTimeout" in c and "desk.example" in c)
    assert "-p 922" in probe, probe


def _site_stub(tmp_path: Path) -> str:
    """Stand in for the job's output: wait stub drops output.tar.gz in the run dir."""
    site = tmp_path / "made" / "_site"
    site.mkdir(parents=True)
    (site / "index.html").write_text("built")
    return str(tmp_path / "made")


def test_no_output_path_returns_nothing(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="0")
    assert proc.returncode == 0, proc.stderr
    sub = (tmp_path / "calls.log.sub").read_text()
    assert 'transfer_output_files = ""' in sub
    assert "CONDOR_OUTPUT" not in sub


def test_output_path_is_returned_by_file_transfer_and_unpacked(tmp_path):
    made = _site_stub(tmp_path)
    proc, calls = _run(
        tmp_path, ["a", "b"], STUB_RV="0", CONDOR_OUTPUT="_site", STUB_MADE=made
    )
    assert proc.returncode == 0, proc.stderr
    sub = (tmp_path / "calls.log.sub").read_text()
    assert "transfer_output_files = output.tar.gz" in sub
    assert 'environment = "CONDOR_OUTPUT=_site"' in sub
    assert (tmp_path / "checkout" / "_site" / "index.html").read_text() == "built"
    # The one extra rsync is the fetch, and the run directory is removed after it.
    assert _count(calls, "rsync ") == 3
    assert not (tmp_path / "ci" / "42").exists()


def _pack(tmp_path: Path, output: str, step: str) -> list[str]:
    """Run the generated .condor-run.sh directly and list what output.tar.gz holds."""
    _run(tmp_path, ["a", "b"], STUB_RV="0", CONDOR_OUTPUT=output)
    work = tmp_path / "scratch"
    work.mkdir()
    (work / ".condor-steps").write_text(step + "\n")
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["tar", "-czf", str(work / "checkout.tar.gz"), "-C", str(seed), "."], check=True)
    env = {**os.environ, "CONDOR_OUTPUT": output}
    proc = subprocess.run(
        ["bash", str(tmp_path / "calls.log.run")], cwd=work, env=env,
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    listing = subprocess.run(
        ["tar", "-tzf", str(work / "output.tar.gz")], capture_output=True, text=True, check=True,
    )
    return sorted(line for line in listing.stdout.splitlines() if not line.endswith("/"))


def test_several_output_paths_are_packed_together(tmp_path):
    step = "mkdir _site _freeze && echo a > _site/i.html && echo b > _freeze/p.json"
    assert _pack(tmp_path, "_site,_freeze", step) == ["_freeze/p.json", "_site/i.html"]


def test_a_missing_output_path_is_skipped_and_the_rest_returned(tmp_path):
    step = "mkdir _site && echo a > _site/i.html"
    assert _pack(tmp_path, "_site,_freeze", step) == ["_site/i.html"]


def test_no_output_path_made_packs_an_empty_tarball(tmp_path):
    assert _pack(tmp_path, "_site,_freeze", "true") == []


def test_output_is_returned_even_when_a_step_fails(tmp_path):
    made = _site_stub(tmp_path)
    proc, _ = _run(
        tmp_path, ["a", "b"], STUB_RV="3", CONDOR_OUTPUT="_site", STUB_MADE=made
    )
    assert proc.returncode == 3, proc.stderr
    assert (tmp_path / "checkout" / "_site" / "index.html").exists()
    assert not (tmp_path / "ci" / "42").exists()


def test_failed_fetch_of_the_output_exits_70(tmp_path):
    proc, _ = _run(tmp_path, ["a", "b"], STUB_RV="0", CONDOR_OUTPUT="_site")
    assert proc.returncode == 70
    assert "could not bring _site back" in proc.stderr


def test_jobs_of_one_run_get_different_run_directories(tmp_path):
    dirs = set()
    for job in ("render-solution", "render-assign"):
        case_dir = tmp_path / job
        case_dir.mkdir()
        proc, calls = _run(
            case_dir, ["a", "b"], STUB_RV="0", RUN_ID="",
            GITHUB_RUN_ID="9001", GITHUB_JOB=job, GITHUB_RUN_ATTEMPT="1",
        )
        assert proc.returncode == 0, proc.stderr
        copied = [c for c in calls if c.startswith("rsync") and c.endswith(".condor-steps")]
        assert len(copied) == 1
        dirs.add(copied[0].rsplit(":", 1)[1].split("/ci/", 1)[1])
    assert len(dirs) == 2, dirs


# gha#2093: with several heads, each head's queue decides the order.
SLOT = "8:16384:52428800"  # 2 copies of the default 4 CPU, 8GB, 20GB request


def _head_run(tmp_path: Path, **extra_env: str):
    return _run(tmp_path, ["a", "b"], STUB_RV="0", **extra_env)


def test_a_head_with_room_is_chosen_over_the_spread_order(tmp_path):
    # Run 42 starts the spread at a.example, but only b.example has room.
    proc, calls = _head_run(
        tmp_path, CONDOR_HEAD="a.example b.example",
        STUB_IDLE="a.example=5", STUB_SLOTS=f"b.example:{SLOT}",
    )
    assert proc.returncode == 0, proc.stderr
    submits = [c for c in _submits(calls) if "/ci/" in c]
    assert len(submits) == 1 and "b.example" in submits[0], submits
    assert "head a.example: 5 idle job(s) in the queue; 0 copies" in proc.stderr
    assert "head b.example: 0 idle job(s) in the queue; 2 copies" in proc.stderr
    assert "chose head b.example (order: b.example a.example)" in proc.stderr


def test_fit_counts_copies_of_the_request_not_free_slots(tmp_path):
    # b.example has more free slots, but none fits 4 CPUs; a.example's one
    # slot fits two copies against one idle job.
    proc, _ = _head_run(
        tmp_path, RUN_ID="43", CONDOR_HEAD="a.example b.example",
        STUB_IDLE="a.example=1",
        STUB_SLOTS=f"a.example:{SLOT} b.example:2:65536:99999999 b.example:3:65536:99999999",
    )
    assert proc.returncode == 0, proc.stderr
    assert "head b.example: 0 idle job(s) in the queue; 0 copies" in proc.stderr
    assert "chose head a.example (order: a.example b.example)" in proc.stderr


def test_a_bare_memory_request_is_read_as_megabytes(tmp_path):
    proc, _ = _head_run(
        tmp_path, CONDOR_HEAD="a.example b.example", REQUEST_MEMORY="16384",
        STUB_SLOTS=f"b.example:{SLOT}",
    )
    assert proc.returncode == 0, proc.stderr
    assert "head b.example: 0 idle job(s) in the queue; 1 copies" in proc.stderr


def test_more_room_wins_and_ties_keep_the_order(tmp_path):
    proc, _ = _head_run(
        tmp_path, CONDOR_HEAD="a.example b.example c.example",
        STUB_SLOTS=f"a.example:{SLOT} b.example:{SLOT} b.example:{SLOT} c.example:{SLOT}",
    )
    assert proc.returncode == 0, proc.stderr
    assert "(order: b.example a.example c.example)" in proc.stderr


def test_a_fallback_head_with_room_goes_first(tmp_path):
    proc, calls = _head_run(
        tmp_path, CONDOR_HEAD="a.example", CONDOR_FALLBACK_HEAD="z.example",
        STUB_SLOTS=f"z.example:{SLOT}",
    )
    assert proc.returncode == 0, proc.stderr
    assert "chose head z.example (order: z.example a.example)" in proc.stderr


def test_without_room_anywhere_the_fallback_stays_last(tmp_path):
    proc, _ = _head_run(
        tmp_path, CONDOR_HEAD="a.example", CONDOR_FALLBACK_HEAD="z.example",
        STUB_IDLE="z.example=3", STUB_SLOTS=f"z.example:{SLOT}",
    )
    assert proc.returncode == 0, proc.stderr
    assert "chose head a.example (order: a.example z.example)" in proc.stderr


def test_a_head_whose_queue_cannot_be_read_keeps_its_place(tmp_path):
    proc, _ = _head_run(
        tmp_path, CONDOR_HEAD="a.example b.example c.example",
        STUB_Q_FAIL_HOST="a.example", STUB_SLOTS=f"c.example:{SLOT}",
    )
    assert proc.returncode == 0, proc.stderr
    assert "head a.example: queue could not be read" in proc.stderr
    assert "(order: c.example a.example b.example)" in proc.stderr


def test_one_head_is_not_probed(tmp_path):
    proc, calls = _head_run(tmp_path, CONDOR_HEAD="a.example")
    assert proc.returncode == 0, proc.stderr
    assert not any("-af ClusterId" in c for c in calls)
    assert "chose head" not in proc.stderr


def test_a_head_that_reports_too_slowly_keeps_its_place(tmp_path):
    proc, _ = _head_run(
        tmp_path, CONDOR_HEAD="a.example b.example c.example",
        CONDOR_PROBE_SECONDS="1", STUB_Q_SLOW_HOST="a.example",
        STUB_SLOTS=f"c.example:{SLOT}",
    )
    assert proc.returncode == 0, proc.stderr
    assert "head a.example did not report within 1s" in proc.stderr
    assert "(order: c.example a.example b.example)" in proc.stderr
