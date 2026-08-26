- **New `check-formatting` capability** (composite action +
  `check-formatting.yml` reusable workflow)
  ([#333](https://github.com/Morrison-Lab/gha/issues/333)).
  Runs `air format --check -- <path>` after
  [`posit-dev/setup-air`](https://github.com/posit-dev/setup-air)
  installs a pinned Air release.
  Air is Posit's R formatter, a Rust binary, so there is no R session
  to start.
  Complements `lint-changed-lines.yml`: Air settles layout, lintr
  decides the rest of R style.
  Check-only -- it never rewrites the caller's branch.
  The Air version is an input (default `0.11.0`, the pin
  `IndrajeetPatil/workflows` locked on 2026-08-26; #333 cited `0.9.0`,
  which that workflow has since bumped), and `posit-dev/setup-air` is
  SHA-pinned with the exact release in the comment (`v1.0.1`), not the
  floating `# v1` tag upstream uses.
  Derived from
  [`IndrajeetPatil/workflows`](https://github.com/IndrajeetPatil/workflows)
  `check-formatting.yaml` (MIT).
  Adopting this in a consumer is a separate reformat commit
  (commit an `air.toml` first, even empty); this change lands the
  capability only.
