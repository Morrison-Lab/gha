- `check-exercise-question-paragraph`:
  add a diff-scoped composite action and reusable workflow
  that fails a PR adding a paragraph of an exercise (`#exr-` div) that mixes scenario information with the instruction or question
  (Ezra, 2026-11-02, [psw#448](https://github.com/Morrison-Lab/psw/pull/448)).
  A task sentence ends with a question mark or starts with an imperative task verb such as Show, Find or Estimate;
  every other prose sentence is scenario.
  Solutions, hints, code, display math, lists and comments are not examined,
  and `<!-- question-paragraph-ok: reason -->` exempts an exercise.
  `fail: false` gives warnings only, and `whole-tree` measures a corpus.
