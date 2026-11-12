- `check-wikipedia-further-reading` and `check-redundant-citations` now import their git, glob, and file helpers from `check-common/diffscope.py` instead of carrying their own copies (gha#1856).
  Both pick up `-z` file listing and the pinned diff-prefix settings those copies lacked, and `check-wikipedia-further-reading` also takes the shared diff parser, which unquotes quoted paths.
