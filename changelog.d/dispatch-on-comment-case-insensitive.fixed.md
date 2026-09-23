- **`claude-review.yml`'s `dispatch-on-comment` job now matches `/review` case-insensitively** (#908).
  Setting `shopt -s nocasematch` aligns the in-step standalone command regex with GitHub Actions'
  case-insensitive `startsWith` pre-filter, preventing capitalized commands like `/Review` from
  skipping silently without dispatching a review.
