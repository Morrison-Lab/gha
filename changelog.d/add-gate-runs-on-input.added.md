- **`gate-runs-on` input on `claude-code-review.yml`**, empty by default,
  which keeps the existing `runs-on` / `CI_RUNNER` / `ubuntu-latest` chain
  so existing callers are unaffected.
  It sets the runner for the five short jobs that only call the GitHub API or
  report a result (`preempt-previous`, `gather-context`, `find-fallback-verdict`,
  `require-review` and `require-clean-verdict`).
  A caller whose `runs-on` is a busy self-hosted pool can send them to a
  hosted runner, so the merge gate does not queue behind long jobs
  (one such caller waited about an hour for two of them).
