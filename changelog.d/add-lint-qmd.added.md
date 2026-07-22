Add `lint-qmd` composite action and reusable workflow for linting the prose
sections of `.qmd` Quarto files with markdownlint. Quarto code chunks are
replaced with blank lines before linting (preserving line numbers); YAML front
matter is skipped natively by markdownlint. Default config: MD013 (line length,
default 80 chars, configurable via `max-line-length` input), MD022/MD024/MD031
and the full markdownlint ruleset; MD033, MD041, and MD060 off.
