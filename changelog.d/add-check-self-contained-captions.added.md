- `check-self-contained-captions`:
  add a diff-scoped, blocking composite action and reusable workflow
  that flags a figure or table caption
  whose first sentence only points to another div,
  such as "The symmetry of @exm-x."
  ([#1237](https://github.com/Morrison-Lab/gha/issues/1237)).
  A trailing ", as in @x" is support,
  and `<!-- caption-ref: reason -->` inside the div is the justified exception.
  Like `check-exm-figures` it scopes to added lines,
  skips when there is no base to diff against,
  and has a `whole-tree` mode.
