- **`claude-code-review`'s `require-review` gate no longer reports green when
  no review ran** (#434).
  A PR that edits the caller's own review workflow trips the self-review skip
  guard, which is correct --- `claude-code-action` requires that file to match
  the default branch, so it cannot review such a PR.
  But the gate reported the same green for that skip as for a clean review, so
  an unreviewed PR was indistinguishable from a reviewed one on a required
  check.
  The review job now surfaces the guard's decision as a `self_mod` output, the
  gate reports a gray *skipped* rather than green, and the review job posts a
  PR comment saying that no review ran, that no re-run will change that, and
  that a self-review or human review is needed.
  `require-review`'s semantics are now documented on the reference page: green
  attests that a reviewer ran, never that one approved.
