- **New `altdoc-multiversion-docs.yml` reusable workflow** renders an altdoc-based
  R package's Quarto docs site and deploys multiple versions side by side on
  `gh-pages` (`/dev/`, `/latest-tag/`, `/vX.Y.Z/`, plus PR previews and a root
  redirect landing page). Ported from `d-morrison/rpt`'s bespoke
  `docs.yaml` (the pattern `UCD-SERG/serocalculator#504` asked to
  incorporate) so altdoc-based packages don't each carry their own copy of
  the version-dropdown and landing-page generator scripts. Also fixes a gap
  in the ported pattern: the original skipped its whole job on PR close (so
  the preview directory was never actually removed); this version keeps the
  removal step reachable. Ships at `@v2` (postdates the `@v1` freeze). New
  internal composites: `.github/actions/generate-altdoc-version-dropdown`,
  `.github/actions/generate-altdoc-landing-page`, and
  `.github/actions/resolve-altdoc-base-url` (shared base-URL derivation used
  by both).
