- **New `check-orphaned-images` capability** (#960).
  Reports tracked images that no tracked source file (`.qmd`, `.md`, `.yml`,
  `.scss`, `.lua`, `.html`, and others) names.
  Warn-only by default, with `paths-ignore` and an `added-only` mode that
  reports only the images a pull request adds.
  Also a default-on, warn-only step in `check-quarto-website`
  (`orphaned-images-fail` makes it blocking).
