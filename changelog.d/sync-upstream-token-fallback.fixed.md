- `sync-upstream.yml` falls back to the built-in `github.token` when the
  `WORKFLOW_TOKEN` secret cannot read the repository, instead of failing at
  checkout, as `sync-shared-fragments.yml` already does (gha#1816).
