- **`preview.yml` renders docx again when `docx-tracked-changes: true`.**
  Since `skip-docx` became the default (gha#1055),
  a caller that turned on tracked changes rendered no Word files,
  and the "Create DOCX tracked changes" step failed on every content PR
  because it had nothing to compare (gha#1059, seen on Morrison-Lab/psc#13).
  `docx-tracked-changes: true` now keeps docx in the preview render,
  with a notice that `skip-docx` was not applied,
  so such callers no longer need to set `skip-docx: false` themselves.
