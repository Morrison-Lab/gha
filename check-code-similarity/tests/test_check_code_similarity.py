#!/usr/bin/env python3
"""Offline tests for check_code_similarity.py (gha#296).

A stub `java` writes a canned JPlag results CSV, so this suite needs neither
the 80 MB jar nor a JDK. That matters beyond speed: the branches worth pinning
are the ones a real green run never reaches -- an empty corpus, a crashed
JPlag, a missing results file -- and a suite that can only exercise the happy
path proves nothing about them.

**The negative cases are the ones to keep if this is ever trimmed.** Every one
of them fails in the same direction: a similarity check that could not run
prints no findings, which is indistinguishable from a check that ran and found
none. Each must be an error rather than a quiet pass.

Usage::

    python3 -m pytest check-code-similarity/tests/ -q
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "check_code_similarity.py"

# A stub stands in for the jar. Its real digest is irrelevant offline, but the
# script must still verify SOMETHING here or the pin itself goes untested.
STUB_JAR_BODY = b"not a real jar"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Build a submission tree, a corpus, and a stub `java` on PATH."""
    (tmp_path / "new" / "submission").mkdir(parents=True)
    (tmp_path / "new" / "submission" / "a.R").write_text("f <- function() 1\n")
    (tmp_path / "corpus" / "alice").mkdir(parents=True)
    (tmp_path / "corpus" / "alice" / "a.R").write_text("g <- function() 2\n")

    jar = tmp_path / "jplag.jar"
    jar.write_bytes(STUB_JAR_BODY)

    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return tmp_path, jar, bindir


def write_stub_java(bindir: pathlib.Path, *, csv: str | None, exit_code: int = 0,
                    stderr: str = "") -> None:
    """Install a `java` that mimics one JPlag run.

    It parses `-r <dir>` out of its own argv so the script's real
    result-path plumbing is exercised, rather than assumed.
    """
    script = textwrap.dedent(
        f"""\
        #!/usr/bin/env python3
        import pathlib, sys
        argv = sys.argv[1:]
        sys.stderr.write({stderr!r})
        result = None
        for i, a in enumerate(argv):
            if a == "-r":
                result = pathlib.Path(argv[i + 1])
        csv = {csv!r}
        if csv is not None and result is not None:
            result.mkdir(parents=True, exist_ok=True)
            (result / "results.csv").write_text(csv)
        raise SystemExit({exit_code})
        """
    )
    path = bindir / "java"
    path.write_text(script)
    path.chmod(0o755)


