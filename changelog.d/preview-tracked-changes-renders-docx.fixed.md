- **`preview.yml` renders docx again when `docx-tracked-changes: true`.**
  Since `skip-docx` became the default (gha#1055),
  a caller that turned on tracked changes rendered no Word files,
  and the "Create DOCX tracked changes" step failed on every content PR
  because it had nothing to compare (gha#1059, seen on Morrison-Lab/psc#13).
  `docx-tracked-changes: true` now renders docx as a `preview:docx` label would,
  under an explicit list naming docx and the empty default
  (`formats: default` already renders every declared format since gha#1061),
  so such callers no longer need to set `skip-docx: false` themselves.
  An explicit `formats` list that leaves docx out is still rendered as written.
