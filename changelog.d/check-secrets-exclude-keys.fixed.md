- **`check-secrets` no longer reads a BibTeX key passed to gha's own
  `exclude-keys` or `bib-exclude-keys` input as a credential** (#2113).
  gitleaks' default `generic-api-key` rule took a key such as
  `abramson2021algebra` on that line for a credential assignment,
  so every csci201 push to `main` failed the scan.
  The generated config now always carries a line-targeted allowlist anchored to
  those two YAML keys, so no caller needs its own `.gitleaksignore` entry.
