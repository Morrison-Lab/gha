- **`wrappers` input on `check-literal-math-letters`**,
  defaulting to empty so existing callers are unaffected.
  It names generic wrapper macros, such as `\vecf` and `\vec`,
  that only mark a symbol's type.
  A direct use of one on an added line is flagged in either mode,
  and whatever `letters` says,
  because the quantity then has no semantic macro.
  [Morrison-Lab/lds#2881](https://github.com/Morrison-Lab/lds/pull/2881) wrote `\vecf{z}` where `\aug{\vx}` belonged,
  and lds blocks only `J`, so nothing flagged it.
