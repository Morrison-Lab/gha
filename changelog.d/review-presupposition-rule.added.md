- **`claude-code-review.yml`: the Morrison-Lab content rules now include a
  presupposition rule.** The reviewer flags a definite noun phrase with no
  earlier antecedent or link, and wording that presumes a conclusion the text
  has not shown, as a blocking finding on notes content. The warn-only
  `check-definite-antecedents` heuristic still covers only a div's first
  sentence; this rule covers the rest of the prose.
