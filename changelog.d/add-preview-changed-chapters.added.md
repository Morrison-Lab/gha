- **`preview`: detect the chapters that differ from the published render**
  ([#760](https://github.com/Morrison-Lab/gha/issues/760)).
  Set `detect-changed-chapters: true` and the composite compares this run's
  render against the copy currently on `gh-pages`,
  exposing `changed-chapters`, `any-changed`, `detection-status`, and
  `skip-reason` as outputs.
  Set `changed-chapters-banner: true` and the preview home page gains a banner
  linking each changed page.
  Both default off, so no existing consumer changes behaviour.
  `changed-chapters-glob`, `deployed-branch`, `deployed-subdir`,
  `banner-index`, and `changed-chapters-normalize-patterns` tune it.
  The comparison is against the deployed render rather than the source diff,
  which is what makes it usable for a site whose pages depend on shared code.
  Ported from `ucdavis/win` and rewritten to this repo's fail-fast bar:
  a missing `gh-pages` is a **stated skip** rather than an empty list,
  and an unreachable remote fails rather than reading as "nothing changed".
