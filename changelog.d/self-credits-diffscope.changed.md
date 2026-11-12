- `check-self-credits` now takes its git, diff, listing, and path-ignore helpers from `check-common/diffscope.py` instead of carrying its own copies (gha#1856).
  A file whose name holds `"`, a backslash, or a tab is now read in both diff-scoped and whole-tree runs,
  where before git's quoting of the name left it unread.
