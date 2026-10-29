- **`CI_RUNNER` applies only when the triggering repository is not public.**
  A job's runner is now
  `inputs.runs-on || (github.event.repository.private != false && vars.CI_RUNNER) || 'ubuntu-latest'`.
  A pull request in a public repository (`repository.private` is `false`)
  therefore stays on a GitHub-hosted runner even if `CI_RUNNER` is set at the
  repository or organization level, so fork code never reaches a self-hosted
  runner through this variable.
  Events with no repository payload (`schedule`, some `workflow_dispatch`
  runs) still use `CI_RUNNER`; they run default-branch code only.
