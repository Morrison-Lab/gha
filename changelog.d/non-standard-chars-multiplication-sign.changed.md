- `check-non-standard-chars` now flags the multiplication sign (`U+00D7`)
  alongside the curly quotes and en/em dashes it already covered
  ([#322](https://github.com/Morrison-Lab/gha/issues/322)).
  The shared ASCII-punctuation convention has always named it with the others,
  so consumers had a documented rule with no instrument behind it, and the two
  instances that prompted this had sat in `ucdavis/bcs` for months.
  Its ASCII replacement depends on context, unlike the rest: `x` or `*` in code
  and comments, and `$\times$` or `&times;` in `.qmd` prose, since Pandoc
  renders a `\uXXXX` escape literally rather than decoding it.
  **This is a behavior change for consumers**, which may flag pre-existing
  prose in repositories that were previously clean; this repository's own 46
  in-scope files carry none.
