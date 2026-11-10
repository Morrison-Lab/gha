- `check-removed-content`:
  add a diff-scoped composite action, and a reusable workflow,
  that fails a PR removing prose sentences that reappear nowhere among its added lines
  (Ezra, 2026-11-09, review of pull request 2032 in the private `lds` repository, [gha#1791](https://github.com/Morrison-Lab/gha/issues/1791)).
  Sentences are matched on normalized word trigrams, so a move, a reflow, or a light rewording passes.
  `removed-content-ok: reason` in the PR body opts out, and a deleted file named in the body is exempt.
  `fail: false` gives warnings only.
