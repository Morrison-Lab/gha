* `check-links.yml` now comments on the open "Broken links detected in main
  branch" issue when links break again, instead of filing a duplicate on every
  failing run. It shares the new `open-failure-issue` action with
  `report-failure.yml` rather than carrying its own `gh issue create` call. A
  label the calling repository does not define no longer fails the step -- the
  issue is filed without it, with a warning
  ([#325](https://github.com/d-morrison/gha/issues/325)).
