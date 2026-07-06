- **`check-news.yml` gains a `no-changelog-label` input** (#143, #237). The
  wrapped `UCD-SERG/changelog-check-action`'s own skip-label check is hardcoded
  to the string `no changelog` (with a space) and reads PR label context from
  inside a nested composite-action step. `check-news.yml` now does the label
  check itself, before ever invoking the composite, via a configurable
  `no-changelog-label` input (default `no-changelog`, matching the hyphenated
  convention already used by at least one consumer). Set it to an empty string
  to disable the escape hatch entirely.
