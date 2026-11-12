- `check-term-links` and `check-removed-content` now take their git calls and diff helpers from `check-common/diffscope.py` (gha#1856).
  Both now read a file name holding a double quote, a backslash, or a tab as written, rather than in git's quoted form (gha#1923), and `check-term-links` does the same for a non-ASCII name.
  Before, `check-term-links` skipped the added lines of such a file, and `check-removed-content` reported the file under its quoted name and missed a PR body that named it.
