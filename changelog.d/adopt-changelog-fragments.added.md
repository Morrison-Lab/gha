- **Changelog fragments (`changelog.d/`)** — changelog entries are now added as
  individual files under `changelog.d/` (named `<slug>.<category>.md`) instead of
  by editing `CHANGELOG.md` directly, so two PRs in flight never conflict on the
  same `## [Unreleased]` lines. `changelog.d/assemble.sh` collates the fragments
  into `CHANGELOG.md` at release time, grouped by keepachangelog category. This
  sidesteps GitHub's PR-UI merge conflicts on the shared changelog, which the
  `.gitattributes` `merge=union` driver can't fix (GitHub doesn't apply custom
  merge drivers). See [`changelog.d/README.md`](changelog.d/README.md).
