- **`altdoc-multiversion-docs.yml` now shows which version a reader is
  looking at** (#307). The navbar "Versions" menu is labeled with the version
  the build renders -- `v1.2.3 (stable)`, `0.1.0.9000 (dev)`, or an archived
  `v1.1.0` -- instead of a static "Versions", so the menu names the entry it
  is currently on. The navbar title also carries that version beside the
  package name, after pkgdown, muted for a release build and red for a
  development one. The badge is written to Quarto's `website.navbar.title`,
  leaving `website.title` -- and so the page `<title>`, feed, and
  social-card metadata -- unchanged. Two new inputs control this:
  `version-dropdown-title-template` (default `{version}`; set e.g.
  `Version: {version}` to keep a word beside the number) and
  `version-in-navbar-title` (default `true`).
- **The `generate-altdoc-version-dropdown` composite gains matching
  `current-version`, `dropdown-title-template`, and `version-in-navbar-title`
  inputs, and a `current-version` output** (#307). `current-version` names
  the version being rendered -- a release tag, or `dev`; left empty, the
  composite infers it from the rendered checkout's `DESCRIPTION` version.
  `altdoc-multiversion-docs.yml` passes it from the event, which distinguishes
  a release build from a default branch that has not been version-bumped
  since its last release. The rewritten menu block is now preceded by a
  generated-by marker comment, which also lets a re-run find the block after
  the first run has replaced its `- text: Versions` anchor.
