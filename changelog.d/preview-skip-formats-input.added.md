- **`skip-formats` input on `preview.yml` and the `preview` composite**
  ([gha#1186](https://github.com/Morrison-Lab/gha/issues/1186)).
  A space-separated list such as `pdf docx` that `preview/skip-formats.py` removes
  from the working copy's `_quarto*.yml` files and page front matter before the render.
  A PR preview built with `formats: default` then skips the slow PDF and Word formats
  while still building slide decks.
  A PR labelled `preview:<format>` keeps that format,
  and `docx-tracked-changes: true` keeps docx.
  It defaults to empty, so existing callers are unaffected.
  This replaces the copies of the script that lds, sds and mds carry.
