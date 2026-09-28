- **New `check-typed-output` capability** (composite `check-typed-output/`
  plus reusable `check-typed-output.yml`,
  [gha#959](https://github.com/Morrison-Lab/gha/issues/959)).
  Flags typed ("faked") code output in `.qmd` files:
  a comment standing in for a printed value
  (`# ->`, `#->`, `# =>`, `#>`, `# Output:`)
  inside a `python`/`r`/`julia` fence or an executable `{r}`/`{python}` chunk,
  and a hand-written output block
  (a fence with no language, or `text`/`output`)
  right after such a fence.
  Scans the whole tree by default and warns rather than fails;
  `diff-scoped: true` reports only the lines a pull request adds,
  so a repository with legacy occurrences can adopt it without every run
  reporting them.
  Ships at `@v3` only.
