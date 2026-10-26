- **`scripts/register-self-hosted-runner.sh`** --
  accepts a runner group whose visibility is `all` when `allows_public_repositories` is exactly `false`,
  because "all" then means every non-public repository, as in the group the lab already uses.
  It still refuses a group that allows public repositories,
  or whose setting is missing or not a boolean.
  The decision is in `scripts/runner-group-is-private.sh`, with offline tests.
