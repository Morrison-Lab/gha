- **`preview.yml` no longer fails when `quarto inspect` fails under `skip-docx`.**
  With `formats: default`, the preview ran `quarto inspect` to list the
  project's formats and stopped on its error.
  That command resolves a nested include against the including file,
  which a render does not,
  so a project that renders fine, such as `Morrison-Lab/pds`
  with its `pds -> .` symlink and `pds/_subfiles/...` includes,
  lost its preview build after the tag slid to include `skip-docx`.
  The step now warns and renders every declared format, docx included,
  when the inspect call fails.
