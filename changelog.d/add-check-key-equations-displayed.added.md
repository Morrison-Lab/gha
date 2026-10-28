- `check-key-equations-displayed`:
  add a diff-scoped composite action and reusable workflow
  that fails a pull request adding an inline equation in a proof that should be in display math
  (Ezra, 2026-10-28, [psw#400](https://github.com/Morrison-Lab/psw/pull/400)).
  A key equation is a theorem's conclusion, an equation a proof builds toward, or one a later step refers to.
  This is a partial heuristic with two signals, both inside a proof div:
  an inline equation that restates a displayed equation of the same file (the parent theorem),
  and an inline equation that ends a sentence after "yields", "gives", "implies", "so", "thus", "hence", "therefore" or "forces",
  or before a sentence opening with "So", "Hence", "Therefore" or "Thus".
  It cannot tell a key equation from a routine one,
  so it misses a key equation with no cue word and may flag a minor step;
  put `<!-- inline-ok -->` on a line to accept an inline equation.
  Code fences and comments are skipped, an untouched line keeps its form,
  and a run with no base to diff against is skipped.
  `whole-tree` measures a corpus.
  It fails by default (`fail: false` warns).
