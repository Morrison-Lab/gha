- **`check-fform-paren`**
  ([#1106](https://github.com/Morrison-Lab/gha/issues/1106)):
  also flag `\name\set{...}`, `\name\abs{...}`, `\name\norm{...}` and `\name\angb{...}`
  where `\namef{...}` exists,
  and read `\def\XXXf` aliases (such as `\def\Epf{\E}`) as f forms,
  so `\Ep\sb{X}` is flagged when `\Epf` is defined.
  Companion to
  [psw#286](https://github.com/Morrison-Lab/psw/issues/286).
