- `check-avoided-words` warns on "normal distribution", "standard normal", "multivariate normal", "bivariate normal", "normally distributed" and "normal random variable" on a line a pull request adds
  ([gha#1570](https://github.com/Morrison-Lab/gha/issues/1570); psw#510, write "Gaussian", not "normal").
  It does not flag "normal equations", normal vectors or normal subgroups.
  The rule is warn-only while it is new: it never fails the run, even with `fail` on.
  The shared engine in `check-write-idiom` gains a `warn_only` set for such trial rules.
  The check's allow comment exempts a deliberate use.
