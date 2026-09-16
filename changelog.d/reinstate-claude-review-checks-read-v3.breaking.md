- **`claude-code-review`'s `claude-review` job requests `checks: read` again**
  (#833).
  #832 dropped the scope to stop `@v2` startup-failing every caller
  that had not yet granted it (#831);
  this reinstates it as a major-tag bump rather than a slide of an existing
  tag.
  A caller still on `@v2` is unaffected,
  and a caller already granting `checks: read`
  (the README, `examples/claude-code-review.yml`, and website docs have
  asked for it since #832)
  moves to this tag at no cost.
  Reinstating the scope is what lets the reviewer read
  `GET .../commits/{ref}/check-runs` again,
  so it can assert a genuinely clean CI/check-run status
  instead of reporting an unverifiable diff as blocked
  (ucdavis/bcs#964, #829).
