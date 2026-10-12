- **`preview.yml` no longer fails with `Unknown format html,pdf,revealjs`
  under `formats: default`.**
  The `skip-docx` default passed the project's formats to
  `quarto render --to` as one comma-joined string, which Quarto rejects,
  so every preview of a project declaring more than one non-docx format
  failed at the render step.
  A bare render now renders every declared format again, and `skip-docx`
  applies to an explicit `formats` list only.
