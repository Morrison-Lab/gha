- **`@claude review` dispatch survives a skipped PR checkout** (#418). When the
  `Checkout PR branch` step is skipped after an upstream setup failure (e.g.
  `setup-renv`), `claude.yml` now resolves the PR head branch via the GitHub API
  so all three review-dispatch sites (the trigger comment, a late `@claude
  review` comment, and the post-push re-request) still dispatch instead of
  silently dropping the review.
