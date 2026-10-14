- **`claude-code-review.yml` has a `submodule-paths` input, and the
  `checkout-submodules` composite a matching `paths` input**, so a caller can
  check out only the submodules the reviewer needs.
  A repository with a private submodule beside a public one (for example
  `latex-macros`) can now set `checkout-submodules: true` and
  `submodule-paths: latex-macros` without a `SUBMODULES_TOKEN` that reads the
  private one.
  Empty keeps today's behavior, every submodule.
  The composite calls it through a new script with offline tests.
  The workflow calls the composite at its own major tag, so the input takes
  effect once that tag slides.
