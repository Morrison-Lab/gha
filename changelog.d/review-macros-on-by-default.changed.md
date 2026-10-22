- `claude-code-review.yml`: the `check-latex-macros` input now defaults to `true`,
  and its review guidance enforces the lab's semantic-macro rule instead of only
  suggesting a macro for a duplicated expansion.
  The reviewer flags a literal letter for a symbol that has a macro, raw `e^{...}`
  and other raw operators, hat forms where a semantic macro exists, deprecated
  aliases, a hand-typed `\paren` around an `f` form, and macros defined outside
  `Morrison-Lab/macros`.
  It stays silent on a diff with no math.
  Agents kept writing literal math because this guidance was off by default and
  no notes repo's caller turned it on
  ([Morrison-Lab/ai-config#4673](https://github.com/Morrison-Lab/ai-config/issues/4673)).
  Set `check-latex-macros: false` to opt a repository out.
