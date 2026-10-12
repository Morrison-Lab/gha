- **`skip-docx` input on `preview.yml`**, defaulting to `true`, so a PR
  preview leaves Word (docx) out of the render and builds faster, while the
  publish build still renders it.
  An explicit `formats` list drops `docx`;
  `formats: default` is a bare render and still renders every declared
  format, because `quarto render --to` takes one format.
  A PR labelled `preview:docx` opts back in, and `skip-docx: false` restores
  the old behavior.
  The input is new, so no caller breaks at the call gate, but its default
  changes what previews render:
  callers that render docx in previews today lose it once the tag they pin
  slides to include this change (`v3` for Morrison-Lab/lds,
  `v2` for callers following `examples/preview.yml`),
  and set `skip-docx: false` to keep it.
  The default is deliberate, requested by the maintainer for every
  Morrison-Lab repo, and preferred over a major bump.
