- `check-unexplained-contrasts`:
  fail by default instead of warning (gha#1477).
  The "is not a/an" phrase is dropped from the trigger list,
  since most plain statements use it.
  A whole-tree run over lds, mds, pds, sds, and psw was sampled,
  and every remaining hit was a real contrast.
  The `fail` input default changes from `false` to `true`, in the action and the reusable workflow.
  A caller that wants warnings sets `fail: false`.
