- **`CI_RUNNER` applies only when the triggering repository is private.**
  A job's runner is now
  `inputs.runs-on || (github.event.repository.private && vars.CI_RUNNER) || 'ubuntu-latest'`.
  A pull request in a public repository (`repository.private` is `false`)
  therefore stays on a GitHub-hosted runner even if `CI_RUNNER` is set at the
  repository or organization level, so fork code never reaches a self-hosted
  runner through this variable.
  An event whose payload carries no `repository` object also stays hosted,
  the safe direction.
  `audit_ci_runner_guard.py` fails any reusable-workflow `runs-on` that reads
  `vars.CI_RUNNER` without this guard.