def run(tmp_path, jar, *extra, **kwargs):
    cmd = [
        sys.executable, str(SCRIPT),
        "--path", str(tmp_path / "new"),
        "--corpus-path", str(kwargs.pop("corpus", tmp_path / "corpus")),
        "--language", "rlang",
        "--jar", str(jar),
        "--jplag-sha256", sha256_of(STUB_JAR_BODY),
        "--work-dir", str(tmp_path / "work"),
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


HEADER = "submissionName1,submissionName2,averageSimilarity,maxSimilarity\n"


def test_clean_run_reports_what_it_compared(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER + "new/submission,corpus/alice,0.1,0.12\n")
    result = run(tmp_path, jar, "--fail")
    assert result.returncode == 0, result.stderr
    # Not merely "no findings": the run must say it examined something, so a
    # vacuous pass is distinguishable from a real one.
    assert "Comparing 1 submission(s) against 1 corpus submission(s)." in result.stdout
    assert "No pair at or above" in result.stdout


def test_similar_pair_is_flagged(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER + "new/submission,corpus/alice,0.9,0.95\n")
    result = run(tmp_path, jar)
    assert result.returncode == 0          # a warning by default
    assert "::warning::" in result.stdout
    assert "0.9500" in result.stdout


def test_fail_flag_turns_a_finding_into_a_failure(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER + "new/submission,corpus/alice,0.9,0.95\n")
    result = run(tmp_path, jar, "--fail")
    assert result.returncode == 1
    assert "::error::" in result.stdout


def test_threshold_is_inclusive(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER + "new/submission,corpus/alice,0.8,0.8\n")
    assert run(tmp_path, jar, "--fail", "--threshold", "0.8").returncode == 1
    assert run(tmp_path, jar, "--fail", "--threshold", "0.81").returncode == 0


def test_corpus_internal_pairs_are_ignored(env):
    """Two prior submissions resembling each other is not this PR's problem."""
    tmp_path, jar, bindir = env
    (tmp_path / "corpus" / "bob").mkdir()
    (tmp_path / "corpus" / "bob" / "a.R").write_text("h <- 3\n")
    write_stub_java(
        bindir,
        csv=HEADER
        + "corpus/alice,corpus/bob,0.99,0.99\n"
        + "new/submission,corpus/alice,0.1,0.1\n",
    )
    result = run(tmp_path, jar, "--fail")
    assert result.returncode == 0, result.stdout


def test_a_corpus_entry_sharing_a_name_is_not_mistaken_for_the_submission(env):
    """Two students both submitting `analysis/` must stay distinguishable.

    Matching on the submission's own basename would read this corpus-internal
    pair as a finding against the PR.
    """
    tmp_path, jar, bindir = env
    (tmp_path / "new" / "analysis").mkdir()
    (tmp_path / "new" / "analysis" / "a.R").write_text("k <- 1\n")
    (tmp_path / "corpus" / "analysis").mkdir()
    (tmp_path / "corpus" / "analysis" / "a.R").write_text("k <- 2\n")
    write_stub_java(
        bindir,
        csv=HEADER
        + "corpus/analysis,corpus/alice,0.99,0.99\n"
        + "new/analysis,corpus/alice,0.1,0.1\n",
    )
    result = run(tmp_path, jar, "--fail")
    assert result.returncode == 0, result.stdout


def test_no_relevant_pair_is_an_error_not_a_clean_result(env):
    """JPlag compared things, but none of them was the submission under review.

    That is a false negative wearing a clean result: the check reports nothing
    found, having evaluated nothing that mattered.
    """
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER + "corpus/alice,corpus/bob,0.2,0.2\n")
    result = run(tmp_path, jar)
    assert result.returncode == 2
    assert "nothing being reviewed was evaluated" in result.stderr


def test_identical_root_names_are_refused(env):
    """JPlag labels by root basename, so two roots named alike are ambiguous."""
    tmp_path, jar, bindir = env
    twin = tmp_path / "twin"
    (twin / "new").mkdir(parents=True)
    (twin / "new" / "s").mkdir()
    write_stub_java(bindir, csv=HEADER + "new/s,new/s,0.1,0.1\n")
    result = run(tmp_path, jar, corpus=twin / "new")
    assert result.returncode == 2
    assert "same directory name" in result.stderr


def test_jplag_stderr_is_not_forwarded_to_the_log(env):
    """JPlag quotes source; publishing it defeats the upload-report default."""
    tmp_path, jar, bindir = env
    secret = "super_secret_identifier_from_a_students_file"
    write_stub_java(bindir, csv=None, exit_code=3, stderr=f"error near {secret}\n")
    result = run(tmp_path, jar)
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert secret not in combined, "JPlag's stderr must not reach the job log"
    assert "exited 3" in result.stderr
    # It is preserved where the report-privacy gate already governs.
    assert (tmp_path / "work" / "jplag-stderr.log").read_text().strip().endswith(secret)


