- A shared module, `check-common/diffscope.py`, now holds one tested copy of the diff-scoping helpers the checks each carry (gha#1856).
  Checks move onto it in later pull requests, starting with `check-one-div-per-subfile`, which more than a dozen checks load.
