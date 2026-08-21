- `classify-review-delivery.sh` and the `install-gha-scripts` composite decide
  whether a dispatched review actually produced a verdict, by looking for the
  agent's own no-verdict marker inside a PR comment naming that run.
  A run conclusion of `success` is not the same as "produced a verdict":
  `claude-code-review.yml` deliberately succeeds on a graceful quota skip and
  surfaces the skip through a comment instead.
  Nothing calls this yet.
  `ai-code-review.yml` cannot, until `v2` advances past this merge, since a new
  composite action cannot gain its first `@v2` caller in the PR that introduces
  it (#569).
