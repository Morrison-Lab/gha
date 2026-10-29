- **`check-write-idiom`'s diff engine** and **`check-proof-statements`**
  ([gha#1355](https://github.com/Morrison-Lab/gha/issues/1355)):
  fix two silent skips in the diff engine shared by `check-write-idiom`, `check-avoided-words` and `check-proof-statements`.
  Under `diff.mnemonicPrefix=true` every touched file read as missing and the check passed with 0 files examined;
  the engine now passes `--src-prefix=a/ --dst-prefix=b/` and `--no-textconv`.
  A path holding a quote, a backslash or a control character, which git writes C-quoted, is now decoded instead of dropped.
  `check-proof-statements` reads a div's attributes as tokens, so attribute order and unquoted values no longer hide a `content-hidden` wrapper
  and a word inside `title="..."` no longer makes a theorem look like a proof.
  The reasoning rule no longer reads link targets, URLs, cross-references and `{#id}` blocks,
  and a `$$` that closes display math mid-line hands the rest of the line back to prose.
