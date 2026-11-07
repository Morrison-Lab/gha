- `check-def-wiktionary`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags a `#def-` div
  whose first bolded defined term is not linked to its Wiktionary entry when one exists,
  and a Wiktionary link to a page that does not exist
  ([gha#1558](https://github.com/Morrison-Lab/gha/issues/1558), Ezra, 2026-11-06).
  The terms are the comma-separated names in the div title.
  A lookup uses the MediaWiki API,
  and a network failure skips the definition with a warning instead of failing the run.
  `<!-- wiktionary-link: allow -->` exempts a definition.
