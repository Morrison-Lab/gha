- **`preview.yml`** --
  takes `post-build-command`, a shell command run in the build job after the site is rendered,
  so checks that read the rendered site no longer wait for a runner a second time
  in a separate `workflow_run` workflow.
  `post-build-continue-on-error: true` turns its failure into a warning.
