- **A closed PR's preview is removed without a preview build job**
  ([gha#1528](https://github.com/Morrison-Lab/gha/issues/1528)).
  `preview.yml` no longer runs its build job for a `closed` event,
  which waited for a pool runner only to upload a "remove" artifact.
  The gate in `preview-deploy.yml` now finds the run's PR in the `workflow_run` event,
  and when no artifact was uploaded and that PR is closed, the deploy job removes the preview.
  A skipped `labeled` event for an unrecognized label already skipped the build job, and still does.
