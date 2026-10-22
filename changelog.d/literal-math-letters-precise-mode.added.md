- `check-literal-math-letters`: add a precise `mode: known` and a deprecated-alias rule.
  `known` flags only a letter or Greek command that has a semantic macro
  (`y`, `Y`, `x`, `X`, `n`, `L`, `e`, `\theta`, `\beta`, `\varepsilon`, `\mu`),
  so index letters such as `k` and `p` pass; on `Morrison-Lab/lds` `main` it
  flags 2,702 lines where `all` flags 6,768.
  The letter `e` now suggests `\euler` (or `\e{...}` for a power), which covers raw `e^{...}`.
  `deprecated-files` reads rows of an interpretations file that say
  `deprecated, use \x` and flags a use of the deprecated macro on an added line,
  in either mode.
  The reusable workflow gains `mode`, `deprecated-files` and `submodules` inputs.
  Defaults are unchanged
  ([#1159](https://github.com/Morrison-Lab/gha/issues/1159)).
