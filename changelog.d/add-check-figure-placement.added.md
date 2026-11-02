- `check-figure-placement`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags a figure a pull request adds
  when no sentence on its page cites it with `@fig-id`,
  or when it sits directly after an example, exercise or solution div instead of inside it (Ezra, 2026-11-02).
  Like `check-exm-figures` it scopes to touched figures and skips rather than scanning the whole tree
  when there is no base to diff against.
  `<!-- figure-placement: allow -->` exempts a figure that several examples share.
