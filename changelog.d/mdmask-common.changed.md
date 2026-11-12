- `check-write-idiom`, `check-fform-paren`, `check-macro-expansions`, and `check-local-macros` now take their Markdown masking (code spans, HTML comments, and the code-fence pattern) from `check-common/mdmask.py`, one copy instead of four (gha#1856).
  Their findings are unchanged.
