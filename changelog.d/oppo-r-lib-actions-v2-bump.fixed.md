- **Bumps `r-lib/actions` third-party pins to `v2.14.0` across all composite actions**
  and expands Dependabot tracking coverage across the repository (#918).
  Composite actions `check-ai-tells`, `check-extra`, `lint-changed-files`,
  `lint-changed-lines`, and `spellcheck` now use `r-lib/actions` at `v2.14.0`
  (`f9a764fea8d5c63df6ef9a5c7795bf7deb5d7e05`),
  inheriting upstream r-hub HTTP retry reliability improvements and runner compatibility fixes.
  In addition, `.github/dependabot.yml` now tracks all 29 composite action directories
  containing external third-party action pins to prevent configuration drift.
