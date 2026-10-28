- `check-bare-yes-no`:
  add a diff-scoped composite action and reusable workflow
  that fails a pull request adding a solution paragraph (inside a `#sol-` div or a `.sol`, `.solution` or `.answer` div)
  that opens with a bare "Yes." or "No." (Ezra, 2026-10-28;
  [psw](https://github.com/Morrison-Lab/psw) teaching chapter).
  An answer says what it means in the question's terms, as in "No: it's not possible that the advanced network has a test error of 0.25."
  Code fences and comments are skipped, an untouched answer keeps its form,
  and a run with no base to diff against is skipped; `whole-tree` measures a corpus.
  It fails by default (`fail: false` warns).
