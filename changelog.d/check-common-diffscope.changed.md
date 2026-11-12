- A shared module, `check-common/diffscope.py`, now holds one tested copy of the diff-scoping helpers the checks each carry (gha#1856).
  `check-one-div-per-subfile` imports it instead of defining its own copy.
  The checks that load that script keep working unchanged, because it re-exports the helpers under their old names.
