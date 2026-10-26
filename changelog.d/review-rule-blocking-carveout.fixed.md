- **`claude-code-review.yml`: the content rules' "report each violation as blocking" sentence now defers to rules 9 and 10.**
  Rule 9 blocks only in a div's first sentence and rule 10 is always a suggestion, so the blanket sentence contradicted them.
  The sentence now ends "except where rules (9) and (10) say otherwise".
