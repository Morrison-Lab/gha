"""Offline test of condor-batch.sh: stub ssh and rsync record every call."""

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "condor-batch.sh"


def _stub(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path: Path, steps: list[str]):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    # ssh logs its argv and the script it receives on stdin.
    _stub(bin_dir / "ssh", f'echo "ssh $*" >> {log}; cat >> {log}\n')
    _stub(bin_dir / "rsync", f'echo "rsync $*" >> {log}\n')
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    steps_file = tmp_path / "steps.txt"
    steps_file.write_text("\n".join(steps) + "\n")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "RUN_ID": "42"}
    proc = subprocess.run(
        ["bash", str(SCRIPT), str(checkout), str(steps_file)],
        env=env, capture_output=True, text=True, check=False,
    )
    calls = log.read_text() if log.exists() else ""
    return proc, calls


def test_five_steps_make_exactly_one_submission(tmp_path):
    proc, calls = _run(tmp_path, ["a", "b", "c", "d", "e"])
    assert proc.returncode == 0, proc.stderr
    assert calls.count("condor_submit") == 1
    assert sum(l.startswith("ssh ") for l in calls.splitlines()) == 1
    assert "/cluster/home/morri313/ci/42" in calls


def test_single_step_is_refused_without_contacting_the_cluster(tmp_path):
    proc, calls = _run(tmp_path, ["only"])
    assert proc.returncode == 2
    assert "refusing" in proc.stderr
    assert calls == ""
