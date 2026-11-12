- `check-def-title-synonyms` and `check-def-wiktionary` now import their git calls and diff parser from `check-common/diffscope.py` instead of carrying their own copies (gha#1856).
  Both pick up `-z` file listing, unquoting of quoted paths in the diff, and the pinned diff-prefix settings those copies lacked.
