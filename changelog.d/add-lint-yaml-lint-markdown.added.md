- **`lint-yaml` and `lint-markdown` -- style linting for tracked YAML and
  Markdown** (#192). Two new composites-plus-reusable-workflows, following the
  existing `check-*` pattern: `lint-yaml` runs
  [`yamllint`](https://yamllint.readthedocs.io/) with a bundled default
  config, and `lint-markdown` runs
  [`markdownlint-cli2`](https://github.com/DavidAnson/markdownlint-cli2) with
  a bundled default config. Both bundled configs are tuned to this
  ecosystem's actual style (e.g. disabling `line-length`/`MD013`, since
  workflow prompt blocks and the lab manual's semantic-line-break prose
  convention both routinely exceed a fixed width) rather than shipping an
  unmodified upstream default. Each also ships a companion check that flags
  `run:` script blocks (YAML) or fenced code blocks (Markdown) longer than a
  configurable line threshold (default 150) as decomposition candidates,
  matching the [lab manual's](https://ucd-serg.github.io/lab-manual/coding-practices.html)
  `<150`-line function-length heuristic; this check defaults to warn-only,
  since the manual documents that heuristic as "a provisional heuristic
  trigger to reassess decomposition, not a hard constraint." Ships at `@v2`
  (too new for the frozen `@v1` tag), like `test-coverage`/`check-equation-renders`. See
  `examples/lint-yaml.yml` and `examples/lint-markdown.yml` for the caller
  stubs.
