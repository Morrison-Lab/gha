- **Diff-scoped checks no longer scan the base branch's newer commits on a pull request** (#1007).
  `check-duplicate-roxygen`, `check-informal-definitions`, `check-merge-drops`,
  `check-new-line-breaks`, `check-one-function-per-file`, `check-orphaned-images`,
  `check-phi`, `check-typed-output` and `check-typos` diffed from the event payload's
  `pull_request.base.sha`, while their checkout is GitHub's merge ref,
  built on the base branch's current tip.
  The payload's SHA can lag that tip, so every commit the base gained in between
  counted as added by the PR (Morrison-Lab/lds#184 measured 12 extra commits and 29 extra files).
  They now diff from `HEAD^1`, the merge commit's first parent.
  In the four of these that take a `base-ref` input (`check-duplicate-roxygen`,
  `check-informal-definitions`, `check-one-function-per-file` and `check-typos`),
  a caller's explicit value still wins.
  A new `audit_pr_diff_base.py` audit in `_selftest.yml` fails any workflow
  that hands `pull_request.base.sha` to a step as a diff base.
