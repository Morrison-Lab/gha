- **`check-language-suffix-names`**
  (Morrison-Lab/lds#3152):
  add a diff-scoped composite action and reusable workflow
  that fails a pull request that binds a name ending in a language suffix,
  such as `fit_py = model.fit(X, y)` or `fit_r <- lm(y ~ x)`,
  in a `{python}`, `{r}` or `{julia}` chunk.
  A Python object takes the same name as its R counterpart,
  since each language keeps its own namespace.
  A use of a suffixed name, an element or attribute assignment,
  and a keyword argument pass.
  Only lines a PR adds count, so existing pages never block.
