- `sync-shared-fragments.yml` falls back to the built-in `github.token` when the
  `WORKFLOW_TOKEN` secret cannot read the repository, instead of failing at
  checkout (gha#1807).
