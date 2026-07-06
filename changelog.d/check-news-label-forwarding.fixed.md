- **`check-news.yml` gains a `no-changelog-label` input** (#143, #237). The
  wrapped `UCD-SERG/changelog-check-action`'s own skip-label check is hardcoded
  to the literal string `no changelog` (with a space) and not configurable —
  at least one consumer (`UCD-SERG/serocalculator`) documents and uses
  `no-changelog` (hyphen) instead, so the composite's own escape hatch never
  fired for that PR label. `check-news.yml` now does its own label check,
  before ever invoking the composite, via a configurable `no-changelog-label`
  input (default `no-changelog`). Setting it to an empty string disables this
  workflow's own escape hatch, but not the wrapped composite's separate,
  unconditional recognition of its own hardcoded `no changelog` (space) label
  — that's baked into `UCD-SERG/changelog-check-action` itself and isn't
  controlled by this input.
