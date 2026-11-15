- `preview.yml`: a label event for a label the build does not read, such as `ai-authored`, now gets a concurrency group of its own, so it no longer cancels the PR's running preview build (gha#1998).
  `preview:runner`, which the build's `runs-on` reads, joins the build-label list, so adding or removing it re-renders on the chosen runner.
  `run-preview-workflow-tests.py` pins that the job `if:` and the concurrency group name the same labels.
  Callers can drop a workflow-level `concurrency` group that copies the list (Morrison-Lab/lds#2490).
