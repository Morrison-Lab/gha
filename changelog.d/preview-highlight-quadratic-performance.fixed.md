- **Fixes quadratic performance hang in `preview/highlight-html-changes.py`** (#948).
  Replaces repeated whole-string `.replace()` passes with a single-pass `re.finditer` span splice,
  preventing `O(n_changes * len(html))` re-scans and eliminating incorrect replacements on repeated identical elements.
  Adds `max-elements-for-pairwise` input (default 500) to cap element comparisons on large pages and avoid `O(n_old * n_new)` runtime explosions.
