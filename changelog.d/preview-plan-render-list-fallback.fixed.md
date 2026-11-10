- **`preview` plans an incremental render when `quarto inspect` fails**
  ([#1608](https://github.com/Morrison-Lab/gha/issues/1608)).
  `quarto inspect` can fail on an include nested in a subfile,
  and the planner then chose a full render even with a restored cache.
  It now lists the pages from the `project.render` entries
  of `_quarto.yml` and the profile file when `quarto inspect` lists none.
