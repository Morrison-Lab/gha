- **`claude-code-review` keeps a review whose tail is an appended
  self-correction** (#850).
  gha#805's last-heading rule read every later authored `### Verdict`
  heading as a complete redraft, so a reviewer that wrote a full review and
  then appended a short correction carrying its own heading had the review
  dropped and only the correction posted, citing analysis nobody could see
  (gha#710's failure, reintroduced).
  A later heading block now replaces the current draft only when it is at
  least half the length of the longest draft held so far;
  a shorter one is a correction, and the posted text runs from the draft it
  corrects (or, when no later block replaced the first, from the first
  verdict-bearing block) through the last verdict-bearing block.
  A heading block that lacks the structured review-data payload never
  replaces a held draft that carries it, whatever its length;
  the length rule decides every other pair,
  including a payload-bearing block arriving after a payload-free draft,
  and its boundary is pinned from both sides by fixtures.
  Because the posted text can now carry two verdict statements,
  `classify-review-verdict` no longer lets a payload decide when an authored
  verdict heading follows it:
  a retracting correction carries no payload of its own,
  so without that the retracted review's `CLEAN` payload still decided and
  `require-clean-verdict` went green over an explicit withdrawal.
  Label forms are excluded from that signal,
  since gha#710's follow-up tail is written that way and means the verdict
  stands,
  and so is a heading whose word continues into another,
  since an ordinary `### Verdict rationale` section in a single uncorrected
  review would otherwise discard that review's payload and re-score it from
  prose.
  A qualified heading (`### Verdict (revised)`, `### Verdict: Needs more work`)
  does supersede.
  When the rule fires but the prose that follows states no verdict either way,
  the payload is used after all rather than reporting no recognisable verdict,
  so a review whose correction merely confirms it is not failed for saying so.
