- `check-new-line-breaks`: recognize digits, open parentheses, and underscore emphasis as sentence boundaries (#884, closes #878).
  `_SENT_BREAK_RE`'s follower lookahead previously matched only uppercase letters and closing punctuation or quote/code/bracket markup, missing sentence boundaries where the following sentence opens with a count or number (e.g. `19 sites across 18 hooks...`), an open parenthesis (e.g. `(Measured on 2026-09-13.)`), or an underscore emphasis opener.
  Across `Morrison-Lab/ai-config`, the widening raises detected multi-sentence lines from 21,807 to 24,682 (+13.2%).
  Across this repository, detected multi-sentence lines rise from 376 to 390 (+3.7%).
