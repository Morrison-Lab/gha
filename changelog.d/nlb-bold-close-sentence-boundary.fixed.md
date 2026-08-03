- **`check-new-line-breaks` now flags a sentence ending in Markdown emphasis**
  (#397).
  The sentence-boundary regex's closing-character class omitted `*` and `_`,
  so the emphasis close in `**Claim.** Explanation.` sat between the period
  and the whitespace and defeated the boundary ---
  meaning the check silently passed newly-added lines of that shape.
  Measured on 2026-08-03, the two characters take the multi-sentence lines
  detected across `Morrison-Lab/ai-config`'s Markdown from 2837 to 3398
  (+19.8%), and across this repo's from 719 to 784 (+9.0%).
  The class now accepts both emphasis characters;
  a lowercase word after the close still blocks the split via the existing
  uppercase-or-markup lookahead, so mid-sentence emphasis is left intact.
  Mirrors the same fix to the sibling reformatter in
  [`Morrison-Lab/ai-config#1098`](https://github.com/Morrison-Lab/ai-config/pull/1098).
