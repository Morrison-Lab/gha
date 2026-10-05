- `claude-code-review`: commits that reach a PR branch only by merging its base
  branch are no longer counted as unreviewed PR commits. `compute-incremental-range.sh`
  takes the base branch (new fourth argument, or `BASE_REF`), fetches it, and
  counts `<prior>..<head> --not <base>`, listing the base's commits separately as
  not this PR's content. Before, a PR that merged `main` after a reviewed round
  carried other PRs' squash merges into the range; a truthful "no new content"
  verdict then failed `require-clean-verdict` as `unreviewed-commits-skipped`,
  that round stamped no `Reviewed commit:` boundary, and the range only grew, so
  the PR could never go green (observed on Morrison-Lab/lds#369). Genuine PR
  commits are still counted, and an empty, malformed or unfetchable base ref
  keeps the full count, so the #992 guard (#965) still fails closed.
