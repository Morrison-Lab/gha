- **`check-new-line-breaks`: moved content is not new content** --
  an added line whose exact text was also deleted somewhere in the same
  diff is now exempted as relocated rather than new, so a PR that splits
  an existing file no longer reflags every grandfathered line it moves;
  a line merely duplicating untouched base content still flags
  ([#684](https://github.com/Morrison-Lab/gha/issues/684)).
