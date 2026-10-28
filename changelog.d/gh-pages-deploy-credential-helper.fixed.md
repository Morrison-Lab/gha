- **Deploys to `gh-pages` no longer fail on a self-hosted runner's stale git
  credential cache.**
  The deploy jobs in `preview-deploy`, `quarto-publish` and
  `cleanup-pr-previews` run on `inputs.runs-on`, which can be a self-hosted
  runner whose user's `~/.gitconfig` sets `credential.helper=cache`.
  With that home on a network filesystem the cache daemon's socket can go
  stale, and the push died with
  `fatal: unable to connect to cache daemon: Stale file handle`
  (Morrison-Lab/lds run 40653511896, which passed on re-run).
  Each job now sets an empty `credential.helper` through
  `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0`,
  which resets git's helper list for that job only;
  the push authenticates with the job token, not a helper.
