- `check-term-links`:
  a code fence inside a blockquote (a `>` before the fence) is now skipped as code instead of read as prose, so a defined term in quoted code is no longer reported (gha#1905).
  As in Pandoc, a fence closes at the opener's quote depth or a shallower one, and a deeper quoted fence line inside an unquoted block stays code.
  A line that is blank inside a shallower quote, such as a blank line, ends the opener's blockquote, and with it a quoted fence that never closed.
