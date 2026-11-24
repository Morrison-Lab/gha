- `preview-deploy.yml` now waits, up to `pages-build-wait-minutes` (default 15), for a running GitHub Pages build to finish before pushing to `gh-pages`,
  so a preview push no longer cancels the build that would publish the main site (gha#2192).
