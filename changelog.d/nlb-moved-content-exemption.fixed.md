- **`check-new-line-breaks`: moved content is not new content** --
  a flagged added line that exists verbatim anywhere in the base tree is
  now exempted as relocated rather than new, so a PR that splits an
  existing file no longer reflags every grandfathered line it moves
  ([#684](https://github.com/Morrison-Lab/gha/issues/684)).
