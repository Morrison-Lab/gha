- `claude-code-review.yml` rewrites a made-up prior-verdict link,
  such as `#issuecomment-placeholder`, before posting the review (gha#1766).
  A real comment ID is digits,
  so a link whose ID starts with a letter now points to the newest earlier verdict comment,
  or to the pull request when there is none.
  The prompt already asked for the real URL (gha#1039),
  but a review on 2026-11-09 still wrote the placeholder.
