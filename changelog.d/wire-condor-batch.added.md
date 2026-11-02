- **`condor-batch` composite runs bundled steps on the cluster**
  ([#1381](https://github.com/Morrison-Lab/gha/issues/1381)).
  It copies the checkout to the cluster home and runs the given steps as one HTCondor job.
  It runs them on the runner instead when the key is absent, there are fewer than two steps, or the cluster job does not run normally.
  A step that fails on the cluster fails the job and is not retried locally.
  This repository's `_selftest.yml` uses it for three slow offline suites when `CI_RUNNER` is set.
  It is internal for now, with no reference page or caller stub.
