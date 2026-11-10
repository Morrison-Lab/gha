- `student-qmd` gains a `drop-front-matter-keys` input (default empty, so nothing changes)
  that removes the named top-level front-matter keys from each student file,
  for instructor-only settings such as a `canvas:` block that syncs an assignment to a course site (gha#1805).
  A nested key of the same name stays.
  The check removes the same keys from the source before comparing,
  so any other metadata difference still fails it.
