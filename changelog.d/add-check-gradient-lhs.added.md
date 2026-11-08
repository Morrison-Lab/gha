Add `check-gradient-lhs`, a diff-scoped check that warns when a page states a gradient ("the gradient is ...") and the equation has no gradient symbol on its left-hand side ([gha#1538](https://github.com/Morrison-Lab/gha/issues/1538), from [psw#488](https://github.com/Morrison-Lab/psw/issues/488)).
It warns by default and takes the same inputs as `check-proof-statements`.
