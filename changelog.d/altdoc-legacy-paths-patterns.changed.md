- **`legacy-paths` in `altdoc-multiversion-docs.yml` gains pattern-and-template and exact mappings** (#851),
  enabling redirects across shape-changing migrations (such as pkgdown to altdoc).
  Exact whole-path keys (`reference/index.html=latest-tag/reference.html`) match
  first; prefix globs (`reference/*=latest-tag/man/*`) substitute the remainder
  into the target template with longest-prefix precedence; and single-segment
  renames (`main=dev`) preserve their prefix-rename semantics.
  Fail-closed validation rejects bare wildcards, misplaced wildcards,
  and targets that match another entry to prevent loops.
