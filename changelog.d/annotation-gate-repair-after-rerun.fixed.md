- **`annotation-gate-run.yml` gates again a commit whose Claude review re-run never started a gate** (gha#2077).
  A finished re-run of the review after its 429 sent no `workflow_run` event, so the commit kept the first attempt's red check until a manual dispatch.
  A gate that did not defer now also gates again each commit where a run of `repair-workflows` (default `Claude Code Review`) finished in the last `repair-hours` (default 3) after its newest check.
  It never fails the gate that called it.
