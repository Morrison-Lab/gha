- **A closed same-repo PR's preview is removed without a preview build job**
  ([gha#1528](https://github.com/Morrison-Lab/gha/issues/1528)).
  `preview.yml` no longer runs its build job for a `closed` event on a PR from the same repository,
  which waited for a pool runner only to upload a "remove" artifact.
  The gate in `preview-deploy.yml` (now granted `pull-requests: read`) finds the run's PR in the `workflow_run` event,
  and when no artifact was uploaded and that PR is closed, the deploy job removes the preview.
  A fork PR still builds on close, because `workflow_run.pull_requests` is empty for fork runs.
