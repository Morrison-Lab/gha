- **`condor-batch` composite runs bundled steps on the cluster**
  ([#1381](https://github.com/Morrison-Lab/gha/issues/1381)).
  It copies the checkout to the cluster home and runs the given steps as one HTCondor job.
  It runs them on the runner instead when the key is absent, there are fewer than two steps (exit 71), or the cluster job does not run normally (exit 70, including a failed ssh).
  A step that fails on the cluster fails the job and is not retried locally: a step exit of 70, 71 or 255 is reported as 1, so only infrastructure failures use those codes.
  This repository's `_selftest.yml` uses it for three slow offline suites when `CI_RUNNER` is set in a private repository, so it does not run in this public repository.
  It is internal for now, with no reference page or caller stub.
