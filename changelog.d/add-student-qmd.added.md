- **New `student-qmd` capability** (composite `student-qmd/` plus
  reusable `student-qmd.yml`,
  [gha#922](https://github.com/Morrison-Lab/gha/issues/922)).
  For a course whose assessment sources keep each answer beside its question
  in a `.sol` div,
  it writes a self-contained student `.qmd` per source:
  includes inlined the way Quarto resolves them,
  and answer-key-only divs, HTML comments and whole-line front-matter
  comments removed.
  It then checks each written file against its source with Quarto's own
  Pandoc,
  refuses a source whose answer sits in a misnamed div (`.solution`,
  `.answer`, ...) the assign filter would pass through,
  or in a raw HTML `<div>` the writer cannot remove,
  and renders each file alone in an empty directory.
  Ported from `Morrison-Lab/mlg`'s `make_student_qmd.py` and the
  `--student-qmd` half of `check_student_copy.py` (mlg#22),
  with `Morrison-Lab/epi204`'s `quarto render` chunk removal as an option;
  every mlg#22 negative control is a pytest case.
  Ships at `@v2` only.