def test_submission_root_with_no_directories_is_an_error(env):
    tmp_path, jar, bindir = env
    flat = tmp_path / "flatnew"
    flat.mkdir()
    (flat / "a.R").write_text("x <- 1\n")
    write_stub_java(bindir, csv=HEADER)
    cmd = [
        sys.executable, str(SCRIPT),
        "--path", str(flat),
        "--corpus-path", str(tmp_path / "corpus"),
        "--jar", str(jar), "--jplag-sha256", sha256_of(STUB_JAR_BODY),
        "--work-dir", str(tmp_path / "work"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 2
    assert "nothing to compare" in result.stderr


# ---------------------------------------------------------------- refusals
# Each of these would otherwise print no findings and exit 0, which is exactly
# what a genuinely clean run looks like.

def test_missing_corpus_is_an_error(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER)
    result = run(tmp_path, jar, corpus=tmp_path / "absent")
    assert result.returncode == 2
    assert "not a directory" in result.stderr


def test_empty_corpus_is_an_error(env):
    tmp_path, jar, bindir = env
    (tmp_path / "empty").mkdir()
    write_stub_java(bindir, csv=HEADER)
    result = run(tmp_path, jar, corpus=tmp_path / "empty")
    assert result.returncode == 2
    assert "no submission directories" in result.stderr


def test_corpus_of_loose_files_is_an_error(env):
    """JPlag treats each CHILD DIRECTORY as a submission, so files compare to nothing."""
    tmp_path, jar, bindir = env
    flat = tmp_path / "flat"
    flat.mkdir()
    (flat / "a.R").write_text("x <- 1\n")
    write_stub_java(bindir, csv=HEADER)
    result = run(tmp_path, jar, corpus=flat)
    assert result.returncode == 2
    assert "no submission directories" in result.stderr


def test_jplag_crash_is_an_error(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=None, exit_code=3, stderr="boom\n")
    result = run(tmp_path, jar)
    assert result.returncode == 2
    assert "exited 3" in result.stderr


def test_missing_results_csv_is_an_error(env):
    """Exit 0 with no CSV means nothing was compared, not that nothing matched."""
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=None, exit_code=0)
    result = run(tmp_path, jar)
    assert result.returncode == 2
    assert "wrote no results.csv" in result.stderr


def test_empty_results_csv_is_an_error(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER)
    result = run(tmp_path, jar)
    assert result.returncode == 2
    assert "no rows" in result.stderr


def test_results_csv_missing_a_column_is_an_error(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv="submissionName1,submissionName2\na,b\n")
    result = run(tmp_path, jar)
    assert result.returncode == 2
    assert "missing column" in result.stderr


def test_unparseable_similarity_is_an_error(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER + "new/submission,corpus/alice,0.1,notanumber\n")
    result = run(tmp_path, jar)
    assert result.returncode == 2
    assert "unparseable maxSimilarity" in result.stderr


def test_digest_mismatch_refuses_and_keeps_a_caller_supplied_jar(env):
    """A jar we were merely pointed at is not ours to delete."""
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER)
    cmd = [
        sys.executable, str(SCRIPT),
        "--path", str(tmp_path / "new"),
        "--corpus-path", str(tmp_path / "corpus"),
        "--language", "rlang",
        "--jar", str(jar),
        "--jplag-sha256", "deadbeef",
        "--work-dir", str(tmp_path / "work"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 2
    assert "digest mismatch" in result.stderr
    assert jar.is_file(), "a caller-supplied jar must survive a mismatch"


def test_empty_expected_digest_is_refused(env):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER)
    cmd = [
        sys.executable, str(SCRIPT),
        "--path", str(tmp_path / "new"),
        "--corpus-path", str(tmp_path / "corpus"),
        "--jar", str(jar), "--jplag-sha256", "",
        "--work-dir", str(tmp_path / "work"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 2
    assert "unverified binary" in result.stderr


@pytest.mark.parametrize("bad", ["7", "-0.1", "abc"])
def test_threshold_out_of_range_is_an_error(env, bad):
    tmp_path, jar, bindir = env
    write_stub_java(bindir, csv=HEADER)
    result = run(tmp_path, jar, "--threshold", bad)
    assert result.returncode == 2


def test_parse_errors_are_surfaced_not_swallowed(env):
    """R's native pipe makes JPlag emit ANTLR errors; a lower bound must say so."""
    tmp_path, jar, bindir = env
    write_stub_java(
        bindir,
        csv=HEADER + "new/submission,corpus/alice,0.1,0.1\n",
        stderr="ANTLR error - line 3\nANTLR error - line 4\n",
    )
    result = run(tmp_path, jar)
    assert result.returncode == 0
    assert "2 parse error(s)" in result.stdout
