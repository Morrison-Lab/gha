- **New `check-merge-drops` capability** (composite action +
  `check-merge-drops.yml` reusable workflow, at `@v3`)
  ([#958](https://github.com/Morrison-Lab/gha/issues/958)).
  For every merge commit in a PR (or push),
  it reports lines either side added since the merge base
  that appear nowhere in the merge's tree:
  the signature of a conflict resolved by keeping one side of a whole file.
  Moved, rewrapped and reworded content is not reported.
  Warn-only by default (`fail: false`), with the report in the job summary.
