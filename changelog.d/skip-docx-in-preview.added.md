- **`skip-docx` input on `preview.yml`**, defaulting to `true`, so a PR
  preview leaves Word (docx) out of the render and builds faster, while the
  publish build still renders it.
  Under `formats: default` the preview renders the project's declared
  formats minus docx, read with `quarto inspect`, in one `quarto render --to`
  call so every format keeps its supporting files; an explicit `formats`
  list drops `docx` the same way.
  A PR labelled `preview:docx` opts back in, and `skip-docx: false` restores
  the old behavior.
  This changes an optional input's default for callers that render docx in
  previews today, so those callers get no docx in their previews once the
  `v3` tag slides.
