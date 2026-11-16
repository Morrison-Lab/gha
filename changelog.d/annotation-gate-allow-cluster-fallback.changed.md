- `annotation-gate` now allows by default the notice `condor-batch` emits when it reruns the steps on the runner after the cluster job did not run normally.
  A step that then fails on the runner still fails its job.
  The other fallback reasons (no cluster key, too few steps) stay gated (gha#2039).
