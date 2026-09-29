- `claude-code-review`: `compute-incremental-range.sh` now accepts explicit
  PR head SHA and count-file parameters, ignores restated clean reviews and
  skipped review comments when selecting the prior reviewed commit, and uses
  `git log --no-merges` and `git rev-list --count --no-merges` to track
  unreviewed commits (#965).
  When restated review comments were treated as genuine reviewed bounds,
  a round that merely repeated a clean verdict moved the incremental range
  forward over unreviewed commits.
  Filtering out skipped and restated comments preserves the genuine lower bound.

- `claude-code-review`: `classify-review-verdict.sh` now fails closed to
  `verdict=unreviewed-commits-skipped` (`clean=false`) when unreviewed commits
  exist and a review declares "no new diff" or posts a skipped verdict (#965).
  `pack-review-payload` and `claude-code-review.yml` forward the unreviewed
  commit count from `compute-incremental-range.sh` through `payload.json` into
  `classify-review-verdict`.
  `classify-review-verdict.sh` compares the review's claimed commit SHA against
  the expected PR head SHA when unreviewed commits exist, structurally failing
  closed if an older commit was evaluated, and evaluates verdict-section
  stale-claim checks across all core trigger patterns even when the commit
  matches (failing closed if a stale claim is made over unreviewed commits).
  `compute-incremental-range.sh` checks the full stripped comment body to
  prevent stale comments with pre-verdict no-diff claims from zeroing out the
  unreviewed count.
  Both scripts strip fences, blockquotes, HTML comments, code spans, and
  quoted strings (single, double, and curly quotes), qualify trigger patterns
  with determiner and noun lookaround guards, and tighten "no commits have
  landed" with trailing qualifier negative lookaheads so descriptive mentions
  in plain prose do not trigger false positives.
