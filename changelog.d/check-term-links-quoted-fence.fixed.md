- `check-term-links`:
  a code fence inside a blockquote (`> ` before the fence) is now skipped as code instead of read as prose, so a defined term in quoted code is no longer reported (gha#1905).
  As in Pandoc, a fence closes at the opener's quote depth or a shallower one, and a deeper `> ` fence line inside an unquoted block stays code.
