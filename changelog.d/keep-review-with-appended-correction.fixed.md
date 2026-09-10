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
  corrects through the last verdict-bearing block.
  A heading block that lacks the structured review-data payload never
  replaces a held draft that carries it, whatever its length;
  the length rule decides every other pair,
  including a payload-bearing block arriving after a payload-free draft,
  and its boundary is pinned from both sides by fixtures.
