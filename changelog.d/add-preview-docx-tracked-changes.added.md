- **`preview`: generate Word DOCX with tracked changes against the published render**
  ([#762](https://github.com/Morrison-Lab/gha/issues/762)).
  Set `docx-tracked-changes: true` and the composite compares rendered DOCX files
  against the published versions on `gh-pages`,
  producing `-tracked-changes.docx` files carrying Word revision markup.
  Exposes `docx-status`, `docx-skip-reason`, `docx-tracked-changes-files`, and
  `any-docx-changed` as outputs.
  `docx-tracked-changes-glob` (default `chapters/*.docx`), `deployed-branch`, and
  `deployed-subdir` tune it.
  Ported from `ucdavis/win` and rewritten to this repo's fail-fast bar:
  `python-docx` is a strict dependency rather than silently degrading to copying unchanged files,
  and a missing `gh-pages` branch or zero published DOCX files is a stated skip.
