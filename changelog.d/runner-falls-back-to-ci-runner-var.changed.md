- **Every reusable workflow now runs on the caller's `CI_RUNNER` variable
  when the caller passes no `runs-on`.**
  A job's runner is `inputs.runs-on`, else the caller's `vars.CI_RUNNER`,
  else `ubuntu-latest`, so a private repository that sets `CI_RUNNER` to its
  self-hosted label moves every gha job off GitHub-hosted minutes without
  editing each caller.
  The `runs-on` input defaults to the empty string instead of
  `ubuntu-latest`; passing `ubuntu-latest` explicitly still works.
  Reusable workflows that hardcoded `ubuntu-latest` (about 45 jobs, among
  them `annotation-gate`, the `check-*` workflows, `claude-code-review`
  and `report-failure`) read `CI_RUNNER` too, and `claude.yml`'s
  `mention-filter` job does as well, so a quoted mention in a private
  repository no longer needs hosted minutes.
  A public repository must leave `CI_RUNNER` unset: a fork pull request can
  run arbitrary code on a self-hosted runner.
