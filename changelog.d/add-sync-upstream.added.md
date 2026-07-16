- **New `sync-upstream` reusable workflow** (#254). Periodically merges an
  upstream repository's branch into a fork and opens a PR when the merge brings
  changes — for a fork that tracks another project (e.g. `d-morrison/altdoc`
  tracking `etiennebacher/altdoc`). The fork's own changes are preserved; on a
  conflict the PR carries the conflict markers for manual resolution (or set
  `fail-on-conflict` to fail the run instead). Reuses the `open-sync-pr`
  composite, alongside `bump-submodule` and `sync-shared-fragments`.
