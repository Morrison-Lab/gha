- **Fixes quadratic performance hang in `preview/highlight-html-changes.py`** (#948).
  Replaces repeated whole-string `.replace()` passes with a single-pass `re.finditer` span splice,
  preventing `O(n_changes * len(html))` re-scans and eliminating incorrect replacements on repeated identical elements.
  Adds `MAX_ELEMENTS_FOR_PAIRWISE` (default 500) to cap element comparisons on large pages and avoid `O(n_old * n_new)` runtime explosions.
