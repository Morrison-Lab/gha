- **`altdoc-multiversion-docs.yml` gains a `root-landing-target` input**
  ([UCD-SERG/serocalculator#681](https://github.com/UCD-SERG/serocalculator/issues/681)),
  pinning the docs subdirectory the site root's redirect page points at.
  By default each deploy points the root at whatever it just built, so a
  default-branch push sends every reader arriving at `/` to `/dev/` --
  documentation for unreleased behavior they do not have installed.
  Setting `root-landing-target: latest-tag` keeps the root on the released
  docs while each version still deploys to its own subdirectory.
