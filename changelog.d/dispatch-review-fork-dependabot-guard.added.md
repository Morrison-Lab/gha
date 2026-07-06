- **`claude-code-review`'s dispatched (`workflow_dispatch`) review path now
  guards against fork and Dependabot PRs** (#235). The automatic
  `pull_request` path already skips fork/Dependabot/draft PRs using the
  triggering event's own payload; the dispatched path had no equivalent
  check and ran unconditionally. A new `gather-context` step resolves the
  dispatched PR's cross-repository/author status via `gh pr view` and skips
  the review (gray, not a failure) when it's a fork or Dependabot PR. Both
  real dispatch entry points (`claude.yml`'s trusted-author gate, the
  `/review`-comment path's collaborator check) were already trust-gated
  upstream of this, so it's defense-in-depth against a mistaken manual
  dispatch, not a fix for a demonstrated exploit.
