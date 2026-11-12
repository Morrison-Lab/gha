- `check-new-line-breaks` now checks a file whose name git quotes or pads in diff output.
  That covers a name holding a quote, backslash, tab, space or non-ASCII character.
  Before, such a file was recorded under a garbled path and its violations went unreported.
  The script now takes its git calls and path decoding from `check-common/diffscope.py`,
  so a copy of the script run outside this repository needs that directory beside it (gha#1927).
