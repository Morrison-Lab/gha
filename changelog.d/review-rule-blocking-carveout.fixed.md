- **`claude-code-review.yml`: the content rules' "report each violation as blocking" sentence now defers to any rule that says otherwise.**
  Rule 9 blocks only in a div's first sentence, and rules 10 and 11 are always suggestions, so the blanket sentence contradicted them.
  The sentence now ends "except where a rule says to report it as a suggestion or limits when it blocks", so the next suggestion-only rule needs no edit here.
