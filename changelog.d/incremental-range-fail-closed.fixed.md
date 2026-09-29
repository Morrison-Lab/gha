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
  Both scripts strip fences, blockquotes, HTML comments, code spans, and
  quoted strings (single, double, and curly quotes) before evaluating no-diff
  patterns, preventing false positives on quoted diffs, prompt instructions,
  and reviews that quote or discuss trigger phrases in prose.
