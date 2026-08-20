- **`altdoc-multiversion-docs.yml`'s PR-build concurrency group is now keyed
  by PR number, not `github.run_id`** (#306, #311).
  Keying by `run_id` put every run in its own group, so `cancel-in-progress`
  could never fire for a PR's own superseded runs: several full renders
  raced to deploy to the same `pr-preview/pr-<N>/` path on `gh-pages`,
  sometimes leaving it mid-rebase
  (`JamesIves/github-pages-deploy-action` add/add conflicts) and sometimes
  letting an older commit's run finish last and overwrite a newer commit's
  preview.
  A newer push to the same PR now cancels that PR's still-running build,
  while different PRs continue to build concurrently as before.
