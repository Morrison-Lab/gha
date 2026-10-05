- **`claude-code-review` no longer counts default-branch commits merged into a
  PR as unreviewed PR commits** (#965, #992). A PR that merged `main` after a
  reviewed round carried other PRs' squash merges into the incremental range.
  A truthful "no new content" verdict then failed `require-clean-verdict` as
  `unreviewed-commits-skipped`. That round stamped no `Reviewed commit:`
  boundary, and the range only grew, so the PR could never go green (observed
  on Morrison-Lab/lds#369). `compute-incremental-range.sh` now takes the base
  branch and the default branch (new fourth and fifth arguments, or `BASE_REF`
  and `DEFAULT_BRANCH`). It counts `<prior>..<head> --not <base>` only when
  the two are equal, and lists the base's commits separately. The workflow
  passes both from the event, and reads them from the API on
  `workflow_dispatch`. A base that is not the default branch keeps the full
  count, since a PR author can retarget at a branch of their own without
  re-running the review. An empty, malformed or unfetchable base, or a base
  that never meets the PR's history within `DEEPEN_MAX`, also keeps the full
  count, so the guard still fails closed.
- **Merges stay counted when their result differs from git's own merge.**
  Once base commits are excluded, each merge in the range is compared with
  `git show --remerge-diff` (git 2.36 or later). A merge whose result differs
  in any file is counted as unreviewed and listed with those files. That
  covers a conflict resolved by taking one side, and a base change reverted
  to the PR's old copy. A merge whose re-merge cannot be computed is counted
  as well.
- **`compute-incremental-range.sh` no longer undercounts a range on a shallow
  checkout.** It used to stop deepening once the prior commit was reachable,
  which could leave commits brought in by a merge beyond the shallow boundary
  and uncounted. It now deepens until no commit in the range is a boundary.
  If `DEEPEN_MAX` stops it first, it excludes nothing, counts the visible part
  of the range (at least 1), and tells the reviewer the range is incomplete.
