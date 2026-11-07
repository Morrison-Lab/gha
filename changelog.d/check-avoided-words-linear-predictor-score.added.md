- **`check-avoided-words`** (gha#1568):
  add a `linpred` rule that flags "score" or "scores" on a line that also has
  `\eta`, "linear predictor", "log-odds", "logit", "sigmoid" or "logistic function".
  Write "log-odds" for a logistic regression and "linear predictor" for a GLM in general.
  The statistical score passes: "score function", "score equation", "score test",
  "Brier score", "z-score", "F1 score", "component score", a link whose text is "score",
  and a line holding `#def-score`.
