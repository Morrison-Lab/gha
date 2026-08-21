- **New `spellcheck` capability** (composite action + `spellcheck.yml`
  reusable workflow) (#257, #555).
  Spellchecks an R package's prose --
  `DESCRIPTION`'s `Title` and `Description`, `man/*.Rd`, vignette sources, and
  root `README`/`NEWS`/`CHANGES`/`index` Markdown --
  with the [{spelling}](https://docs.ropensci.org/spelling/) package,
  wrapping
  [`insightsengineering/r-spellcheck-action`](https://github.com/insightsengineering/r-spellcheck-action).
  The package's own `inst/WORDLIST` stays the accepted vocabulary,
  so a repo replacing its bespoke `check-spelling.yaml` migrates nothing:
  that file is {spelling}'s own format.
  R comes from `r-lib/actions/setup-r` rather than a `rocker` container,
  matching every other R capability here,
  and {spelling} is installed through `setup-r-dependencies` so it arrives as
  a cached RSPM binary
  instead of compiling {hunspell} from CRAN source on every run,
  which is what the upstream action's own installer would do.
  Only {spelling} is resolved, not the consumer package's dependency tree,
  since `spell_check_package()` reads a package's files without loading it.
  Three upstream quirks are handled rather than papered over (#556).
  A lone glob in `exclude` used to exclude only its first match --
  upstream expands the input unquoted in a shell and then reads only the
  first argument --
  so the composite normalizes the value into a single unexpandable word
  and lets R's own `Sys.glob()` match;
  an entry containing whitespace is rejected rather than silently mangled.
  The other two are documented on the reference page:
  `exclude` deletes the files it matches and never restores them,
  and a count of exactly 256 misspelled words exits `0`.
  Prose outside an R package -- a Quarto site's non-vignette pages,
  `CONTRIBUTING.md`, and any repo that is not a package at all --
  is still unchecked; #557 tracks that separately.
