- **The read-only capability lists in `README.md` and `website/permissions.qmd`
  are now derived and checked, not restated** ([#559](https://github.com/Morrison-Lab/gha/issues/559)).
  The same fact -- which reusable workflows need only the default
  `contents: read`, so a caller needs no `permissions:` block -- was stated
  independently in both files, and the two had drifted apart and behind the
  workflows themselves: README named seven, the website three, and the
  workflows' own `permissions:` blocks said eighteen.
  Both lists are backfilled, and
  `.github/workflows/scripts/tests/run-permissions-docs-tests.py` now derives
  the set from those blocks and fails when either list disagrees.

- **`check-news.yml` declares `contents: read` explicitly.**
  It was the one reusable workflow declaring no permissions anywhere, so it
  inherited whatever the caller granted.
  Its own reference page already documented it as read-only, and the wrapped
  `UCD-SERG/changelog-check-action` only checks out and runs a local
  `git diff`, so the narrower token is sufficient.
