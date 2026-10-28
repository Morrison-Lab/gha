- **`claude-code-review.yml`: the Morrison-Lab content rules now include two presupposition rules.**
  Rule 9 flags a definite noun phrase with no earlier antecedent or link.
  It blocks only in the first sentence of a div, section or example opener, and elsewhere it is a suggestion.
  Rule 10 suggests hedging wording that asserts a result the page has not shown.
  The warn-only `check-definite-antecedents` heuristic still covers only a div's first sentence.
