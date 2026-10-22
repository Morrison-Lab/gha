- `check-multipart-exercises`:
  add a diff-scoped composite action and reusable workflow that fails a pull request
  adding or revising an exercise div (id `exr-...`) that holds more than one part
  ([#1156](https://github.com/Morrison-Lab/gha/issues/1156)).
  It flags two or more list items in one marker style (`(a)`/`(b)`, `a.`, `(i)`, `1.`, bare or bolded)
  and inline "(a) ... (b)" parts; math, code, comments and bullet lists do not count,
  and `<!-- multipart-ok: reason -->` exempts an exercise, such as a single-choice question.
  Like `check-one-div-per-subfile` it scopes to touched exercises, so existing ones are never reflagged,
  and skips rather than scanning the whole tree with no base to diff against;
  unlike it, it fails by default (`fail: false` warns), because the rule is settled.
