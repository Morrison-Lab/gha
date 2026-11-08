- **`external-targets` input on `check-quarto-links`.**
  A link to a page that does not exist is not reported when its target matches these globs,
  for links that a Lua filter repoints at render time.
  A project that includes a submodule's subfiles, such as mcs including mds,
  otherwise gets a false finding for every link to a page of the submodule's site
  ([gha#1692](https://github.com/Morrison-Lab/gha/issues/1692)).
  A matching page that does exist still gets its anchor checked.
